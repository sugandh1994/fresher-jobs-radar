"""Greenhouse public Job Board API (approved ✅ in docs/SOURCES.md).

One GET per company board per run. No key needed.
Company list lives in pipeline/sources/companies.json.
"""
from __future__ import annotations

from pipeline.http_client import SourceError, get_json
from pipeline.models import RawJob
from pipeline.sources.companies import load_companies

NAME = "greenhouse"
URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

# Per-company results from the last fetch(), read by run.py for the run log.
LAST_STATS: dict[str, dict] = {}


def fetch_board(slug: str, company: str) -> list[RawJob]:
    data = get_json(URL.format(slug=slug), {"content": "true"})
    jobs = []
    for item in data.get("jobs", []):
        item = dict(item, _company=company, _slug=slug)
        jobs.append(RawJob(source=NAME, payload=item))
    return jobs


def fetch() -> list[RawJob]:
    LAST_STATS.clear()
    out: list[RawJob] = []
    for slug, company in load_companies(NAME).items():
        try:
            got = fetch_board(slug, company)
            LAST_STATS[slug] = {"fetched": len(got), "error": None}
            out.extend(got)
        except SourceError as exc:  # one bad board must not stop the others
            LAST_STATS[slug] = {"fetched": 0, "error": str(exc)}
    if LAST_STATS and all(s["error"] for s in LAST_STATS.values()):
        raise SourceError("every Greenhouse board failed")
    return out
