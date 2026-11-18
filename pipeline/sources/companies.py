"""Loads the Greenhouse / Lever company list from companies.json."""
from __future__ import annotations

import json
from pathlib import Path

COMPANIES_FILE = Path(__file__).with_name("companies.json")


def load_companies(source: str) -> dict[str, str]:
    """Return {slug: display name} for 'greenhouse' or 'lever'."""
    data = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    return data.get(source, {})
