"""Lever public Postings API (approved ✅ in docs/SOURCES.md).

One GET per company per run. No key needed. Companies that have switched
the feed off return 404 — we log and skip them.
Company list lives in pipeline/sources/companies.json.
"""
from __future__ import annotations

from pipeline.http_client import SourceError, get_json
from pipeline.models import RawJob
from pipeline.sources.companies import load_companies

NAME = "lever"
URL = "https://api.lever.co/v0/postings/{slug}"

LAST_STATS: dict[str, dict] = {}


def fetch_board(slug: str, company: str) -> list[RawJob]:
    data = get_json(URL.format(slug=slug), {"mode": "json"})
    if not isinstance(data, list):
        raise SourceError(f"unexpected Lever response for {slug}")
    return [RawJob(source=NAME, payload=dict(item, _company=company, _slug=slug)) for item in data]


def fetch() -> list[RawJob]:
    LAST_STATS.clear()
    out: list[RawJob] = []
    for slug, company in load_companies(NAME).items():
        try:
            got = fetch_board(slug, company)
            LAST_STATS[slug] = {"fetched": len(got), "error": None}
            out.extend(got)
        except SourceError as exc:
            LAST_STATS[slug] = {"fetched": 0, "error": str(exc)}
    if LAST_STATS and all(s["error"] for s in LAST_STATS.values()):
        raise SourceError("every Lever board failed")
    return out
