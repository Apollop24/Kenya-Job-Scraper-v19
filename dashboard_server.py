#!/usr/bin/env python3
"""
Kenya Job Scraper - Dashboard Server
=====================================
Why this file exists
---------------------
The dashboard is a plain HTML file. Browsers deliberately do not let a
web page - even one you opened yourself from disk - launch programs or run
Python on your computer; if they did, any website could do the same thing
to run arbitrary code on your computer, which is why that door is closed.

So a button *inside* the dashboard HTML cannot, by itself, re-run
kenya_job_scraper_v22.py. What it CAN do is call a small local web server
that runs on your own machine and is allowed to launch that script - which
is exactly what this file is.

How to use it
-------------
    pip install flask selenium pandas
    python dashboard_server.py

Then open the URL it prints (default http://localhost:8877) instead of
double-clicking the dashboard HTML file directly. The page looks and works
exactly the same, except the "Run scraper" button now actually works:
clicking it runs kenya_job_scraper_v22.py in the background, and the page
reloads itself with fresh data when the run finishes.

If you open the dashboard HTML file directly (double-click, file:// URL)
the button still shows up but explains it needs this server instead of
silently pretending to work.

Optional: pass --schedule to also auto-run the scraper once every 24
hours in the background, for a simple "daily updates" scheduler.
"""

import argparse
import threading
import time
import traceback
from datetime import datetime

from flask import Flask, jsonify, Response

from kenya_job_scraper_v22 import KenyaJobScraper, get_or_create_save_path

app = Flask(__name__)

# ----------------------------------------------------------------------
# Shared run-state. A simple dict guarded by a lock is enough here - this
# server is meant for one person on their own machine, not concurrent
# multi-user traffic.
# ----------------------------------------------------------------------
_state_lock = threading.Lock()
_state = {
    "running": False,
    "message": "Idle.",
    "error": None,
    "last_finished_at": None,
}

SAVE_PATH = None  # resolved in main()


def _set_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)


def _run_scraper_background():
    _set_state(running=True, message="Scraper started - this can take several minutes...", error=None)
    try:
        scraper = KenyaJobScraper(save_path=SAVE_PATH)
        _set_state(message="Scraping MyJobMag, BrighterMonday, Fuzu, CareerPoint Kenya, MyJobsInKenya...")
        scraper.run()
        _set_state(
            running=False,
            message=f"Finished - {len(scraper.jobs_data)} job(s) in today's file.",
            error=None,
            last_finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as e:
        traceback.print_exc()
        _set_state(running=False, message="Scraper failed.", error=str(e))


@app.route("/")
def index():
    """Serve the latest dashboard HTML, generating one first if this is a
    brand-new folder with no dashboard yet."""
    scraper = KenyaJobScraper(save_path=SAVE_PATH)
    if not scraper.jobs_data:
        return Response(
            "<html><body style='font-family:sans-serif;background:#0a1930;color:#eaf1fc;"
            "padding:60px;text-align:center;'>"
            "<h1>No job data yet</h1>"
            "<p>Click below to run the scraper for the first time.</p>"
            "<button onclick=\"fetch('/api/refresh',{method:'POST'}).then(()=>alert("
            "'Scraper started - this can take a few minutes. Reload this page when it finishes.'))\" "
            "style='padding:12px 20px;font-size:1rem;border-radius:8px;border:none;"
            "background:#3b82f6;color:white;cursor:pointer;'>Run scraper now</button>"
            "</body></html>",
            mimetype="text/html",
        )
    scraper.generate_dashboard()
    with open(scraper.dashboard_filename, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    with _state_lock:
        if _state["running"]:
            return jsonify({"error": "A scrape is already running."}), 409
    thread = threading.Thread(target=_run_scraper_background, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/status")
def api_status():
    with _state_lock:
        return jsonify(dict(_state))


def _scheduler_loop(interval_hours: float):
    """Optional bonus feature: re-run the scraper automatically on a fixed
    interval (default once every 24h with --schedule). Runs forever in a
    daemon thread; skips a cycle if a manual run is already in progress."""
    while True:
        time.sleep(interval_hours * 3600)
        with _state_lock:
            already_running = _state["running"]
        if not already_running:
            print(f"[scheduler] Kicking off a scheduled scrape at {datetime.now().isoformat(timespec='seconds')}")
            _run_scraper_background()


def main():
    global SAVE_PATH

    parser = argparse.ArgumentParser(description="Kenya Job Scraper - Dashboard Server")
    parser.add_argument("--path", dest="save_path", default=None,
                         help="Folder where scraper data/dashboard live (same one the scraper uses).")
    parser.add_argument("--port", type=int, default=8877, help="Port to serve the dashboard on.")
    parser.add_argument("--schedule", action="store_true",
                         help="Also auto-run the scraper every --schedule-hours (default 24h).")
    parser.add_argument("--schedule-hours", type=float, default=24.0,
                         help="Interval in hours between scheduled runs (used with --schedule).")
    args = parser.parse_args()

    SAVE_PATH = get_or_create_save_path(override=args.save_path)

    if args.schedule:
        threading.Thread(target=_scheduler_loop, args=(args.schedule_hours,), daemon=True).start()
        print(f"Scheduler on: auto-refreshing every {args.schedule_hours} hour(s).")

    url = f"http://localhost:{args.port}"
    print("=" * 70)
    print("Kenya Job Scraper - Dashboard Server")
    print("=" * 70)
    print(f"Data folder: {SAVE_PATH}")
    print(f"Open this in your browser (NOT the raw HTML file): {url}")
    print("Press Ctrl+C to stop.")
    print("-" * 70)

    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
