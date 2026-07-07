# Kenya Job Scraper

A scraper + analytics dashboard for data, analytics, and BI job listings
across five Kenyan job boards — **MyJobMag, BrighterMonday, Fuzu,
CareerPoint Kenya, and MyJobsInKenya.**

> Add a screenshot of your dashboard here once you've generated one, e.g.
> `![dashboard](docs/screenshot.png)`

## Features

- Scrapes 5 sources for 12+ configurable keywords (data analyst, data
  scientist, statistician, BI, M&E, etc.)
- Skips duplicate/expired/stale listings automatically, with a local cache
  so re-runs don't redo work
- Enriches every listing with a normalized city, a canonical role bucket, a
  0–100 completeness ("quality") score, and freshness in days
- Reads every daily snapshot ever saved to build real trend/history charts
  — no database required
- Interactive analytics dashboard: KPI cards, hiring trend line chart, top
  job titles, jobs by day of week, source quality comparison, a 5-week
  calendar heatmap, and a filterable/sortable results table
- Light/dark theme toggle
- Export results to CSV, Excel, or PDF (print)
- Optional one-click "Run scraper" button (via `dashboard_server.py`) and
  an optional daily auto-refresh schedule

## Project structure

```
.
├── kenya_job_scraper_v22.py   # the scraper + dashboard generator
├── dashboard_server.py        # local server that powers the "Run scraper" button
├── requirements.txt
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── .gitignore
```

Generated at runtime (git-ignored, not committed — see `.gitignore`):

```
kenya_jobs_YYYY-MM-DD.json     # today's scraped jobs
jobs_YYYY-MM-DD.csv            # CSV export of today's run
jobs_dashboard_YYYY-MM-DD.html # the dashboard
cache_YYYY-MM-DD.pkl           # dedupe cache
job_scraper_YYYYMMDD_HHMMSS.log
```

## Requirements

- Python 3.9+
- Google Chrome (Selenium resolves a matching chromedriver automatically)
- Internet connection (for scraping, and for the dashboard's Chart.js /
  Excel-export CDN scripts)

## Installation

```bash
git clone <your-repo-url>
cd kenya-job-scraper
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

**Recommended: run the dashboard server.** This is the only command you
need day-to-day — it wraps the scraper and gives you the dashboard's
one-click "Run scraper" button:

```bash
python dashboard_server.py
```

It prints a local URL (default `http://localhost:8877`) — open that in
your browser. Click **Run scraper** to kick off a fresh scrape; the page
reloads itself with new data when it's done.

Optional flags:

```bash
python dashboard_server.py --path "/path/to/data" --port 8877 --schedule --schedule-hours 24
```

| Flag | Purpose |
|---|---|
| `--path` | Folder to read/write scraped data (defaults to a first-run prompt) |
| `--port` | Port to serve the dashboard on |
| `--schedule` | Also auto-run the scraper on a fixed interval |
| `--schedule-hours` | Interval in hours for `--schedule` (default 24) |

**Alternative: run the scraper directly**, without the server or the
"Run scraper" button — useful for a one-off run from a terminal or a cron
job/scheduled task:

```bash
python kenya_job_scraper_v22.py
```

Then open the generated `jobs_dashboard_*.html` file directly in a browser
(the button will just explain it needs `dashboard_server.py` to work).

## Configuration

Keywords, sources, and the "how many days old is too old" cutoff are
defined near the top of `kenya_job_scraper_v22.py`. The first run asks
where to save data; subsequent runs reuse the same path automatically.

## Design system

The dashboard follows a single green accent (`#14A800`) across both light
and dark themes, with neutral grays for everything else and reserved
colors for status (`#F59E0B` warning, `#DC2626` error, `#2563EB` info).
Charts use varying shades of the same green rather than an unrelated
rainbow palette, for a consistent, professional look in both themes.

## License

MIT — see [LICENSE](LICENSE). Change this if you'd prefer a different
license.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
