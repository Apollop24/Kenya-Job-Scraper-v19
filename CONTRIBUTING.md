# Contributing

This started as a personal tool, so the process is intentionally lightweight.

## Getting set up

```bash
git clone <your-repo-url>
cd kenya-job-scraper
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

You'll also need Google Chrome installed locally — Selenium resolves a
matching chromedriver automatically the first time you run the scraper.

## Making changes

- Keep new fields flowing through `enrich_job_data()` rather than editing
  each site-specific scraper, so every source benefits automatically.
- If you change a field the dashboard depends on (e.g. a KPI or chart
  input), update the corresponding `__TOKEN__` replacement in
  `generate_dashboard()` **and** its usage in `DASHBOARD_TEMPLATE`.
- Run a quick smoke test before opening a PR:
  ```bash
  python -m py_compile kenya_job_scraper_v22.py dashboard_server.py
  ```
- If you touch the dashboard HTML/CSS/JS, open the generated
  `jobs_dashboard_*.html` in a browser and check both the light and dark
  themes (the toggle is in the top-right corner).

## Reporting issues

If a site's markup changes and scraping breaks, please include:
- Which source (MyJobMag / BrighterMonday / Fuzu / CareerPoint / MyJobsInKenya)
- The relevant lines from the `job_scraper_*.log` file
- Whether it fails immediately or partway through (helps narrow down which
  selector broke)
