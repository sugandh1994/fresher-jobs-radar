# Sources register

Only sources marked ✅ may be used by the pipeline. Before adding a source:
read its Terms of Service, API terms and robots.txt, and write down what you checked and when.

| Status | Source | How we access it | Key needed | Terms checked (date + note) |
|---|---|---|---|---|
| ✅ | Adzuna (India) | Official Jobs API, country `in` | Yes (free app_id + app_key) | 2026-11-17 — developer.adzuna.com/docs/terms_of_service. **Use:** publishing Adzuna listings is a permitted use; OK for this non-commercial project. If the site ever earns money or generates leads → needs a paid licence. **Display:** allowed. **Attribution:** every Adzuna job card must show a "Jobs by Adzuna" label/logo, at least 116×23 px, linking to adzuna.in. **Limits:** not published; see your Adzuna dashboard (free key is for evaluation) — keep to 1 run/day. **Storing:** no rule; but all Adzuna data must be removed from the site if access ends. **Don't:** contact employers about listings, resell data, or make multiple accounts. |
| ⏳ | Jooble | Official REST API | Yes (free key, by email) | 2026-11-17 — jooble.org/api/about says the API lets you "post the results on your website in your own design" → display allowed. Jooble's general site terms ban bots and republishing copied site content — so use the API only, never scrape jooble.org. **Still to check:** any API terms/attribution/limits sent with the key email. Change to ✅ after that. |
| ✅ | Greenhouse job boards | Public Job Board API: `boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true` | No | 2026-11-17 — docs.greenhouse.io/job-board.html. GET endpoints are public, no auth (only posting applications needs a key). **Display:** these are jobs companies chose to publish. **Attribution:** link each card to the job's `absolute_url`. **Limits:** none published — call each board once per run. **Storing:** keep only open jobs; drop any that disappear from the feed. |
| ✅ | Lever job boards | Public Postings API: `api.lever.co/v0/postings/{company}?mode=json` (EU: `api.eu.lever.co`) | No | 2026-11-17 — Lever's public Postings API is read-only and unauthenticated (separate from the private Data API). **Attribution:** link each card to the posting's `hostedUrl`. **Limits:** none published — once per board per run. Some companies switch the feed off; skip those. |
| ⏳ | Government / PSU job RSS feeds | Public RSS | No | Not checked yet — pick specific feeds first, then check each site's terms + robots.txt. |
| ❌ | LinkedIn | — | — | Terms prohibit scraping. Do not use. |
| ❌ | Naukri | — | — | Terms prohibit scraping. Do not use. |
| ❌ | Indeed (scraping) | — | — | Terms prohibit scraping. Do not use. |

## Company list for Greenhouse / Lever
Add Indian or India-hiring companies that use these boards. Verify each slug returns jobs.
Find the slug in the careers URL: `boards.greenhouse.io/<slug>`, `job-boards.greenhouse.io/<slug>`, or `jobs.lever.co/<slug>`.
The pipeline reads the live list from `pipeline/sources/companies.json` — edit that file to add/remove a company, and update the table below.

Verified 2026-11-17: each slug returned jobs from the public API, with open roles located in India.
"Fresher" = India + fresher-level by our filter (before the 30-day rule).

| ATS | Slug | Company | Total jobs | In India | Fresher (India) |
|---|---|---|---|---|---|
| Greenhouse | `groww` | Groww | 9 | 9 | 0 |
| Greenhouse | `druva` | Druva | 28 | 11 | 0 |
| Greenhouse | `inmobi` | InMobi | 75 | 40 | 0 |
| Greenhouse | `rubrik` | Rubrik | 188 | 36 | 4 |
| Greenhouse | `databricks` | Databricks | 891 | 83 | 0 |
| Greenhouse | `stripe` | Stripe | 794 | 44 | 3 |
| Greenhouse | `mongodb` | MongoDB | 400 | 75 | 1 |
| Greenhouse | `okta` | Okta | 358 | 103 | 0 |
| Greenhouse | `twilio` | Twilio | 115 | 13 | 0 |
| Greenhouse | `elastic` | Elastic | 384 | 17 | 0 |
| Greenhouse | `airbnb` | Airbnb | 205 | 12 | 1 |
| Greenhouse | `hackerrank` | HackerRank | 32 | 18 | 2 |
| Greenhouse | `highradius` | HighRadius | 68 | 44 | 2 |
| Greenhouse | `sigmoid` | Sigmoid | 42 | 37 | 1 |
| Lever | `meesho` | Meesho | 47 | 47 | 0 |
| Lever | `cred` | CRED | 15 | 15 | 0 |
| Lever | `zeta` | Zeta | 30 | 25 | 0 |
| Lever | `mindtickle` | Mindtickle | 20 | 17 | 0 |
| Lever | `fampay` | FamPay | 15 | 15 | 2 |
| Lever | `paytm` | Paytm | 200 | 193 | 17 |

Checked but not added (2026-11-17): `cloudflare`, `slice`, `figma`, `coinbase` (Greenhouse — 0–10 India jobs); `gitlab` (34 India jobs but mostly remote/global, 0 fresher — kept list at 20);
`digit` (Greenhouse), `freshworks` (Lever) — board exists but empty. ~75 other Indian company slugs
(razorpay, swiggy, zomato, cred on Greenhouse, etc.) returned 404 on both APIs — they use other systems.

## Attribution
- Every job card links to the original post.
- Adzuna cards show the "Jobs by Adzuna" badge (≥116×23 px) linking to adzuna.in.
- The footer names each source.
