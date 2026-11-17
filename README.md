# Fresher Jobs Radar

A daily-refreshing, searchable list of fresher jobs and internships in India.

**Live page:** _add link after deploy_

## How it works
1. **Fetch** from approved public sources (see `docs/SOURCES.md`).
2. **Filter** to India + fresher-level + last 30 days.
3. **Dedupe** by canonical URL, normalized fingerprint, and fuzzy title match.
4. **Tag** role and city with an LLM, limited to fixed lists (`docs/TAXONOMY.md`).
5. **Publish** `site/jobs.json` + a static search page via GitHub Pages, every day at 06:00 IST.

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env   # add your keys
python -m pipeline.run
python -m http.server -d site 8000
```

## Sources and terms
_Summarize docs/SOURCES.md here._

## Tagging prompt
_Paste the final prompt here._

## Results
_Counts from the latest run, accuracy of a 20-job spot-check._
