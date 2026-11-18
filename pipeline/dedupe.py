"""Dedupe step (docs/SPEC.md "Dedupe rules").

A job is a duplicate of an earlier one if ANY rule matches:
  1. url         — same canonical URL (tracking params + trailing slash removed)
  2. fingerprint — same cleaned-up title | company | city
  3. fuzzy       — same company AND same city AND title similarity >= 90
                   (rapidfuzz token_sort_ratio) AND same level words
                   ("New Associate" never merges with "Associate")

Duplicates are merged into one group. From each group we keep the job with
the longest description (ties -> most recent), give it the newest posted date
seen in the group, and list every source in `sources`.

Note: dedupe runs before LLM tagging, so "city" here comes from a simple
deterministic lookup on location_raw (city_key), not from the LLM.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from pipeline.models import Job

FUZZY_THRESHOLD = 90

# --- canonical URL --------------------------------------------------------

_TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "ref", "refid", "src", "source",
    "gh_src", "lever-source", "lever-origin", "trk", "mc_cid", "mc_eid",
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


# --- text cleaning --------------------------------------------------------

_COMPANY_NOISE = {
    "pvt", "private", "ltd", "limited", "inc", "incorporated", "llp", "llc",
    "corp", "corporation", "co", "company", "plc", "gmbh",
}
_PUNCT_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")


def clean(text: str) -> str:
    text = _PUNCT_RE.sub(" ", (text or "").lower())
    return _SPACE_RE.sub(" ", text).strip()


def clean_company(name: str) -> str:
    return " ".join(w for w in clean(name).split() if w not in _COMPANY_NOISE)


# --- city key (taxonomy cities + aliases from docs/TAXONOMY.md) -----------

_CITY_ALIASES = {
    "mumbai": ["mumbai", "bombay", "navi mumbai", "thane"],
    "pune": ["pune"],
    "bengaluru": ["bengaluru", "bangalore"],
    "delhi ncr": ["delhi", "new delhi", "gurugram", "gurgaon", "noida",
                  "greater noida", "faridabad", "ghaziabad"],
    "hyderabad": ["hyderabad"],
    "chennai": ["chennai"],
    "kolkata": ["kolkata"],
    "ahmedabad": ["ahmedabad"],
    "jaipur": ["jaipur"],
    "kochi": ["kochi", "cochin", "ernakulam"],
    "chandigarh": ["chandigarh"],
    "indore": ["indore"],
    "coimbatore": ["coimbatore"],
    "remote": ["remote", "work from home", "wfh"],
}
_ALIAS_TO_CITY = {alias: city for city, aliases in _CITY_ALIASES.items() for alias in aliases}
_CITY_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, _ALIAS_TO_CITY), key=len, reverse=True)) + r")\b"
)


def city_key(location_raw: str) -> str:
    """First taxonomy city mentioned, else the cleaned first part of the location."""
    loc = clean(location_raw)
    m = _CITY_RE.search(loc)
    if m:
        return _ALIAS_TO_CITY[m.group(1)]
    first = clean((location_raw or "").split(",")[0])
    return first or "unknown"


# Words that mark a job's level. "Associate" vs "New Associate" are different
# grades, so a fuzzy match is only allowed when both titles have the same ones.
_LEVEL_WORDS = {
    "new", "fresher", "freshers", "trainee", "intern", "internship", "apprentice",
    "graduate", "junior", "jr", "senior", "sr", "lead", "principal", "staff",
    "head", "manager", "i", "ii", "iii", "iv", "1", "2", "3", "4", "l1", "l2", "l3",
}


def level_words(clean_title: str) -> frozenset[str]:
    words = set(clean_title.split())
    found = {w for w in words if w in _LEVEL_WORDS}
    if "freshers" in found:                      # "(Freshers)" == "(Fresher)"
        found = (found - {"freshers"}) | {"fresher"}
    return frozenset(found)


def fingerprint(job: Job) -> str:
    key = f"{clean(job.title)}|{clean_company(job.company)}|{city_key(job.location_raw)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


# --- grouping -------------------------------------------------------------

@dataclass
class Removed:
    rule: str          # "url" | "fingerprint" | "fuzzy"
    kept: Job          # the job it matched (first job of the group)
    dropped: Job
    score: float | None = None


@dataclass
class _Group:
    jobs: list[Job] = field(default_factory=list)


def _merge(group: _Group) -> Job:
    jobs = group.jobs
    best = max(jobs, key=lambda j: (len(j.description), j.posted_at or ""))
    dates = [j.posted_at for j in jobs if j.posted_at]
    sources: list[str] = []
    for j in jobs:
        for s in j.sources or [j.source]:
            if s not in sources:
                sources.append(s)
    best.posted_at = max(dates) if dates else None
    best.sources = sources
    return best


def dedupe(jobs: list[Job]) -> tuple[list[Job], list[Removed]]:
    groups: list[_Group] = []
    by_url: dict[str, _Group] = {}
    by_fp: dict[str, _Group] = {}
    by_company_city: dict[tuple[str, str], list[_Group]] = {}
    removed: list[Removed] = []

    for job in jobs:
        url = canonical_url(job.url) if job.url else None
        fp = fingerprint(job)
        cc = (clean_company(job.company), city_key(job.location_raw))
        title = clean(job.title)

        match, rule, score = None, None, None
        if url and url in by_url:
            match, rule = by_url[url], "url"
        elif fp in by_fp:
            match, rule = by_fp[fp], "fingerprint"
        else:
            levels = level_words(title)
            for g in by_company_city.get(cc, []):
                scores = [fuzz.token_sort_ratio(title, clean(j.title)) for j in g.jobs
                          if level_words(clean(j.title)) == levels]
                s = max(scores, default=0)
                if s >= FUZZY_THRESHOLD:
                    match, rule, score = g, "fuzzy", s
                    break

        if match is None:
            match = _Group()
            groups.append(match)
            by_company_city.setdefault(cc, []).append(match)
        else:
            removed.append(Removed(rule=rule, kept=match.jobs[0], dropped=job, score=score))

        match.jobs.append(job)
        if url:
            by_url.setdefault(url, match)
        by_fp.setdefault(fp, match)

    return [_merge(g) for g in groups], removed
