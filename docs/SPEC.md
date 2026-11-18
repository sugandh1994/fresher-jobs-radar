# Spec — Fresher Jobs Radar

## Goal
A public page listing 200+ current fresher jobs and internships in India, refreshed daily, searchable by keyword, role and city.

## Users
Final-year students and freshers (0–1 year experience) looking for jobs or internships in India.

## Pipeline steps
1. **Fetch** — call each approved source in docs/SOURCES.md with fresher keywords:
   `fresher, intern, internship, trainee, graduate, entry level, junior, 0-1 years`.
2. **Normalize** — map to the common Job schema in CLAUDE.md. Strip HTML from descriptions.
3. **Filter** — keep only jobs that are:
   - in India or "Remote – India" (check location text),
   - fresher-level (keyword in title/description, OR experience ≤ 1 year),
     refined 2026-11-17 to stop false matches:
     - **Title:** any fresher word counts (intern, trainee, fresher, graduate, junior/jr, new grad, campus, apprentice, early career, entry level).
     - **Description:** only clear wording counts — "freshers", "fresh/recent graduates", "0–N years", "entry-level role",
       "early-career", "no experience required", a singular "intern"/"trainee" (this job), "junior X" (not "junior engineers/team").
       Bare "graduate" (a degree), "campus" (an office), "guidance to entry level engineers" don't count.
     - **Ruled out:** "freshers need not apply"; senior titles; a minimum of 1+ years ("1–3 years", "minimum 1 year")
       unless the post also says freshers are welcome.
   - posted in the last 30 days (if a date is available). **Exception:** Greenhouse and Lever
     feeds only contain jobs that are still open, so the 30-day rule is skipped for them (decided 2026-11-17).
4. **Dedupe** — see rules below.
5. **Tag** — LLM assigns `role` and `city` (see Tagging).
5b. **Scope** — the site covers only the roles in docs/TAXONOMY.md. Jobs the LLM tags role `"Other"`
   (e.g. Radiologist, Electrician, Sewing Trainee) are hidden (decided 2026-11-17). Untagged jobs and
   error fallbacks are kept. The ≥90% "not Other" quality figure is measured *before* this step.
6. **Write** — `site/jobs.json` sorted newest first, plus `updated_at` timestamp; `data/run_log.json` with counts per step and per source.

## Dedupe rules
1. Exact: same canonical URL (strip `utm_*`, tracking params, trailing slash) → duplicate.
2. Fingerprint: lowercase + remove punctuation/extra spaces + remove words like "pvt ltd", "limited", "inc" →
   `fingerprint = hash(title | company | city)` → duplicate.
3. Fuzzy: same company AND title similarity ≥ 90 (rapidfuzz `token_sort_ratio`) AND same city → duplicate.
   Not applied when the titles have different level words (New, Trainee, Intern, Senior, I/II…) —
   e.g. Accenture "New Associate" ≠ "Associate" (decided 2026-11-17).
When duplicates are found, keep the one with the longest description and most recent date; record all source names in `sources: []`.

## Tagging (LLM)
- Model: a small, fast Claude model (`claude-haiku-5-5`), effort `low`. (Haiku 5.5 rejects a
  `temperature` setting, so consistency comes from low effort + a JSON schema whose role/city
  fields only allow the taxonomy values.)
- Batch 20 jobs per request. Send only: id, title, company, location_raw, first 600 chars of description.
- Ask for strict JSON: `[{"id": "...", "role": "...", "city": "..."}]`.
- Role and city must be chosen from docs/TAXONOMY.md. Unknown → `"Other"`. Remote → city `"Remote"`. Multiple cities → first listed.
- Validate the output; if JSON is invalid, retry once, then fall back to `"Other"` (city: `"Other India"`).
  Fallbacks are not cached. If the API itself can't be used (no credit, bad key), stop calling it and
  leave the remaining jobs untagged so the next run tags them.
- Cache by job fingerprint in `data/tag_cache.json`.

## Web page
- Header: title, short description, "Last updated: <date>", total count.
- Controls: search box (title/company/description), Role dropdown, City dropdown, "Internships only" toggle, clear filters.
- Results: cards with title, company, city chip, role chip, posted date, source, "Apply" link (opens original post in new tab).
- Shows result count; empty state message when nothing matches.
- Mobile-first, accessible (labels, keyboard focus, contrast AA).
- Footer: list of sources + note that posts link to the original site.

## Automation
- GitHub Actions: `schedule: cron "30 0 * * *"` (06:00 IST) + `workflow_dispatch`.
- Steps: checkout → setup Python → install → run pipeline → commit `site/jobs.json` + `data/*.json` if changed → deploy `site/` to GitHub Pages.
- Secrets: `ANTHROPIC_API_KEY`, plus any source API keys.

## Out of scope (v1)
User accounts, saved jobs, email alerts, a database.
