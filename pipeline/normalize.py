"""Convert each source's raw JSON into the common Job schema."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from pipeline.models import Job, RawJob

MAX_DESCRIPTION = 2000

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_EXPERIENCE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:years?|yrs?)\b"   # "0-1 years", "2 to 4 yrs"
    r"|\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b",                      # "3+ years", "1 year"
    re.IGNORECASE,
)


def strip_html(text: str | None) -> str:
    text = _TAG_RE.sub(" ", text or "")
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def experience_hint(text: str) -> str | None:
    """First experience phrase found, e.g. "0-1 years", or None."""
    m = _EXPERIENCE_RE.search(text)
    return m.group(0) if m else None


def _from_adzuna(p: dict) -> Job:
    title = strip_html(p.get("title"))
    description = strip_html(p.get("description"))[:MAX_DESCRIPTION]
    loc = p.get("location") or {}
    location_raw = loc.get("display_name") or ""
    area = loc.get("area") or []
    if area and area[0] == "India" and "india" not in location_raw.lower():
        location_raw = f"{location_raw}, India" if location_raw else "India"
    created = p.get("created") or ""
    return Job(
        id=f"adzuna:{p.get('id')}",
        title=title,
        company=strip_html((p.get("company") or {}).get("display_name")) or "Unknown",
        location_raw=location_raw,
        url=p.get("redirect_url") or "",
        source="adzuna",
        posted_at=created[:10] or None,
        description=description,
        experience_hint=experience_hint(f"{title} {description}"),
        sources=["adzuna"],
    )


def _from_greenhouse(p: dict) -> Job:
    title = strip_html(p.get("title"))
    # Greenhouse sends HTML that is itself escaped (&lt;p&gt;), so unescape first.
    description = strip_html(html.unescape(p.get("content") or ""))[:MAX_DESCRIPTION]
    posted = p.get("first_published") or p.get("updated_at") or ""
    return Job(
        id=f"greenhouse:{p.get('_slug')}:{p.get('id')}",
        title=title,
        company=p.get("_company") or p.get("company_name") or p.get("_slug", ""),
        location_raw=strip_html((p.get("location") or {}).get("name")),
        url=p.get("absolute_url") or "",
        source="greenhouse",
        posted_at=posted[:10] or None,
        description=description,
        experience_hint=experience_hint(f"{title} {description}"),
        sources=["greenhouse"],
    )


def _from_lever(p: dict) -> Job:
    title = strip_html(p.get("text"))
    parts = [p.get("descriptionPlain") or ""]
    for section in p.get("lists") or []:
        parts.append(f"{section.get('text', '')}: {strip_html(section.get('content'))}")
    parts.append(p.get("additionalPlain") or "")
    description = strip_html(" ".join(parts))[:MAX_DESCRIPTION]

    cats = p.get("categories") or {}
    locations = cats.get("allLocations") or [cats.get("location") or ""]
    location_raw = " / ".join(l for l in locations if l)
    if p.get("workplaceType") == "remote" and "remote" not in location_raw.lower():
        location_raw = f"Remote - {location_raw}" if location_raw else "Remote"
    if p.get("country") == "IN" and "india" not in location_raw.lower():
        location_raw = f"{location_raw}, India" if location_raw else "India"

    created_ms = p.get("createdAt")
    posted = (datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).date().isoformat()
              if isinstance(created_ms, (int, float)) else None)
    return Job(
        id=f"lever:{p.get('_slug')}:{p.get('id')}",
        title=title,
        company=p.get("_company") or p.get("_slug", ""),
        location_raw=location_raw,
        url=p.get("hostedUrl") or "",
        source="lever",
        posted_at=posted,
        description=description,
        experience_hint=experience_hint(f"{title} {description}"),
        sources=["lever"],
    )


_MAPPERS = {"adzuna": _from_adzuna, "greenhouse": _from_greenhouse, "lever": _from_lever}


def normalize(raw: RawJob) -> Job:
    return _MAPPERS[raw.source](raw.payload)
