# Kenya Data Jobs: Scraper and Analytics Dashboard

[![Python](https://img.shields.io/badge/Python-3.9%2B-14A800.svg)](https://www.python.org/)
[![Selenium](https://img.shields.io/badge/Selenium-4.x-14A800.svg)](https://www.selenium.dev/)
[![Flask](https://img.shields.io/badge/Flask-3.x-14A800.svg)](https://flask.palletsprojects.com/)
[![Chart.js](https://img.shields.io/badge/Chart.js-4.x-14A800.svg)](https://www.chartjs.org/)
[![Pandas](https://img.shields.io/badge/Pandas-2.x-14A800.svg)](https://pandas.pydata.org/)
[![License](https://img.shields.io/badge/License-MIT-14A800.svg)](LICENSE)

> **A five-source web scraper and analytics dashboard for tracking Data, Analytics, and Business Intelligence job postings across Kenya's leading job boards, with automatic historical trend tracking, listing quality scoring, and a one-click local refresh workflow.**

---

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [What This Project Does](#what-this-project-does)
- [Screenshots](#screenshots)
- [Repository Structure](#repository-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Methodology](#methodology)
- [Output](#output)
- [Interpreting the Dashboard](#interpreting-the-dashboard)
- [Design System](#design-system)
- [Limitations and Known Issues](#limitations-and-known-issues)
- [Roadmap](#roadmap)
- [Data Sources](#data-sources)
- [References](#references)
- [License](#license)
- [Contributing](#contributing)

---

## Overview

This project is a Python-based web scraper paired with a self-generating,
interactive HTML analytics dashboard. It monitors five Kenyan job boards for
listings relevant to data, analytics, statistics, and business intelligence
roles, then produces a browser-based dashboard summarizing what it finds:
headline metrics, hiring trends over time, breakdowns by title, location and
source, and a filterable, exportable results table.

The scraper and the dashboard are the same codebase — every run both
collects new listings and regenerates the dashboard from the full history of
everything collected so far.

## Problem Statement

Job seekers targeting data/analytics/BI roles in Kenya do not have a single
place to look. Relevant postings are spread across at least five separate
job boards, each with a different layout, posting cadence, and level of
listing completeness (some list a clear deadline and qualification, others
omit most of that). Manually checking all five sources daily, comparing
freshness, and tracking which boards tend to yield better-quality listings
is repetitive and easy to fall behind on.

This project automates that monitoring and adds a layer of structure
(deduplication, completeness scoring, historical trend tracking) that none
of the individual job boards provide on their own.

## What This Project Does

- Scrapes five job boards for a configurable list of role-related keywords
- Filters out irrelevant, expired, or already-seen listings using keyword
  matching and a local cache
- Normalizes each listing's location into a city, buckets free-text titles
  into a canonical role (for example, "JUNIOR DATA ANALYST" and "Senior
  Data Analyst" both become "Data Analyst")
- Scores each listing's completeness (date posted, expiry, qualification,
  experience, location) on a 0-100 scale
- Aggregates every daily snapshot ever saved into historical trend data
- Generates a self-contained HTML dashboard: KPI summary, hiring trend
  chart, title/day-of-week/source/location breakdowns, a source quality
  comparison, a calendar heatmap, and a filterable results table
- Exports results to CSV, Excel, or PDF (via print) directly from the
  dashboard
- Optionally re-runs itself on a schedule, and can be triggered from the
  dashboard itself via a small local server, without a terminal

## Screenshots

Screenshots are not included in this repository by default. Replace the
placeholder paths below with your own images (same filenames, saved under
`docs/screenshots/`), or update the paths to match whatever you use.

```
docs/screenshots/dashboard-overview.png   KPI cards and hiring trend chart
docs/screenshots/dashboard-charts.png     Top titles, day of week, source, locations
docs/screenshots/dashboard-table.png      Source quality, calendar heatmap, filters, results table
```

Example embed once added:

```markdown
![Dashboard overview](docs/screenshots/dashboard-overview.png)
![Dashboard charts](docs/screenshots/dashboard-charts.png)
![Dashboard table and filters](docs/screenshots/dashboard-table.png)
```

## Repository Structure

```
.
├── kenya_job_scraper_v22.py   Scraper + dashboard generator (main script)
├── dashboard_server.py        Local server powering the "Run scraper" button
├── run_dashboard.bat          Windows one-click launcher (no terminal needed)
├── run_dashboard.command      macOS/Linux one-click launcher
├── docs/
│   └── screenshots/           Images referenced in this README (add your own)
├── requirements.txt           Python dependencies
├── CHANGELOG.md                Version history
├── CONTRIBUTING.md             Setup notes and conventions for contributors
├── LICENSE                     MIT license
└── .gitignore                  Excludes generated data files from version control
```

Files produced at runtime (git-ignored, not committed):

```
kenya_jobs_YYYY-MM-DD.json      Raw scraped data for a given day
jobs_YYYY-MM-DD.csv             CSV export of that day's run
jobs_dashboard_YYYY-MM-DD.html  The generated dashboard
cache_YYYY-MM-DD.pkl            Deduplication cache
job_scraper_YYYYMMDD_HHMMSS.log Run log
```

## Requirements

- Python 3.9 or later
- Google Chrome installed locally (Selenium resolves a matching chromedriver
  automatically; no separate driver download is required)
- An internet connection, both for scraping and for the dashboard's
  charting/export libraries, which load from a CDN

Python packages (see `requirements.txt`):

```
selenium>=4.15
pandas>=2.0
flask>=3.0
```

## Installation

### Non-technical setup

1. Install Python from [python.org/downloads](https://www.python.org/downloads/).
   During installation, enable the option to add Python to PATH.
2. Download this repository's files into a single folder.
3. Double-click `run_dashboard.bat` (Windows) or `run_dashboard.command`
   (macOS/Linux — right-click and choose Open the first time).

The launcher installs the required packages automatically on first run,
starts the local server, and opens the dashboard in your default browser.
No terminal or command-line interaction is required after the initial
Python installation.

### Developer setup

```bash
git clone <repository-url>
cd kenya-data-jobs
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

**Recommended — run the local dashboard server:**

```bash
python dashboard_server.py
```

This prints a local URL (default `http://localhost:8877`), opens it
automatically in your browser, and enables the dashboard's "Run scraper"
button, which re-scrapes all five sources in the background and reloads
the page with fresh data when finished.

Optional arguments:

| Argument | Description |
|---|---|
| `--path <folder>` | Folder to read and write scraped data (prompted on first run if omitted) |
| `--port <number>` | Port to serve the dashboard on |
| `--schedule` | Automatically re-run the scraper on a recurring interval |
| `--schedule-hours <number>` | Interval in hours for `--schedule` (default: 24) |

**Alternative — run the scraper directly**, without the server or dashboard
button (for example, from a scheduled task or cron job):

```bash
python kenya_job_scraper_v22.py
```

This produces the JSON/CSV/HTML output files listed under Repository
Structure. Open the generated `jobs_dashboard_*.html` file directly in a
browser afterward.

## Methodology

**Scraping.** Each of the five sources is scraped using Selenium WebDriver,
searching a configurable list of keywords (for example, "data analyst",
"statistician", "business intelligence") per source. Each site has its own
extraction routine, since page structures differ, but all five converge on
a common job record schema (title, link, posting date, expiry date,
qualification, experience, location, source).

**Relevance filtering.** A listing is kept only if its title or description
matches at least one entry in a shared keyword list, which also covers
common tools (SQL, Python, Power BI, Tableau) and adjacent skill terms, in
addition to role titles.

**Deduplication and freshness.** A local cache keyed by listing URL prevents
re-processing jobs already seen in a prior run. Scraping for a given
keyword on a given source stops once a listing older than a configurable
age threshold or an expired listing is encountered, since job boards
typically list postings in reverse-chronological order.

**Enrichment.** Every saved record is passed through a single enrichment
step that adds: a normalized city (parsed from the raw location string), a
canonical title bucket (mapping free-text titles to one of several fixed
role categories), a completeness/quality score (a 0-100 score based on how
many of five expected fields were successfully captured), and freshness in
days relative to the run date. This runs once, centrally, regardless of
which source the record came from.

**Historical aggregation.** Rather than persisting to a database, the
dashboard generator re-reads every daily JSON snapshot present in the data
folder at generation time, de-duplicates by listing URL across all of them,
and uses that combined dataset to compute trend and history-based metrics.
Same-run metrics (for example, the results table itself) use only the
current run's data.

## Output

Each run produces:

- A dated JSON file containing the full structured record for every job
  saved that day
- A dated CSV export of the same data
- A dated HTML dashboard, self-contained aside from a small number of
  charting/export libraries loaded from a CDN

The dashboard itself is organized into:

- Six summary KPI cards
- A hiring trend line chart (jobs scraped per day, last 30 days of history)
- A top job titles chart and a jobs-by-day-of-week chart
- A jobs-by-source chart and a top-locations chart, scoped to the current run
- A source quality comparison chart
- A five-week calendar heatmap
- A filterable, sortable results table with CSV, Excel, and print/PDF export

## Interpreting the Dashboard

- **Total Jobs (all-time)** counts every unique listing found across every
  saved daily snapshot in the data folder, not just the current run.
- **New Today** and **New This Week** are based on the date a listing was
  first scraped, not its original posting date.
- **Avg. Listing Quality** is a structural completeness score, not a
  judgment of the job itself: a 100 means the listing had a date posted,
  an expiry date, a specific location, a qualification, and an experience
  requirement; a low score means several of those fields were missing on
  the source site.
- **Source Quality** compares job boards by their average completeness
  score, which can help identify when a site's markup has changed (a sharp
  drop for one source, with others unaffected, often indicates that).
- The **Hiring Trend** and **Calendar Heatmap** become more informative the
  more days of history exist in the data folder; on a single day's data,
  both will show only one data point.
- The results table always reflects the current run, while the KPI cards
  and trend-based charts reflect the full history on disk.

## Design System

The dashboard uses a single accent color across both a light and a dark
theme, with a toggle to switch between them.

| Token | Hex | Usage |
|---|---|---|
| Primary | `#14A800` | Buttons, links, active states, primary chart series |
| Hover | `#128A00` | Hover states |
| Active | `#0F7300` | Pressed and active states |
| Tint | `#EAF9E7` | Light-mode accent backgrounds |
| Warning | `#F59E0B` | Expiring-soon flags, mid-tier quality scores |
| Error | `#DC2626` | Low quality-score indicators |
| Information | `#2563EB` | Neutral status readouts |

| Theme | Background | Cards | Primary Text |
|---|---|---|---|
| Dark | `#121212` | `#222222` | `#F5F5F5` |
| Light | `#F8F9FA` | `#FFFFFF` | `#1F2937` |

Typography is Inter throughout: headings at semibold (600), body text at
regular (400), and buttons/navigation at medium (500). Corner radii range
from 10px to 14px. Chart series use varying shades of the same green rather
than an unrelated color palette, for visual consistency across the
dashboard.

## Limitations and Known Issues

- **Markup dependency.** The scraper relies on each site's current HTML
  structure. A layout change on any of the five sources will likely require
  an update to that source's extraction routine.
- **Keyword-based relevance.** Filtering is keyword-driven, which can admit
  some false positives (adjacent but not truly relevant roles) and miss
  listings that use unusual phrasing.
- **Quality score is structural, not qualitative.** It reflects how
  complete a listing's metadata is, not whether the job itself is a good
  opportunity.
- **No rate-limit or terms-of-service handling beyond basic delays.**
  Anyone deploying this should review each target site's terms of service
  and robots.txt before running it on a recurring or high-frequency basis.
- **Trend accuracy scales with history.** Historical charts are only as
  meaningful as the number of daily snapshots present locally; a fresh
  install with one day of data will show minimal trend information.
- **Single-user, local tool.** There is no multi-user access control, and
  data is stored as local files rather than in a shared database.

## Roadmap

See [CHANGELOG.md](CHANGELOG.md) for version history. Suggestions and
contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Data Sources

- [MyJobMag Kenya](https://www.myjobmag.co.ke/)
- [BrighterMonday Kenya](https://www.brightermonday.co.ke/)
- [Fuzu](https://www.fuzu.com/kenya)
- [CareerPoint Kenya](https://www.careerpointkenya.co.ke/)
- [MyJobsInKenya](https://www.myjobsinkenya.com/)

## References

- [Selenium documentation](https://www.selenium.dev/documentation/)
- [Flask documentation](https://flask.palletsprojects.com/)
- [Chart.js documentation](https://www.chartjs.org/docs/latest/)
- [pandas documentation](https://pandas.pydata.org/docs/)
- [SheetJS (xlsx export)](https://docs.sheetjs.com/)

## License

Released under the [MIT License](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and
conventions.
