# Fresher Jobs Radar

A daily-refreshing, searchable list of fresher jobs and internships in India — collected only from approved public sources, cleaned up, de-duplicated, labelled by role and city with an LLM, and published as a static web page.

**Live page:** https://sugandh1994.github.io/fresher-jobs-radar/

Free and non-commercial: no ads, no sign-up, no backend. Every job links to the original post.

---

## How it works

```
 Adzuna API ─┐
 Greenhouse ─┼─► normalize ─► filter ─► dedupe ─► tag (LLM) ─► scope ─► site/jobs.json ─► GitHub Pages
 Lever ──────┘                                    + cache
```

| Step | What happens | Code |
|---|---|---|
| **1. Fetch** | Call each approved source with fresher keywords (`fresher`, `intern`, `internship`, `trainee`, `graduate`, `entry level`, `junior`, `0-1 years`). One failing source is logged and skipped — it never stops the run. | `pipeline/sources/` |
| **2. Normalize** | Convert every source into one common job shape (title, company, location, link, date, plain-text description ≤ 2,000 chars). | `pipeline/normalize.py` |
| **3. Filter** | Keep jobs that are in India, fresher-level, and posted in the last 30 days. | `pipeline/filters.py` |
| **4. Dedupe** | Merge the same job posted twice or on two sources. | `pipeline/dedupe.py` |
| **5. Tag** | An LLM picks one **role** and one **city** per job from fixed lists. Results are cached so a job is only ever tagged once. | `pipeline/tagger.py` |
| **6. Scope** | Jobs the LLM tags role `Other` (e.g. Radiologist, Electrician) are hidden — the site covers the roles in `docs/TAXONOMY.md`. | `pipeline/run.py` |
| **7. Publish** | Write `site/jobs.json` (newest first) and `data/run_log.json` (counts per step and source); a GitHub Action deploys the page. | `.github/workflows/daily.yml` |

---

## Sources and terms

Only sources marked ✅ in [`docs/SOURCES.md`](docs/SOURCES.md) are used. Each was checked against its terms of service on 2026-11-17. LinkedIn, Naukri and Indeed are **not** used — their terms forbid scraping.

| Source | Access | What the terms require |
|---|---|---|
| **Adzuna India** | Official Jobs API (free key) | Allowed for non-commercial use. Every Adzuna job card shows a **"Jobs by Adzuna"** badge (≥ 116×23 px) linking to adzuna.in. If the site ever makes money it needs a paid licence. |
| **Greenhouse** | Public Job Board API, 14 companies | Read-only, no key. Each card links to the company's own job page. |
| **Lever** | Public Postings API, 6 companies | Read-only, no key. Each card links to the company's own job page. |
| Jooble | Official API | ⏳ Waiting on API key terms — not used yet. |

Companies on Greenhouse: Groww, Druva, InMobi, Rubrik, Databricks, Stripe, MongoDB, Okta, Twilio, Elastic, Airbnb, HackerRank, HighRadius, Sigmoid.
Companies on Lever: Meesho, CRED, Zeta, Mindtickle, FamPay, Paytm.
(Full table with job counts: `docs/SOURCES.md`. Edit the list in `pipeline/sources/companies.json`.)

Good-citizen rules for every request: a clear User-Agent, a 15-second timeout, and at least 1 second between requests to the same site. API keys are never printed in logs or error messages.

---

## Filter rules

A job is kept only if **all three** are true:

1. **In India** — the location mentions India or an Indian city. A bare "Remote" only counts for Adzuna (whose results are India-only), so "Remote – US" from a global company is excluded.
2. **Fresher-level**
   - **Title** contains a fresher word: intern, trainee, fresher, graduate, junior/jr, new grad, campus, apprentice, early career, entry level → keep.
   - **Description** only counts with clear wording: "freshers welcome", "fresh/recent graduates", "0–1 years", "an entry-level role", "Junior X Developer", "Marketing Intern".
     Words used in other senses don't count — "Qualification: Graduate" (a degree), "Andheri Campus office", "mentor junior engineers", "guidance to entry level engineers".
   - **Ruled out:** "freshers need not apply"; senior titles (Senior, Lead, Manager, Head…); a minimum of 1+ years ("1–3 years") unless the post also says freshers are welcome.
3. **Recent** — posted in the last 30 days. Greenhouse and Lever are exempt: their feeds only list jobs that are still open.

---

## Dedupe logic

