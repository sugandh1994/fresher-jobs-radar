Run the full pipeline locally and report the results.

1. Run `python -m pipeline.run`.
2. Read `data/run_log.json` and show me a small table: jobs fetched per source, after filter, after dedupe, final count.
3. Check that the final count is ≥ 200. If not, suggest which source or keywords to expand.
4. Pick 10 random jobs from `site/jobs.json` and show title, role, city so I can spot-check the tags.
