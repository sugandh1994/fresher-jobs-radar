"""Shared data shapes used across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RawJob:
    """One job exactly as a source returned it (before we clean it up)."""
    source: str             # e.g. "adzuna"
    payload: dict[str, Any] # the source's original JSON for this job


@dataclass
class Job:
    """The common Job schema every source is converted into (see CLAUDE.md)."""
    id: str
    title: str
    company: str
    location_raw: str
    url: str
    source: str
    posted_at: str | None          # ISO date "YYYY-MM-DD"
    description: str               # plain text, max 2000 chars
    role: str | None = None        # filled by the tagger
    city: str | None = None        # filled by the tagger
    experience_hint: str | None = None
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
