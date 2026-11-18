"""Company logos for well-known employers.

- pipeline/company_logos.json lists companies (official website + the exact names
  they appear under). Only exact name matches get a logo — no guessing.
- `python -m pipeline.logos --download` fetches each missing logo ONCE into
  site/assets/logos/<domain>.png (via Google's public favicon service, 128px).
  Blurry or missing icons (smaller than 64px) are rejected, so those companies
  fall back to initials on the page.
- The daily pipeline only looks up files that already exist; it never downloads.
  Visitors load logos from our own site, never from a third party.
"""
from __future__ import annotations

import argparse
import json
import struct
from functools import lru_cache
from pathlib import Path

from pipeline.dedupe import clean_company
from pipeline.http_client import SourceError, get_bytes

ROOT = Path(__file__).resolve().parent.parent
MAPPING_FILE = Path(__file__).with_name("company_logos.json")
LOGO_DIR = ROOT / "site" / "assets" / "logos"
FAVICON_URL = "https://www.google.com/s2/favicons"
MIN_SIZE = 48   # px; shown at 36px, so smaller icons would look blurry — those get initials


def png_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a PNG, or None if it isn't a PNG."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def file_name(domain: str) -> str:
    return domain.replace("/", "_") + ".png"


@lru_cache(maxsize=1)
def _name_to_domain() -> dict[str, str]:
    data = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    out = {}
    for entry in data["companies"]:
        for name in entry["names"]:
            out[clean_company(name)] = entry["domain"]
    return out


def logo_for(company: str, logo_dir: Path = LOGO_DIR) -> str | None:
    """Site-relative path of the company's logo, or None (page shows initials)."""
    domain = _name_to_domain().get(clean_company(company or ""))
    if not domain:
        return None
    if not (logo_dir / file_name(domain)).exists():
        return None
    return f"assets/logos/{file_name(domain)}"


def download_missing(logo_dir: Path = LOGO_DIR) -> dict:
    logo_dir.mkdir(parents=True, exist_ok=True)
    domains = sorted(set(_name_to_domain().values()))
    report = {"downloaded": [], "already_had": [], "rejected": []}
    for domain in domains:
        target = logo_dir / file_name(domain)
        if target.exists():
            report["already_had"].append(domain)
            continue
        try:
            data = get_bytes(FAVICON_URL, {"domain": domain, "sz": 128})
        except SourceError as exc:
            report["rejected"].append(f"{domain} ({exc})")
            continue
        size = png_size(data)
        if not size or min(size) < MIN_SIZE:
            report["rejected"].append(f"{domain} (icon too small or not a PNG: {size})")
            continue
        target.write_bytes(data)
        report["downloaded"].append(f"{domain} {size[0]}x{size[1]}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download company logos listed in company_logos.json")
    parser.add_argument("--download", action="store_true", help="fetch logos that aren't saved yet")
    args = parser.parse_args()
    if not args.download:
        parser.print_help()
        raise SystemExit(0)
    r = download_missing()
    print(f"downloaded {len(r['downloaded'])}, already had {len(r['already_had'])}, rejected {len(r['rejected'])}")
    for line in r["rejected"]:
        print("  rejected:", line)
