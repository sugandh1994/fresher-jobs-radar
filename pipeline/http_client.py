"""Polite HTTP helper shared by all sources.

Rules from CLAUDE.md: clear User-Agent, 15s timeout, >=1s between requests to
the same host. Error messages never include the request URL, because API keys
travel in the query string.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

USER_AGENT = "FresherJobsRadar/0.1 (non-commercial fresher job listings for India)"
TIMEOUT_SECONDS = 15
MIN_DELAY_SECONDS = 1.0

_last_request_at: dict[str, float] = {}
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


class SourceError(Exception):
    """A source failed. The message is safe to log (no secrets)."""


def get_json(url: str, params: dict | None = None) -> dict:
    host = urlparse(url).netloc
    wait = MIN_DELAY_SECONDS - (time.monotonic() - _last_request_at.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    try:
        resp = _session.get(url, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # Don't include str(exc): it can contain the full URL with keys.
        raise SourceError(f"network error talking to {host}: {type(exc).__name__}") from None
    finally:
        _last_request_at[host] = time.monotonic()

    if resp.status_code != 200:
        raise SourceError(f"{host} returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise SourceError(f"{host} returned something that isn't JSON") from None
