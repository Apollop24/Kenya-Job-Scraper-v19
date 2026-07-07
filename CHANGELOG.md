# Changelog

All notable changes to this project are documented here.

## [22.0] - 2026-07

### Added
- Enriched data model: every saved job now includes `date_scraped`, `day_of_week`, `week_key`, `month_key`, a normalized `city`, `matched_keywords`, a canonical `title_bucket`, a `quality_score` (0-100 listing completeness), and `freshness_days`.
- Historical trend tracking via `load_historical_jobs()`, which reads every daily `kenya_jobs_*.json` snapshot in the data folder and de-duplicates by link, powering multi-day analytics without a database.
- Analytics dashboard rebuild:
  - 6 KPI cards (Total Jobs, New Today, New This Week, Job Boards, Cities Covered, Avg. Listing Quality)
  - Hiring trend line chart (jobs scraped per day, last 30 days)
  - Top Job Titles and Jobs by Day of Week charts
  - Source Quality comparison chart
  - 5-week calendar heatmap
  - Table rows with conditional-formatting badges ("New today", "Expiring soon") and a quality indicator
  - Filters for source, location, quality tier, and "new today only"
  - Export to CSV, Excel (.xlsx), and Print/PDF
  - Light/dark theme toggle, following a monochromatic green design system with the theme persisted in `localStorage`
- `dashboard_server.py`: a local Flask server that powers a one-click "Run scraper" button on the dashboard (starts a background scrape, polls status, then reloads with fresh data). Supports an optional `--schedule` flag for automatic recurring runs.

### Changed
- Refactored the relevant-keyword list into a shared class constant (`RELEVANT_KEYWORDS`) used by both relevance filtering and keyword-match enrichment, removing duplicated logic.
- Dashboard visuals (charts, badges, buttons) restyled to the project's design system (see `README.md`).

## [21.0] - 2026-07
- Universal Edition: multi-source scraping across MyJobMag, BrighterMonday, Fuzu, CareerPoint Kenya, and MyJobsInKenya, with a static navy-themed HTML dashboard, JSON/CSV export, and a local cache to avoid re-scraping unchanged listings.