Each job is compared with the jobs already kept. It's a duplicate if **any** rule matches:

| Rule | Match when… | Example |
|---|---|---|
| **1. Same link** | The URLs are identical after removing tracking bits (`utm_*`, `gclid`, `lever-source`…), the `#fragment` and trailing `/`. | `…/jobs/123/?utm_source=x` = `…/jobs/123` |
| **2. Same fingerprint** | `title | company | city` match after lower-casing, removing punctuation and legal suffixes (Pvt, Ltd, Limited, Inc…), and mapping city aliases (Bangalore → Bengaluru, Gurgaon → Delhi NCR). | "Software Engineer – Intern, Acme Pvt Ltd, Bangalore" = "software engineer intern, ACME Limited, Bengaluru" |
| **3. Near-identical title** | Same company **and** same city **and** title similarity ≥ 90 (`rapidfuzz.token_sort_ratio`) **and** the same level words (New, Trainee, Intern, Senior, I/II…). | "BD Associate (Fresher)" ≈ "BD Associate (Freshers)" — but Accenture "New Associate" ≠ "Associate" (different grades) |

When duplicates are found, the kept job is the one with the **longest description**, it gets the **newest date** in the group, and `sources` lists **every source** it appeared on.

Dedupe runs before tagging, so the "city" here comes from a simple lookup on the location text, not from the LLM.

---

## Tagging

- **Model:** `claude-haiku-5-5` (small and fast) at `effort: low`.
- **Batches** of 20 jobs per request. Only `id`, `title`, `company`, `location_raw` and the first 600 characters of the description are sent.
- **Strict output:** the request includes a JSON schema whose `role` and `city` fields only allow values from `docs/TAXONOMY.md`, and the answer is validated again in code — anything unexpected becomes `Other` / `Other India`.
- **Retry once** for jobs missing from a bad answer, then fall back to `Other` (fallbacks aren't cached, so they're retried next run).
- **Cache:** results are stored in `data/tag_cache.json` by job fingerprint; a cached job is never sent again. Daily cost is a few paise; the first full run of ~480 jobs is estimated at ~₹2 (limit: ₹50/day).
- **Account problems** (no credit, bad key) stop the LLM calls after the first failure and leave jobs untagged — they're tagged on the next working run.
- *Note:* Haiku 5.5 doesn't accept a `temperature` setting, so consistency comes from low effort plus the fixed-value schema.

### The prompt

System prompt (generated from `docs/TAXONOMY.md` by `build_system_prompt()` in `pipeline/tagger.py`):

```text
You label fresher job and internship posts in India for a job search site.
For every job you are given, choose exactly one role and exactly one city.

Roles (pick the closest match; use "Other" only if none fit):
- Software Engineering
- Frontend / Web Development
- Data Analytics
- Data Science / ML
- UI/UX Design
- Graphic / Visual Design
- Product Management
- QA / Testing
- DevOps / Cloud
- Cybersecurity
- Marketing / Digital Marketing
- Content / Writing
- Sales / Business Development
- Customer Support
- Finance / Accounting
- HR / Recruitment
- Operations
- Consulting
- Research
- Other

Cities:
- Mumbai
- Pune
- Bengaluru
- Delhi NCR
- Hyderabad
- Chennai
- Kolkata
- Ahmedabad
- Jaipur
- Kochi
- Chandigarh
- Indore
- Coimbatore
- Remote
- Other India

City rules:
- Delhi NCR covers Delhi, New Delhi, Gurugram/Gurgaon, Noida, Faridabad, Ghaziabad.
- Remote / work from home jobs -> "Remote".
- If several cities are listed, use the first one.
- If the location only says "India", look for a city in the description; if there is none, use "Other India".
- A real Indian city not in the list -> "Other India".

Mapping notes:
- "Bangalore" → Bengaluru; "Gurgaon" → Delhi NCR; "Bombay"/"Navi Mumbai"/"Thane" → Mumbai.
- "Hybrid – Pune" → Pune.
- "Work from home", "Remote (India)" → Remote.

Return one entry per job, using the job's id exactly as given.
```

User message: `Label these jobs:` followed by a JSON array of up to 20 jobs. Expected answer: `{"tags": [{"id": "...", "role": "...", "city": "..."}]}`.

---

## The web page

Plain HTML + CSS + vanilla JavaScript in `site/` — no framework, no build step, no backend. It loads only `jobs.json`.

