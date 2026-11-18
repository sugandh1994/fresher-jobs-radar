"""Tag step (docs/SPEC.md "Tagging"): an LLM picks one role and one city per job.

- Allowed values are read from docs/TAXONOMY.md (single source of truth).
- 20 jobs per request; only id, title, company, location_raw and the first
  600 characters of the description are sent.
- The API is asked for JSON matching a fixed schema whose role/city fields
  are limited to the taxonomy lists, and we validate the answer again anyway.
- Bad/missing answer -> retry once -> fall back to "Other" / "Other India".
- Results are cached in data/tag_cache.json by job fingerprint; a cached job
  is never sent again. Fallbacks are NOT cached, so they get another try
  next run.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline.dedupe import fingerprint
from pipeline.models import Job

log = logging.getLogger("pipeline.tagger")

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_FILE = ROOT / "docs" / "TAXONOMY.md"
CACHE_FILE = ROOT / "data" / "tag_cache.json"

MODEL = "claude-haiku-5-5"
BATCH_SIZE = 20
DESCRIPTION_CHARS = 600
MAX_TOKENS = 8000
# Haiku 5.5 prices (USD per 1M tokens) — used only for the cost line in the run log.
PRICE_IN, PRICE_OUT = 0.10, 0.50
USD_TO_INR = 90  # rough, for the ₹50/day budget check

FALLBACK_ROLE = "Other"
FALLBACK_CITY = "Other India"  # every job is already filtered to India


# --- taxonomy --------------------------------------------------------------

def load_taxonomy(path: Path = TAXONOMY_FILE) -> tuple[list[str], list[str], str]:
    """Return (roles, cities, mapping_notes) parsed from TAXONOMY.md."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line.rstrip())

    def bullets(name: str) -> list[str]:
        # "- Delhi NCR (Delhi, Gurugram, ...)" -> "Delhi NCR"
        return [re.sub(r"\s*\(.*\)\s*$", "", l[2:]).strip()
                for l in sections.get(name, []) if l.startswith("- ")]

    roles, cities = bullets("roles"), bullets("cities")
    notes = "\n".join(sections.get("mapping notes", []))
    if not roles or not cities:
        raise ValueError("could not read Roles/Cities lists from TAXONOMY.md")
    return roles, cities, notes


# --- cache -----------------------------------------------------------------

def load_cache(path: Path = CACHE_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict, path: Path = CACHE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")


# --- prompt ----------------------------------------------------------------

def build_system_prompt(roles: list[str], cities: list[str], notes: str) -> str:
    return (
        "You label fresher job and internship posts in India for a job search site.\n"
        "For every job you are given, choose exactly one role and exactly one city.\n\n"
        "Roles (pick the closest match; use \"Other\" only if none fit):\n"
        + "\n".join(f"- {r}" for r in roles)
        + "\n\nCities:\n"
        + "\n".join(f"- {c}" for c in cities)
        + "\n\nCity rules:\n"
        "- Delhi NCR covers Delhi, New Delhi, Gurugram/Gurgaon, Noida, Faridabad, Ghaziabad.\n"
        "- Remote / work from home jobs -> \"Remote\".\n"
        "- If several cities are listed, use the first one.\n"
        "- If the location only says \"India\", look for a city in the description; "
        "if there is none, use \"Other India\".\n"
        "- A real Indian city not in the list -> \"Other India\".\n"
        + (f"\nMapping notes:\n{notes}\n" if notes else "")
        + "\nReturn one entry per job, using the job's id exactly as given."
    )


def output_schema(roles: list[str], cities: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "role": {"type": "string", "enum": roles},
                        "city": {"type": "string", "enum": cities},
                    },
                    "required": ["id", "role", "city"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["tags"],
        "additionalProperties": False,
    }


def job_payload(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location_raw": job.location_raw,
        "description": job.description[:DESCRIPTION_CHARS],
    }


# --- calling the model -----------------------------------------------------

def parse_answer(text: str, batch_ids: set[str], roles: list[str], cities: list[str]) -> dict[str, dict]:
    """Validate the model's JSON. Returns {id: {role, city}} for valid entries."""
    data = json.loads(text)
    out = {}
    for item in data.get("tags", []):
        if not isinstance(item, dict) or item.get("id") not in batch_ids:
            continue
        role = item.get("role") if item.get("role") in roles else FALLBACK_ROLE
        city = item.get("city") if item.get("city") in cities else FALLBACK_CITY
        out[item["id"]] = {"role": role, "city": city}
    return out


class Tagger:
    def __init__(self, client=None, taxonomy=None):
        self.roles, self.cities, notes = taxonomy or load_taxonomy()
        self.system = build_system_prompt(self.roles, self.cities, notes)
        self.schema = output_schema(self.roles, self.cities)
        self._client = client
        self.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(max_retries=3, timeout=120.0)
        return self._client

    def _call(self, batch: list[Job]) -> str:
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self.system,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": self.schema},
            },
            messages=[{
                "role": "user",
                "content": "Label these jobs:\n" + json.dumps(
                    [job_payload(j) for j in batch], ensure_ascii=False),
            }],
        )
        self.usage["requests"] += 1
        self.usage["input_tokens"] += response.usage.input_tokens
        self.usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ValueError(f"model stopped early ({response.stop_reason})")
        return next(b.text for b in response.content if b.type == "text")

    def tag_batch(self, batch: list[Job]) -> dict[str, dict]:
        """Tag one batch. Retries once for jobs missing from a bad answer."""
        results: dict[str, dict] = {}
        todo = list(batch)
        for attempt in (1, 2):
            try:
                text = self._call(todo)
                results.update(parse_answer(text, {j.id for j in todo}, self.roles, self.cities))
            except (json.JSONDecodeError, ValueError, StopIteration) as exc:
                log.warning("tagging: bad answer on attempt %d (%s)", attempt, exc)
            todo = [j for j in todo if j.id not in results]
            if not todo:
                break
        return results

    def cost_usd(self) -> float:
        return (self.usage["input_tokens"] * PRICE_IN + self.usage["output_tokens"] * PRICE_OUT) / 1e6


