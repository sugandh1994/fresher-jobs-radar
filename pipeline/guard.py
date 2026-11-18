"""Publish guard: refuse to publish a job list that shrank suspiciously.

If a big source fails (e.g. Adzuna is down), the pipeline still finishes —
but publishing ~20 jobs over yesterday's ~480 would make the site look broken.
In that case this exits with an error, the daily workflow stops before
committing/deploying, and the live site keeps yesterday's list.

    python -m pipeline.guard <previous_jobs.json> <new_jobs.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MIN_JOBS = 50          # never publish fewer than this
MIN_RATIO = 0.5        # never publish less than half of the previous list


def count(path: Path) -> int | None:
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["count"])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return None


def check(previous: int | None, new: int | None) -> tuple[bool, str]:
    if new is None:
        return False, "new jobs.json is missing or unreadable"
    if new < MIN_JOBS:
        return False, f"only {new} jobs (minimum {MIN_JOBS})"
    if previous and new < previous * MIN_RATIO:
        return False, f"{new} jobs is less than half of the previous {previous}"
    return True, f"{new} jobs (previous: {previous if previous is not None else 'none'})"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    ok, reason = check(count(Path(argv[0])), count(Path(argv[1])))
    print(("OK to publish: " if ok else "NOT publishing: ") + reason)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