- A greeting banner that follows India time (**Good morning** 5 am–noon, **Good afternoon** noon–5 pm, **Good evening** otherwise, IST) over a looping background video (muted; a pause button; a still image for visitors who prefer reduced motion or use data saver) with today's numbers and a compact search box.
- A compact **daily list**: jobs grouped under Today / Yesterday / Earlier this week / Earlier.
- **Job category** list on the left with live counts, and a **City** dropdown with live counts. City counts work even before LLM tagging, using the city read from each job's location text (`city_from_location`).
- Each row starts with the **company logo** for well-known employers (65 logos, stored in the site) or a coloured **initials badge** for everyone else.
- Each row: title (tap to open the description, then **Read the full post** or **Share**), company, place, tags, **Save** (bookmark), **Apply** (opens the original post; marked **Applied ✓** afterwards), and the "Jobs by Adzuna" badge where required.
- **Saved** view, and "N new since your last visit" — remembered only in the visitor's browser (localStorage), no accounts.
- Press `/` to jump to search. Filters are kept in the URL, so a view can be shared (e.g. `?role=Data+Analytics&city=Pune`).
- The City dropdown is a custom accessible menu (`site/dropdown.js`, WAI-ARIA select-only combobox).
- Mobile-first (categories open as a bottom sheet on phones), scales up on large iMac screens, light and dark mode, labelled controls, visible keyboard focus, AA contrast, reduced-motion respected.
- Job text is always inserted as plain text, never as HTML.

---

## Daily automation

`.github/workflows/daily.yml` runs every day at **06:00 IST** (`cron: "30 0 * * *"`) and on demand (Actions → Daily refresh → Run workflow):

1. Run the tests — stop if any fail.
2. Run the pipeline (keys come from GitHub Secrets: `ANTHROPIC_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`).
3. Write a counts table to the run's summary page.
4. **Safety check** (`pipeline/guard.py`): don't publish fewer than 50 jobs or less than half of yesterday's — e.g. if Adzuna is down. The run fails, GitHub emails the owner, and the site keeps yesterday's list.
5. Commit `site/jobs.json` and `data/*.json` (including the tag cache) back to `main`.
6. Deploy `site/` to GitHub Pages.

---

## Run locally

Needs Python 3.11+.

```bash
pip install -r requirements.txt
cp .env.example .env              # add ADZUNA_APP_ID, ADZUNA_APP_KEY, ANTHROPIC_API_KEY
python -m pipeline.run            # full run
python -m http.server -d site 8000   # preview at http://localhost:8000
```

Other options:

| Command | Use it to… |
|---|---|
| `python -m pipeline.run --no-llm` | Run without new LLM calls (cached tags are still applied). |
| `python -m pipeline.run --skip-fetch` | Re-filter and re-tag the jobs already in `site/jobs.json` without calling any source (e.g. to stay within Adzuna's once-a-day limit). |
| `pytest -q` | Run the tests (62). |

---

## Results

Latest run — **2026-11-18**, GitHub Actions:

| Source | Fetched | After filter | After dedupe |
|---|---|---|---|
| Adzuna | 1,263 | 486 | 455 |
| Greenhouse | 3,574 | 10 | 10 |
| Lever | 321 | 13 | 12 |
| **Total** | **5,158** | **509** | **477** |

- **Unique jobs published:** 477 (target: ≥ 200) ✅
- **Duplicates removed:** 32
- **Tagging:** not run yet — the Anthropic API account needs credit. Jobs are published untagged until then.
- **Tag accuracy (20-job hand spot-check):** _pending — to be added after the first tagged run._ Target: ≥ 90% of jobs with a role and city that aren't "Other", measured before out-of-scope jobs are hidden (`quality` in `data/run_log.json`).

---

## Project layout

```
pipeline/
  sources/          adzuna.py, greenhouse.py, lever.py, companies.json
  models.py         RawJob + Job data shapes
  http_client.py    polite GET helper (User-Agent, timeout, per-host delay)
  normalize.py      every source → common Job schema
  filters.py        India + fresher + recent
  dedupe.py         URL / fingerprint / fuzzy duplicate removal
  tagger.py         LLM role + city tagging with cache
  guard.py          publish safety check
  run.py            entry point
site/               index.html, styles.css, app.js, dropdown.js, jobs.json (generated)
data/               tag_cache.json, run_log.json (generated)
tests/              pytest suite
docs/               SPEC.md, SOURCES.md, TAXONOMY.md
.github/workflows/  daily.yml
```
