"""Filter step (docs/SPEC.md step 3): keep India + fresher-level + last 30 days."""
from __future__ import annotations

import re
from datetime import date, timedelta

from pipeline.models import Job

MAX_AGE_DAYS = 30

_INDIA_WORDS = [
    "india", "mumbai", "navi mumbai", "bombay", "thane", "pune", "bengaluru", "bangalore", "delhi",
    "gurugram", "gurgaon", "noida", "faridabad", "ghaziabad", "hyderabad",
    "chennai", "kolkata", "ahmedabad", "jaipur", "kochi", "cochin",
    "chandigarh", "indore", "coimbatore",
]
_INDIA_RE = re.compile(r"\b(" + "|".join(map(re.escape, _INDIA_WORDS)) + r")\b", re.I)
_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh)\b", re.I)

# Sources whose results are India-only, so a bare "Remote" means Remote-India.
_INDIA_ONLY_SOURCES = {"adzuna"}

_FRESHER_RE = re.compile(
    r"\b(freshers?|interns?|internships?|trainees?|graduates?|entry[\s-]level|"
    r"junior|jr|new[\s-]grads?|campus|apprentices?|apprenticeship|early[\s-]career|"
    r"0\s*(?:-|–|to)\s*1\s*(?:years?|yrs?))\b",
    re.I,
)
# In a description, bare words like "graduate", "campus", "junior", "trainee"
# or "entry level" are often used in other senses ("Qualification: Graduate",
# "Andheri Campus office", "mentor junior engineers", "guide entry level
# engineers"). So descriptions only count with these clear phrases.
#
# Singular "intern"/"trainee" describe THIS job ("Marketing Intern", "a trainee
# role"); plural "our interns", "engage with trainees" describe other people.
# "junior"/"entry level" only count when not about people the job manages
# ("mentor junior engineers", "guidance to entry level engineers").
_PEOPLE = r"(?:team|members?|chefs?|staff|engineers|developers|sdets|colleagues|resources|talent|hires|candidates|employees|to\s+senior)"
_DESC_FRESHER_RE = re.compile(
    r"\b(freshers?|fresh\s+graduates?|recent\s+graduates?|new[\s-]grads?|"
    r"early[\s-]career|internships?|intern|trainee|"
    r"junior(?!\s+" + _PEOPLE + r")|jr\.?(?=\s)|"
    r"(?<!to\s)entry[\s-]level(?!\s+" + _PEOPLE + r")|"
    r"no\s+(?:prior\s+)?experience\s+(?:is\s+)?required|"
    r"0\s*(?:-|–|to)\s*\d{1,2}\s*(?:years?|yrs?))\b",
    re.I,
)
_NO_FRESHERS_RE = re.compile(
    r"\b(freshers?\s+(?:need\s+not|should\s+not|cannot|can't|do\s+not|don't)\s+apply|"
    r"no\s+freshers|not\s+(?:open\s+to|for)\s+freshers)\b",
    re.I,
)
_SENIOR_TITLE_RE = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|manager|head|director|architect|vp|chief)\b",
    re.I,
)
_MIN_YEARS_RE = re.compile(r"\b(\d{1,2})\s*(?:\+|-|–|to)?\s*\d{0,2}\s*(?:years?|yrs?)\b", re.I)


def is_india(job: Job) -> bool:
    """India city/'India' in the location. A bare 'Remote' only counts for
    India-only sources (Adzuna India); 'Remote - US' from Greenhouse does not."""
    if _INDIA_RE.search(job.location_raw):
        return True
    return job.source in _INDIA_ONLY_SOURCES and bool(_REMOTE_RE.search(job.location_raw))


def min_years(text: str) -> int | None:
    """Smallest 'N years' requirement mentioned, e.g. '2-4 years' -> 2."""
    found = [int(m.group(1)) for m in _MIN_YEARS_RE.finditer(text)]
    return min(found) if found else None


def is_fresher(job: Job) -> bool:
    """Fresher-level if:
      - the title has a fresher word (intern, trainee, fresher, graduate, ...), or
      - the description clearly says so ("freshers can apply", "0-1 years",
        "fresh graduates", "entry-level position", ...),
    and it is not ruled out by "freshers need not apply", a senior title, or
    a minimum of 1+ years with no mention of freshers.
    """
    text = f"{job.title} {job.description}"
    if _NO_FRESHERS_RE.search(text):
        return False
    if _FRESHER_RE.search(job.title):
        return True
    if _SENIOR_TITLE_RE.search(job.title):
        return False
    if _DESC_FRESHER_RE.search(job.description):
        return True
    # No fresher wording: only an explicit 0-year minimum counts. "1-3 years"
    # or "Minimum 1 year" is not open to someone with no experience.
    return min_years(text) == 0


# Company job boards only list jobs that are still open, so the posting age
# doesn't matter there (decision 2026-11-17, see docs/SPEC.md).
_OPEN_ONLY_SOURCES = {"greenhouse", "lever"}


def is_recent(job: Job, today: date | None = None) -> bool:
    if job.source in _OPEN_ONLY_SOURCES:
        return True
    if not job.posted_at:
        return True  # no date available -> keep (spec: "if a date is available")
    try:
        posted = date.fromisoformat(job.posted_at)
    except ValueError:
        return True
    today = today or date.today()
    return posted >= today - timedelta(days=MAX_AGE_DAYS)


def keep(job: Job) -> bool:
    return is_india(job) and is_fresher(job) and is_recent(job)
