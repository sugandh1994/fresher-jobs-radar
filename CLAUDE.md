# Fresher Jobs Radar — project memory for Claude Code

## What this project is
A live web tool that, once a day and with no manual work:
1. Fetches 200+ real fresher / internship job posts in India from **approved public sources only**.
2. Removes duplicates.
3. Uses an LLM to tag each post with a **role** and a **city**.
4. Publishes a searchable static web page.

Full requirements: @docs/SPEC.md
Allowed sources and their terms: @docs/SOURCES.md
Allowed role/city tags: @docs/TAXONOMY.md

## Tech stack (keep it simple — do not add frameworks)
- Python 3.11+ for the pipeline (`requests`, `rapidfuzz`, `anthropic`, `python-dotenv`).
- Plain HTML + CSS + vanilla JS for the page (no React, no build step).
- Data stored as JSON files in `data/` (no database).
- Daily automation: GitHub Actions cron → commits `site/jobs.json` → GitHub Pages.

## Folder layout
```
pipeline/
  sources/        one file per source, each exposes fetch() -> list[RawJob]
    companies.json  Greenhouse/Lever company slugs (keep in sync with docs/SOURCES.md)
  models.py       RawJob + Job data shapes
  http_client.py  polite GET helper (User-Agent, 15s timeout, 1s/host delay, no keys in errors)
  normalize.py    convert every source into the common Job schema
  filters.py      keep India + fresher-level + last 30 days
  dedupe.py       remove duplicates
  tagger.py       LLM tagging with cache
  run.py          entry point: fetch → normalize → filter → dedupe → tag → write
  guard.py        publish safety check used by the daily workflow
  logos.py        company logo lookup; `python -m pipeline.logos --download` fetches new ones once
  company_logos.json  well-known employers whose real logo we show (exact name match only)
site/
  index.html, app.js, styles.css, jobs.json (generated)
  dropdown.js     accessible custom menu for the City dropdown (WAI-ARIA select-only combobox)
  assets/         hero video + poster, logos/ (downloaded company logos)
data/
  tag_cache.json  LLM results keyed by job fingerprint (generated, committed)
  run_log.json    counts per source from last run (generated)
tests/
.github/workflows/daily.yml
```

## Common Job schema (every source must map to this)
`id, title, company, location_raw, url, source, posted_at (ISO date), description (plain text, max 2000 chars), role, city, experience_hint`

`site/jobs.json` also carries a display-only `city_from_location` (taxonomy city read from the location text, no LLM) so city filters/counts work before tagging; the page prefers the LLM `city` when present.

## Rules — always follow
- **Never scrape** a site whose Terms of Service or robots.txt forbid it. Only use sources listed as ✅ in docs/SOURCES.md. If you want to add a source, add it to SOURCES.md with the reason first and ask me.
- Use a clear User-Agent, timeouts (15s), and ≥1s delay between requests to the same host.
- One failing source must **not** crash the run — log it and continue.
- Never print or commit API keys. Keys come from `.env` locally and GitHub Secrets in CI.
- LLM tags must come from the fixed lists in docs/TAXONOMY.md. Anything else → `"Other"`.
- Site scope = TAXONOMY.md roles. Jobs the LLM tags role `"Other"` are hidden from the site
  (untagged jobs and error fallbacks are not). To include a new kind of job, add a role to TAXONOMY.md.
- Cache LLM results; never re-tag a job that is already in `data/tag_cache.json`.
- Keep the run under ₹50/day in LLM cost (use the small/fast model, batch 20 jobs per call).
- The page must work with JavaScript loading only `jobs.json` — no backend.
- Saved / applied jobs and last-visit date are kept only in the visitor's browser (localStorage). No accounts.
- After changing `site/styles.css` or `site/app.js`, bump the `?v=` number on their links in
  `site/index.html` so browsers don't keep the old copy.
- Every Adzuna job card must show a "Jobs by Adzuna" badge (at least 116×23 px) linking to https://www.adzuna.in — this is required by Adzuna's terms.
- Keep the site non-commercial (no ads, no paid features) — Adzuna's free terms depend on it.

## Commands
- Install: `pip install -r requirements.txt`
- Run pipeline locally: `python -m pipeline.run`
- Run without LLM (for quick tests): `python -m pipeline.run --no-llm`
- Tests: `pytest -q`
- Preview site: `python -m http.server -d site 8000`

## Definition of done
- `site/jobs.json` has ≥200 unique jobs after a run.
- ≥90% of jobs have a role and city that are not "Other" (spot-check 20 by hand) — measured
  before out-of-scope jobs are hidden (`quality` in data/run_log.json).
- Page supports text search + Role filter + City filter + "Last updated" date.
- GitHub Action runs daily and on manual trigger, and the live URL updates.
- README explains sources, dedupe logic, tagging prompt, and how to run.

## Working style
- Build in small steps; run and test after each step before moving on.
- Explain changes in plain language — I'm a product designer, not a backend engineer.
- Update this file if we change a rule or the structure.