def tag_jobs(jobs: list[Job], use_llm: bool = True, tagger: Tagger | None = None,
             cache_path: Path = CACHE_FILE) -> dict:
    """Fill job.role / job.city in place. Returns stats for the run log."""
    cache = load_cache(cache_path)
    stats = {"from_cache": 0, "newly_tagged": 0, "fallback": 0, "untagged": 0, "error": None,
             "fallback_ids": []}  # jobs whose "Other" is an error fallback, not the model's choice

    todo = []
    for job in jobs:
        hit = cache.get(fingerprint(job))
        if hit:
            job.role, job.city = hit["role"], hit["city"]
            stats["from_cache"] += 1
        else:
            todo.append(job)

    if not todo:
        return stats
    if not use_llm:
        stats["untagged"] = len(todo)
        return stats

    import anthropic

    tagger = tagger or Tagger()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        try:
            results = tagger.tag_batch(batch)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                anthropic.BadRequestError, anthropic.NotFoundError) as exc:
            # Account/key/request problems repeat on every batch: stop now and
            # leave the rest untagged (role/city = None) so the next run retries.
            stats["error"] = f"{type(exc).__name__}: {getattr(exc, 'message', exc)}"
            log.error("tagging: %s — stopping LLM calls for this run", stats["error"])
            stats["untagged"] += len(todo) - i
            break
        except anthropic.APIError as exc:  # temporary trouble (after SDK retries)
            stats["error"] = type(exc).__name__
            log.error("tagging: batch %d failed (%s); left untagged", i // BATCH_SIZE + 1, stats["error"])
            stats["untagged"] += len(batch)
            continue
        for job in batch:
            tag = results.get(job.id)
            if tag:
                job.role, job.city = tag["role"], tag["city"]
                cache[fingerprint(job)] = {**tag, "model": MODEL, "tagged_at": now}
                stats["newly_tagged"] += 1
            else:
                job.role, job.city = FALLBACK_ROLE, FALLBACK_CITY  # not cached: retry next run
                stats["fallback"] += 1
                stats["fallback_ids"].append(job.id)
        save_cache(cache, cache_path)  # save as we go so a crash keeps progress
        log.info("tagging: %d/%d done", min(i + BATCH_SIZE, len(todo)), len(todo))

    stats["usage"] = dict(tagger.usage)
    stats["cost_usd"] = round(tagger.cost_usd(), 4)
    stats["cost_inr_approx"] = round(tagger.cost_usd() * USD_TO_INR, 2)
    return stats
