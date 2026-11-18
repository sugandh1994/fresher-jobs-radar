"""Pipeline entry point: fetch -> normalize -> filter -> dedupe -> tag -> write.

    python -m pipeline.run            # full run
    python -m pipeline.run --no-llm   # no new LLM calls (cached tags still used)
    python -m pipeline.run --skip-fetch   # re-tag site/jobs.json without calling sources
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipeline import filters
from pipeline.dedupe import city_key, dedupe
from pipeline.models import Job
from pipeline.logos import logo_for
from pipeline.normalize import normalize
from pipeline.tagger import load_taxonomy, tag_jobs
from pipeline.sources import adzuna, greenhouse, lever

ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = ROOT / "site" / "jobs.json"
RUN_LOG_FILE = ROOT / "data" / "run_log.json"
OUT_OF_SCOPE_ROLE = "Other"  # jobs the LLM tags with this role are not shown on the site

# Add new approved sources here (Jooble is waiting on its key — see SOURCES.md).
SOURCES = [adzuna, greenhouse, lever]

log = logging.getLogger("pipeline")


def fetch_all(run_log: dict) -> list:
    raw_jobs = []
    for source in SOURCES:
        entry = {"fetched": 0, "error": None}
        try:
            got = source.fetch()
            entry["fetched"] = len(got)
            raw_jobs.extend(got)
            log.info("%s: fetched %d jobs", source.NAME, len(got))
        except Exception as exc:  # one bad source must not stop the run
            entry["error"] = str(exc)
            log.error("%s: FAILED — %s (continuing)", source.NAME, exc)
        boards = getattr(source, "LAST_STATS", None)
        if boards:
            entry["boards"] = {slug: dict(stats) for slug, stats in boards.items()}
            for slug, stats in boards.items():
                if stats["error"]:
                    log.warning("  %s/%s: %s (skipped)", source.NAME, slug, stats["error"])
        run_log["sources"][source.NAME] = entry
    return raw_jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fresher Jobs Radar pipeline")
    parser.add_argument("--no-llm", action="store_true", help="skip LLM tagging")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="don't call any source; re-tag the jobs already in site/jobs.json")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(ROOT / ".env")

    started = datetime.now(timezone.utc)
    if args.skip_fetch:
        previous = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        known = {f.name for f in fields(Job)}  # ignore display-only extras like city_from_location
        loaded = [Job(**{k: v for k, v in j.items() if k in known}) for j in previous["jobs"]]
        run_log = json.loads(RUN_LOG_FILE.read_text(encoding="utf-8"))  # keep fetch/dedupe stats
        run_log["retagged_at"] = started.isoformat(timespec="seconds")
        # Re-apply the current filter rules (they may have been tightened since the fetch).
        jobs = [j for j in loaded if filters.keep(j)]
        run_log["steps"]["after_refilter"] = len(jobs)
        log.info("skip-fetch: loaded %d jobs, %d still pass the filter",
                 len(loaded), len(jobs))
    else:
        run_log = {"started_at": started.isoformat(timespec="seconds"), "sources": {}, "steps": {}}
        jobs = fetch_filter_dedupe(run_log)
    tag_and_write(jobs, run_log, use_llm=not args.no_llm)
    return 0


def fetch_filter_dedupe(run_log: dict) -> list[Job]:
    # 1. Fetch
    raw_jobs = fetch_all(run_log)
    run_log["steps"]["fetched"] = len(raw_jobs)

    # 2. Normalize
    jobs = []
    for raw in raw_jobs:
        try:
            jobs.append(normalize(raw))
        except Exception as exc:
            log.warning("could not normalize a %s job: %s", raw.source, exc)
    run_log["steps"]["normalized"] = len(jobs)

    # 3. Filter
    jobs = [j for j in jobs if filters.keep(j)]
    run_log["steps"]["after_filter"] = len(jobs)
    for name, entry in run_log["sources"].items():
        entry["after_filter"] = sum(1 for j in jobs if j.source == name)
        for slug, stats in entry.get("boards", {}).items():
            prefix = f"{name}:{slug}:"
            stats["after_filter"] = sum(1 for j in jobs if j.id.startswith(prefix))

    # 4. Dedupe
    jobs, removed = dedupe(jobs)
    run_log["steps"]["after_dedupe"] = len(jobs)
    run_log["dedupe"] = {
        "removed_by_rule": {r: sum(1 for x in removed if x.rule == r)
                            for r in ("url", "fingerprint", "fuzzy")},
        "examples": [
            {"rule": x.rule, "score": x.score,
             "kept": {"id": x.kept.id, "title": x.kept.title, "company": x.kept.company,
                      "location": x.kept.location_raw, "url": x.kept.url},
             "dropped": {"id": x.dropped.id, "title": x.dropped.title, "company": x.dropped.company,
                         "location": x.dropped.location_raw, "url": x.dropped.url}}
            for rule in ("url", "fingerprint", "fuzzy")
            for x in [r for r in removed if r.rule == rule][:5]
        ],
    }
    for name, entry in run_log["sources"].items():
        entry["after_dedupe"] = sum(1 for j in jobs if name in j.sources)
    log.info("dedupe: removed %d duplicates %s", len(removed), run_log["dedupe"]["removed_by_rule"])
    return jobs


def location_city(location_raw: str, cities: list[str]) -> str | None:
    """Taxonomy city read straight from the location text (no LLM), e.g.
    "Bangalore, Karnataka" -> "Bengaluru", "Kanpur, UP" -> "Other India",
    "India" -> None (city unknown). The page uses it when the LLM city is missing,
    so city filters and counts work even before tagging."""
    key = city_key(location_raw or "")
    if key in ("", "india", "unknown"):
        return None
    by_key = {c.lower(): c for c in cities}
    return by_key.get(key, "Other India" if "Other India" in cities else None)


def tag_and_write(jobs: list[Job], run_log: dict, use_llm: bool) -> None:
    # 5. Tag (cached tags are always applied; --no-llm only skips new API calls)
    try:
        stats = tag_jobs(jobs, use_llm=use_llm)
    except Exception as exc:  # tagging trouble must not lose the fetched jobs
        stats = {"error": f"{type(exc).__name__}: {exc}"}
        log.error("tagging: FAILED — %s (writing jobs untagged)", stats["error"])
    fallback_ids = set(stats.pop("fallback_ids", []))
    run_log["tagging"] = stats
    run_log["steps"]["tagged"] = sum(1 for j in jobs if j.role)
    # Quality is measured BEFORE the scope step, so hiding "Other" jobs can't
    # make the >=90% target look better than the tagging really is.
    run_log["quality"] = {
        "role_not_other": sum(1 for j in jobs if j.role and j.role != "Other"),
        "city_not_other": sum(1 for j in jobs if j.city and j.city != "Other India"),
        "total_tagged": sum(1 for j in jobs if j.role),
        "total": len(jobs),
    }
    log.info("tagging: %s", {k: v for k, v in stats.items() if k != "usage"})

    # 5b. Scope: the site covers the roles in TAXONOMY.md. Hide jobs the model
    # decided are role "Other" (e.g. Radiologist, Electrician, Sewing Trainee).
    # Untagged jobs and error fallbacks stay — we don't know their role yet.
    out_of_scope = [j for j in jobs if j.role == OUT_OF_SCOPE_ROLE and j.id not in fallback_ids]
    hidden_ids = {j.id for j in out_of_scope}
    jobs = [j for j in jobs if j.id not in hidden_ids]
    run_log["steps"]["after_scope"] = len(jobs)
    run_log["out_of_scope"] = {
        "hidden": len(out_of_scope),
        "examples": [f"{j.title} — {j.company}" for j in out_of_scope[:15]],
    }
    if out_of_scope:
        log.info("scope: hid %d jobs tagged role 'Other'", len(out_of_scope))

    # 6. Write. "updated_at" = when the job data was last fetched, so a
    # --skip-fetch re-tag keeps the previous value.
    jobs.sort(key=lambda j: j.posted_at or "", reverse=True)
    roles, cities, _ = load_taxonomy()  # page dropdowns come from TAXONOMY.md
    roles = [r for r in roles if r != OUT_OF_SCOPE_ROLE]  # hidden jobs -> no "Other" option
    now =datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated_at = run_log.get("finished_at", now) if "retagged_at" in run_log else now
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(
        json.dumps({"updated_at": updated_at, "count": len(jobs),
                    "taxonomy": {"roles": roles, "cities": cities},
                    "jobs": [{**j.to_dict(), "city_from_location": location_city(j.location_raw, cities),
                               "logo": logo_for(j.company)}
                             for j in jobs]}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    run_log["steps"]["final"] = len(jobs)
    run_log["finished_at"] = updated_at
    RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG_FILE.write_text(json.dumps(run_log, indent=2), encoding="utf-8")

    shown_path = JOBS_FILE.relative_to(ROOT) if JOBS_FILE.is_relative_to(ROOT) else JOBS_FILE
    log.info("done: %d fresher jobs in India written to %s", len(jobs), shown_path)


if __name__ == "__main__":
    raise SystemExit(main())
