"""Adzuna India — official Jobs API (approved ✅ in docs/SOURCES.md).

Searches once per fresher keyword, a few pages each, and returns every unique
job. Keys come from ADZUNA_APP_ID / ADZUNA_APP_KEY in .env (or GitHub Secrets).
"""
from __future__ import annotations

import os

from pipeline.http_client import SourceError, get_json
from pipeline.models import RawJob

NAME = "adzuna"
BASE_URL = "https://api.adzuna.com/v1/api/jobs/in/search/{page}"

# From docs/SPEC.md. Multi-word ones are searched as exact phrases.
KEYWORDS = [
    "fresher", "intern", "internship", "trainee",
    "graduate", "entry level", "junior", "0-1 years",
]
RESULTS_PER_PAGE = 50   # Adzuna's maximum
MAX_PAGES_PER_KEYWORD = 4
MAX_DAYS_OLD = 30


def fetch() -> list[RawJob]:
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise SourceError("ADZUNA_APP_ID / ADZUNA_APP_KEY are not set in .env")

    seen: dict[str, RawJob] = {}
    for keyword in KEYWORDS:
        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": RESULTS_PER_PAGE,
                "max_days_old": MAX_DAYS_OLD,
                "sort_by": "date",
            }
            params["what_phrase" if " " in keyword else "what"] = keyword
            data = get_json(BASE_URL.format(page=page), params)
            results = data.get("results", [])
            for item in results:
                job_id = str(item.get("id", ""))
                if job_id and job_id not in seen:
                    seen[job_id] = RawJob(source=NAME, payload=item)
            if len(results) < RESULTS_PER_PAGE:
                break  # no more pages for this keyword
    return list(seen.values())
