#!/usr/bin/env python3
"""
Kenya Job Scraper v22 - Analytics Edition
A robust web scraper for Kenyan job boards with cross-platform setup, resilient
scraping helpers, and a professional interactive dashboard.
Handles BrighterMonday, MyJobMag, CareerPoint Kenya, Fuzu, and MyJobsInKenya.

What's new in v20
------------------
- UNIVERSAL SAVE LOCATION: on first run, the script asks (via a native folder
  picker, or a console prompt if no display is available) where to store its
  output. The choice is remembered in a small config file in the user's home
  folder, so the same script works unmodified on Windows, macOS, or Linux.
- ROBUST INTERACTIONS: new safe_type / safe_click / find_visible_input /
  get_element_text helpers replace the old "hope it's visible" pattern that
  was causing ElementNotInteractable crashes (mainly on BrighterMonday) and
  blank job titles (mainly on Fuzu, whose `.text` was frequently empty for
  off-screen list items).
- FUZU FIX: results are now filtered through is_relevant_job() and
  de-duplicated (previously every element on the results page was saved,
  regardless of relevance, producing dozens of blank-title duplicates).
- CAREERPOINT KENYA FIX: the scraper now actually performs a WordPress
  keyword search (previously it just re-filtered whatever was already on the
  homepage, which is why it always returned 0 jobs).
- PROFESSIONAL DASHBOARD: complete visual rebuild in a navy-blue, data/fintech
  inspired aesthetic, with KPI cards, two charts, a searchable/filterable
  table, and graceful handling of missing data.

What's new in v21 (based on a real run's log)
-----------------------------------------------
- JUPYTER/IPYTHON FIX: argparse now uses parse_known_args(), so running the
  script from a Jupyter/IPython cell no longer crashes on the kernel's own
  `-f kernel-xxxx.json` argument.
- FUZU + MYJOBSINKENYA, TAKE TWO: a real run showed both sites returning the
  exact same result count on every one of the 12 keyword searches - proof
  their client-side search boxes weren't actually filtering anything. Both
  scrapers now scan the general/paginated job feed directly and apply
  is_relevant_job() once, instead of trusting a search box that two rounds
  of testing show is unreliable.
- TITLE EXTRACTION FIX: get_element_text() now returns only the first line
  of text. Fuzu (and possibly others) wraps an entire job card - title AND
  full description - in one <a>, so grabbing all of .text produced a giant
  blob that never matched is_relevant_job(); the title is reliably the
  first line. get_richest_text_by_href() also de-duplicates the several
  overlapping <a href="/job/..."> elements (title, Apply button, bookmark
  icon) that modern job cards wrap around the same URL.
- SSL/CERT TOLERANCE: added --ignore-certificate-errors / --ignore-ssl-errors
  to Chrome, since CareerPoint Kenya was failing every single page load
  with a certificate handshake error on one tested network (common with
  corporate proxies or antivirus HTTPS scanning).

What's new in v22 (analytics dashboard rebuild)
-----------------------------------------------
- RICHER DATA MODEL: every saved job now also carries date_scraped,
  day_of_week, week_key (ISO year-week), month_key, a normalized city,
  a list of matched_keywords, a 0-100 quality_score (how complete the
  listing is), and freshness_days (age relative to today). This is all
  computed once in enrich_job_data() so every scraper benefits without
  touching the five site-specific extractors.
- HISTORICAL TREND TRACKING: load_historical_jobs() scans every
  kenya_jobs_*.json file ever saved in the save folder (not just today's),
  de-duplicates by link, and builds a multi-day dataset. This powers the
  "jobs over time" trend chart and week-over-week KPIs without needing a
  real database.
- ANALYTICS DASHBOARD REBUILD: generate_dashboard() now computes and
  renders a full BI-style dashboard - 6 KPI cards, a hiring trend line
  chart, top job titles, jobs by day-of-week, a source quality/freshness
  comparison, a 5-week calendar heatmap, plus the existing source/location
  breakdowns. Table rows get conditional-formatting badges (New today /
  Expiring soon / quality dot). CSV export is joined by an Excel (.xlsx)
  export and a print-to-PDF button.
- LIVE REFRESH BUTTON: the dashboard now has a "Run scraper" button. A
  static HTML file can't launch a local process by itself (browsers don't
  allow that, for good security reasons), so this ships with a small
  companion script, dashboard_server.py, that serves the dashboard and
  exposes the endpoint the button calls to actually re-run this scraper
  and reload with fresh data. See dashboard_server.py / README for setup.

Author: Data Scientist
Date: 2026-07-02
Version: 22.0
"""

import os
import re
import glob
import json
import time
import pickle
import hashlib
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import quote_plus

import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.keys import Keys


# ======================================================================
# UNIVERSAL SAVE-PATH SETUP
# ======================================================================
# This lives outside the class so it can run before logging / the scraper
# object even exist. It works the same way on Windows, macOS, and Linux:
#   1. If a path was passed in explicitly, use it.
#   2. Otherwise, look for a remembered choice in a small JSON config file
#      in the user's home directory.
#   3. Otherwise, ask the user - first by trying a native folder picker
#      (tkinter, bundled with Python), falling back to a plain console
#      prompt if there is no display (e.g. a headless server).
# The chosen folder is then remembered for next time.

CONFIG_FILENAME = ".kenya_job_scraper_config.json"


def _config_path() -> str:
    return os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)


def _default_save_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Documents", "KenyaJobScraper")


def _prompt_for_folder_gui(initial_dir: str) -> Optional[str]:
    """Try a native folder-picker dialog. Returns None if unavailable/cancelled
    (e.g. running on a headless server with no display)."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        chosen = filedialog.askdirectory(
            title="Select a folder to save Kenya Job Scraper data",
            initialdir=initial_dir if os.path.isdir(initial_dir) else os.path.expanduser("~"),
        )
        root.destroy()
        return chosen or None
    except Exception:
        return None


def _prompt_for_folder_console(default_dir: str) -> str:
    print("\n" + "=" * 64)
    print("FIRST-TIME SETUP - Where should job data be saved?")
    print("=" * 64)
    print("This only needs to happen once per computer. The choice is")
    print(f"remembered in: {_config_path()}")
    print(f"\nPress Enter to accept the default:\n  {default_dir}\n")
    typed = input("Folder path (or Enter for default): ").strip().strip('"').strip("'")
    return typed if typed else default_dir


def get_or_create_save_path(override: Optional[str] = None, force_prompt: bool = False) -> str:
    """Resolve the folder used to store every file this scraper produces."""
    if override:
        os.makedirs(override, exist_ok=True)
        return override

    config_file = _config_path()

    if not force_prompt and os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                saved = json.load(f).get("save_path")
            if saved:
                os.makedirs(saved, exist_ok=True)
                return saved
        except Exception:
            pass  # fall through and re-prompt if the config file is corrupt

    default_dir = _default_save_dir()
    chosen = _prompt_for_folder_gui(default_dir)
    if not chosen:
        chosen = _prompt_for_folder_console(default_dir)

    chosen = os.path.abspath(os.path.expanduser(chosen))
    os.makedirs(chosen, exist_ok=True)

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({"save_path": chosen, "set_on": datetime.now().isoformat()}, f, indent=2)
    except Exception:
        pass  # non-fatal - worst case we just ask again next run

    print(f"\nSave location set to: {chosen}")
    print(f"(Delete {config_file} any time to be asked again, or run with --path)\n")
    return chosen


class KenyaJobScraper:
    def __init__(self, save_path: Optional[str] = None, force_path_prompt: bool = False):
        """Initialize the Kenya Job Scraper with optimized, cross-platform settings."""
        self.save_path = get_or_create_save_path(override=save_path, force_prompt=force_path_prompt)
        self.jobs_data = []
        self.duplicate_urls = set()
        self.today = datetime.now().date()

        # File names - single files per day
        self.json_filename = os.path.join(self.save_path, f"kenya_jobs_{self.today.strftime('%Y-%m-%d')}.json")
        self.csv_filename = os.path.join(self.save_path, f"jobs_{self.today.strftime('%Y-%m-%d')}.csv")
        self.cache_filename = os.path.join(self.save_path, f"cache_{self.today.strftime('%Y-%m-%d')}.pkl")
        self.dashboard_filename = os.path.join(self.save_path, f"jobs_dashboard_{self.today.strftime('%Y-%m-%d')}.html")

        # Create save directory if it doesn't exist
        os.makedirs(self.save_path, exist_ok=True)

        # Setup logging first (before load_existing_data)
        self.setup_logging()
        self.logger.info(f"Save path resolved to: {self.save_path}")

        # Load existing data and cache
        self.load_existing_data()
        self.load_cache()

        # Initialize webdriver as None (lazy loading)
        self.driver = None
        self.wait = None
        self.long_wait = None  # For human verification

        # KEYWORD CONFIGURATION - Update this list to change search terms
        self.search_keywords = [
            "data", "officer", "MONITORING",
            "data analyst",
            "data analysis",
            "data science",
            "data scientist",
            "data engineer",
            "data analytics",
            "business intelligence",
            "statistics",
            "statistician"
        ]

        # Track run configuration for smarter caching
        self.current_run_config = self.get_current_run_config()

    def get_current_run_config(self) -> str:
        """Generate a hash of current run configuration for cache invalidation"""
        config_data = {
            'keywords': sorted(self.search_keywords),
            'date': self.today.isoformat(),
            'version': '22.0'
        }
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def setup_logging(self):
        """Setup logging configuration without unicode characters"""
        log_filename = os.path.join(self.save_path, f"job_scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("Enhanced logging system initialized")

    def setup_driver(self):
        """Setup Selenium WebDriver with optimized settings (lazy loading)"""
        if self.driver is not None:
            return  # Driver already initialized

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1366,768")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        # Some networks (corporate proxies, antivirus HTTPS scanning) present
        # a certificate Chrome doesn't trust, which showed up as repeated
        # "SSL error code 1, net_error -201" and 0 results from CareerPoint
        # Kenya. These flags tell Chrome to load the page anyway - safe here
        # since we're only reading public job listings, nothing sensitive
        # is ever sent.
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--ignore-ssl-errors")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 1
        })

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.set_window_size(1366, 768)
            self.wait = WebDriverWait(self.driver, 20)
            self.long_wait = WebDriverWait(self.driver, 45)  # Extended wait for human verification
            self.logger.info("Enhanced WebDriver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # ROBUST INTERACTION HELPERS (v20/v21, unchanged in v22)
    # ------------------------------------------------------------------
    # These replace the old pattern of "find an element, check
    # is_displayed(), hope for the best" that was responsible for both the
    # BrighterMonday "element not interactable" crashes and the Fuzu blank
    # job-title bug (Selenium's .text can be empty for elements that are
    # technically present but not yet laid out / off-screen).

    def get_element_text(self, element) -> str:
        """Robustly extract an element's *title* text.

        Falls back to JS innerText/textContent when Selenium's .text comes
        back empty (the original blank-title bug). It also only keeps the
        first non-empty line: on card-style layouts (Fuzu in particular)
        the whole job card - title AND the full description - is wrapped
        in a single <a>, so a naive `.text` grab returns one giant blob.
        Selenium's .text renders block-level children on separate lines,
        so the first line is reliably the title; taking the whole blob was
        why the relevance filter kept silently rejecting real matches."""
        def first_line(raw: str) -> str:
            for line in raw.splitlines():
                line = line.strip()
                if line:
                    return line
            return raw.strip()

        try:
            text = element.text.strip()
            if text:
                return first_line(text)
        except Exception:
            pass
        for js_prop in ("innerText", "textContent"):
            try:
                text = self.driver.execute_script(f"return arguments[0].{js_prop};", element)
                if text and text.strip():
                    return first_line(text)
            except Exception:
                continue
        try:
            title_attr = element.get_attribute("title")
            if title_attr and title_attr.strip():
                return first_line(title_attr)
        except Exception:
            pass
        return ""

    def get_richest_text_by_href(self, elements) -> Dict[str, str]:
        """Group elements by their href and keep only the longest text seen
        for each link. Modern job cards often wrap several anchors around
        the same URL (the title, an 'Apply' button, a bookmark icon...);
        without this, whichever one Selenium happens to see first - often
        an icon with no text - wins, producing blank/junk titles even
        though a same-href sibling had the real title available."""
        best: Dict[str, str] = {}
        for el in elements:
            try:
                href = el.get_attribute('href')
            except Exception:
                href = None
            if not href:
                continue
            text = self.get_element_text(el)
            if href not in best or len(text) > len(best[href]):
                best[href] = text
        return best

    def find_visible_input(self, selectors: List[str]):
        """Return the first element matching one of the XPath selectors that
        is actually visible and enabled - never a hidden/stale leftover."""
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
            except Exception:
                continue
            for el in elements:
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except StaleElementReferenceException:
                    continue
        return None

    def safe_type(self, element, text: str) -> bool:
        """Type into an input safely: scroll into view, wait for visibility,
        and fall back to a JS value-set (with input/change events) if native
        typing is blocked - this is what was crashing BrighterMonday."""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.3)
            WebDriverWait(self.driver, 5).until(EC.visibility_of(element))
            element.clear()
            element.send_keys(text)
            return True
        except Exception as e:
            try:
                self.driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                    element, text
                )
                return True
            except Exception:
                self.logger.warning(f"safe_type failed for text '{text}': {str(e)}")
                return False

    def safe_click(self, element) -> bool:
        """Click an element robustly: scroll into view, try a native click,
        fall back to a JS click if something is intercepting it."""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.3)
            element.click()
            return True
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as e:
                self.logger.warning(f"safe_click failed: {str(e)}")
                return False

    def safe_search_submit(self, search_input) -> bool:
        """Try to submit a search box the way a real user would: press
        Enter. Used as a lightweight fallback when no obvious submit
        button can be found."""
        try:
            search_input.send_keys(Keys.RETURN)
            return True
        except Exception as e:
            self.logger.warning(f"safe_search_submit failed: {str(e)}")
            return False

    def load_existing_data(self):
        """Load existing job data from today's files"""
        if os.path.exists(self.json_filename):
            try:
                with open(self.json_filename, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    self.jobs_data = existing_data
                    for job in existing_data:
                        if 'link' in job:
                            self.duplicate_urls.add(job['link'])
                if hasattr(self, 'logger'):
                    self.logger.info(f"Loaded {len(self.jobs_data)} existing jobs from today's file")
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"Error loading existing data: {str(e)}")
        else:
            if hasattr(self, 'logger'):
                self.logger.info("No existing data file found, starting fresh")

    def load_cache(self):
        """Load cached data to avoid repetitive tasks"""
        self.cache = {}
        if os.path.exists(self.cache_filename):
            try:
                with open(self.cache_filename, 'rb') as f:
                    self.cache = pickle.load(f)
                self.logger.info(f"Loaded cache with {len(self.cache)} entries")
            except Exception as e:
                self.logger.error(f"Error loading cache: {str(e)}")
                self.cache = {}

    def save_cache(self):
        """Save cache data"""
        try:
            with open(self.cache_filename, 'wb') as f:
                pickle.dump(self.cache, f)
            self.logger.info("Cache saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving cache: {str(e)}")

    def is_cache_valid_for_run(self, cache_key: str) -> bool:
        """Check if cache is still valid based on run configuration changes"""
        if cache_key not in self.cache:
            return False

        cached_data = self.cache[cache_key]
        if isinstance(cached_data, dict):
            cached_config = cached_data.get('run_config')
            if cached_config != self.current_run_config:
                self.logger.info(f"Cache invalid for {cache_key}: configuration changed")
                return False

            cached_date = cached_data.get('date')
            if cached_date != self.today.isoformat():
                self.logger.info(f"Cache invalid for {cache_key}: date changed")
                return False

            self.logger.info(f"Cache valid for {cache_key}: using cached data")
            return True

        return False

    def is_not_expired(self, date_expires: str) -> bool:
        """Check if job has not expired"""
        expire_date = self.parse_date(date_expires)
        if expire_date:
            return expire_date.date() >= self.today
        return True  # Include if we can't parse the date

    def parse_date(self, date_string: str) -> Optional[datetime]:
        """Parse various date formats to datetime object"""
        if not date_string or date_string.lower() in ['not specified', 'unknown', 'recently posted']:
            return None

        date_string = date_string.strip()

        if 'ago' in date_string.lower():
            if 'day' in date_string.lower():
                match = re.search(r'(\d+)', date_string)
                if match:
                    return datetime.now() - timedelta(days=int(match.group(1)))
            elif 'week' in date_string.lower():
                match = re.search(r'(\d+)', date_string)
                if match:
                    return datetime.now() - timedelta(weeks=int(match.group(1)))
            elif 'hour' in date_string.lower() or 'minute' in date_string.lower():
                return datetime.now()

        date_formats = [
            "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d/%m/%Y",
            "%m/%d/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y"
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue

        return None

    def is_recent_job(self, date_posted: str, date_expires: str = None) -> bool:
        """Check if job was posted within the last 7 days or hasn't expired"""
        job_date = self.parse_date(date_posted)
        if job_date:
            seven_days_ago = self.today - timedelta(days=7)
            return job_date.date() >= seven_days_ago

        if date_expires and date_expires.lower() not in ['not specified', 'unknown']:
            expire_date = self.parse_date(date_expires)
            if expire_date:
                return expire_date.date() >= self.today

        # If neither date is available, include the job to avoid missing opportunities
        return True

    def should_continue_to_next_page(self, jobs_on_page: List[Dict]) -> bool:
        """Determine if we should continue to next page based on job dates"""
        if not jobs_on_page:
            return False

        last_job = jobs_on_page[-1]

        if last_job.get('date_posted') and last_job['date_posted'] != 'Not specified':
            if not self.is_recent_job(last_job['date_posted']):
                return False

        if last_job.get('date_expires') and last_job['date_expires'] != 'Not specified':
            if not self.is_not_expired(last_job['date_expires']):
                return False

        return True

    def get_cache_key_with_config(self, site_name: str) -> str:
        """Generate cache key that includes run configuration"""
        return f"{site_name}_{self.current_run_config}"

    # Pulled out to a class constant (was a local list rebuilt on every call)
    # so both is_relevant_job() and get_matched_keywords()/enrich_job_data()
    # can share one source of truth for what "relevant" means.
    RELEVANT_KEYWORDS = [
        # Core roles & areas
        'data analyst', 'data analysis', 'statistics', 'statistician',
        'business intelligence', 'data analytics', 'analytics',
        'data science', 'data scientist', 'quantitative',
        'research analyst', 'economic analyst',
        'monitoring and evaluation', 'm&e',
        'data engineer',

        # Technical tools & languages
        'sql', 'python', 'r programming',
        'tableau', 'power bi', 'excel', 'spss',
        'database', 'data warehousing', 'etl',
        'big data', 'hadoop', 'spark',

        # Visualization & reporting
        'data visualization', 'dashboard', 'reporting',
        'google data studio', 'google analytics', 'matplotlib',
        'seaborn', 'plotly',

        # ML & AI buzzwords
        'machine learning', 'predictive modeling', 'a/b testing',
        'data mining', 'ml', 'ai tools', 'prompt engineering',
        'augmented analytics', 'agent workflows',

        # Soft & domain-specific
        'communication', 'critical thinking', 'problem solving',
        'attention to detail', 'collaboration', 'project management',
        'economic analysis', 'financial modeling',
        'healthcare analytics', 'clinical data management'
    ]

    # A small subset of RELEVANT_KEYWORDS that make sense as *job title*
    # buckets for the "Top Job Titles" chart. Free-text titles are messy
    # ("Senior Data Analyst - Fixed Term", "JUNIOR DATA ANALYST", ...), so
    # rather than counting unique strings (which fragments the chart into
    # dozens of one-off bars) we bucket each title into the first canonical
    # role it matches.
    TITLE_BUCKETS = [
        ('Data Scientist', ['data scientist', 'data science']),
        ('Data Analyst', ['data analyst', 'data analysis']),
        ('Data Engineer', ['data engineer']),
        ('Business Intelligence', ['business intelligence', 'bi analyst', 'bi developer']),
        ('Statistician', ['statistician', 'statistics']),
        ('M&E', ['monitoring and evaluation', 'm&e', 'm & e']),
        ('Research Analyst', ['research analyst']),
        ('Data Analytics', ['data analytics', 'analytics']),
    ]

    def is_relevant_job(self, job_title: str, job_description: str = "") -> bool:
        """Check if job is relevant based on title and description"""
        if not job_title:
            return False

        title_lower = job_title.lower()
        desc_lower = job_description.lower()

        for keyword in self.RELEVANT_KEYWORDS:
            if keyword in title_lower or keyword in desc_lower:
                return True

        return False

    def get_matched_keywords(self, job_title: str, job_description: str = "") -> List[str]:
        """Return every relevant keyword found in the title/description, used
        to enrich the saved record for reporting (e.g. 'what skills are most
        in demand this week')."""
        title_lower = (job_title or "").lower()
        desc_lower = (job_description or "").lower()
        matched = [
            kw for kw in self.RELEVANT_KEYWORDS
            if kw in title_lower or kw in desc_lower
        ]
        return matched

    def bucket_job_title(self, job_title: str) -> str:
        """Map a messy free-text title to one canonical bucket for charting."""
        title_lower = (job_title or "").lower()
        for label, needles in self.TITLE_BUCKETS:
            if any(n in title_lower for n in needles):
                return label
        return 'Other'

    @staticmethod
    def _extract_city(location: str) -> str:
        """Normalize a free-text location into a single city/place name so
        jobs like 'Nairobi, Kenya' and 'Nairobi' land in the same bucket.
        Takes the first comma-separated segment and title-cases it."""
        if not location or location.strip().lower() in ('not specified', 'unknown', ''):
            return 'Not specified'
        first_segment = location.split(',')[0].strip()
        return first_segment.title() if first_segment else 'Not specified'

    def _compute_freshness_days(self, date_posted: str) -> Optional[int]:
        """Days between the parsed posted date and today, or None if the
        date couldn't be parsed (kept as None rather than 0 so averages
        aren't silently skewed by unknown dates)."""
        parsed = self.parse_date(date_posted)
        if not parsed:
            return None
        return max((self.today - parsed.date()).days, 0)

    @staticmethod
    def _compute_quality_score(job_data: Dict) -> int:
        """A simple 0-100 completeness score for a listing: how many of the
        fields a job-seeker actually cares about were successfully scraped.
        Used on the dashboard to compare source quality, and to help spot
        when a site's markup has changed (quality drops sharply)."""
        checks = [
            job_data.get('date_posted', 'Not specified') not in ('Not specified', 'Unknown', ''),
            job_data.get('date_expires', 'Not specified') not in ('Not specified', 'Unknown', ''),
            job_data.get('location', 'Not specified') not in ('Not specified', 'Unknown', '', 'Kenya'),
            job_data.get('qualification', 'Not specified') not in ('Not specified', 'Unknown', ''),
            job_data.get('years_of_experience', 'Not specified') not in ('Not specified', 'Unknown', ''),
        ]
        return round(100 * sum(checks) / len(checks))

    def enrich_job_data(self, job_data: Dict) -> Dict:
        """Add every derived field the analytics dashboard needs. Runs once,
        centrally, in save_job_data() so all five site scrapers benefit
        without any of their extract_*_job_details() methods changing."""
        now = datetime.now()
        job_data['date_scraped'] = now.strftime('%Y-%m-%d')
        job_data['scraped_at'] = now.isoformat(timespec='seconds')
        job_data['day_of_week'] = now.strftime('%A')
        job_data['week_key'] = now.strftime('%G-W%V')   # ISO year-week, e.g. 2026-W27
        job_data['month_key'] = now.strftime('%Y-%m')
        job_data['city'] = self._extract_city(job_data.get('location', ''))
        job_data['matched_keywords'] = self.get_matched_keywords(job_data.get('job_title', ''))
        job_data['title_bucket'] = self.bucket_job_title(job_data.get('job_title', ''))
        job_data['freshness_days'] = self._compute_freshness_days(job_data.get('date_posted', ''))
        job_data['quality_score'] = self._compute_quality_score(job_data)
        return job_data

    def save_job_data(self, job_data: Dict):
        """Save individual job data immediately to prevent data loss"""
        if not job_data.get('job_title') or not job_data.get('link'):
            self.logger.warning("Skipped saving a job with a missing title or link")
            return

        job_data = self.enrich_job_data(job_data)
        self.jobs_data.append(job_data)

        try:
            with open(self.json_filename, 'w', encoding='utf-8') as f:
                json.dump(self.jobs_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving JSON: {str(e)}")

        try:
            df = pd.DataFrame(self.jobs_data)
            df.to_csv(self.csv_filename, index=False, encoding='utf-8')
        except Exception as e:
            self.logger.error(f"Error saving CSV: {str(e)}")

        self.logger.info(f"Saved job #{len(self.jobs_data)}: {job_data.get('job_title', 'Unknown')}")

    def handle_popups(self):
        """Enhanced popup handling with better selectors"""
        popup_handlers = [
            ("button", "id", "onetrust-accept-btn-handler"),
            ("button", "class", "onetrust-accept-btn-handler"),
            ("button", "text", "Accept"),
            ("button", "text", "Accept All"),
            ("button", "text", "I Accept"),
            ("button", "id", "onesignal-slidedown-cancel-button"),
            ("button", "class", "onesignal-slidedown-cancel-button"),
            ("button", "text", "No Thanks"),
            ("button", "text", "Not Now"),
            ("img", "data-cy", "close-modal"),
            ("button", "class", "close"),
            ("button", "class", "modal-close"),
            ("div", "class", "modal-close"),
            ("span", "class", "close"),
            ("button", "text", "\u00d7"),
            ("button", "text", "\u2715"),
            ("span", "text", "\u00d7"),
            ("span", "text", "\u2715"),
            ("div", "class", "close-button"),
            ("button", "class", "app-download-close"),
            ("button", "aria-label", "Close"),
            ("button", "title", "Close"),
        ]

        for tag, attr, value in popup_handlers:
            try:
                if attr == "class":
                    element = self.driver.find_element(By.XPATH, f"//{tag}[contains(@{attr}, '{value}')]")
                elif attr == "text":
                    element = self.driver.find_element(By.XPATH, f"//{tag}[contains(text(), '{value}')]")
                else:
                    element = self.driver.find_element(By.XPATH, f"//{tag}[@{attr}='{value}']")

                if element.is_displayed():
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(1)
                    self.logger.info(f"Closed popup: {tag}[@{attr}='{value}']")
            except (NoSuchElementException, Exception):
                continue

    def handle_human_verification(self, max_retries: int = 3) -> bool:
        """Enhanced human verification handling specifically for Fuzu"""
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Attempting human verification (attempt {attempt + 1}/{max_retries})")
                time.sleep(3)

                verification_indicators = [
                    "//div[contains(text(), 'Verifying you are human')]",
                    "//p[contains(text(), 'Verifying you are human')]",
                    "//h1[contains(text(), 'Verifying you are human')]",
                    "//div[contains(@class, 'main-content')]",
                    "//input[@type='checkbox']"
                ]

                verification_present = False
                for indicator in verification_indicators:
                    try:
                        element = self.driver.find_element(By.XPATH, indicator)
                        if element.is_displayed():
                            verification_present = True
                            self.logger.info(f"Human verification detected: {indicator}")
                            break
                    except Exception:
                        continue

                if not verification_present:
                    self.logger.info("No human verification detected")
                    return True

                checkbox_selectors = [
                    "//input[@type='checkbox']",
                    "//input[@type='checkbox' and contains(@name, 'cf-turnstile')]",
                    "//input[@type='checkbox' and contains(@id, 'cf-chl')]",
                    "//div[contains(@class, 'cf-turnstile')]//input[@type='checkbox']"
                ]

                checkbox_found = False
                for selector in checkbox_selectors:
                    try:
                        self.logger.info(f"Looking for checkbox: {selector}")
                        checkbox = self.long_wait.until(EC.element_to_be_clickable((By.XPATH, selector)))

                        if checkbox.is_displayed() and checkbox.is_enabled():
                            self.safe_click(checkbox)
                            self.logger.info("Checkbox clicked")
                            checkbox_found = True
                            time.sleep(2)
                            break
                    except TimeoutException:
                        self.logger.info(f"Checkbox not found with selector: {selector}")
                        continue
                    except Exception as e:
                        self.logger.error(f"Error with checkbox selector {selector}: {str(e)}")
                        continue

                if not checkbox_found:
                    self.logger.warning("No clickable checkbox found, continuing...")
                    time.sleep(5)
                    continue

                verify_button_selectors = [
                    "//button[contains(text(), 'Verify')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[contains(text(), 'Submit')]",
                    "//input[@type='submit']",
                    "//button[@type='submit']"
                ]

                for selector in verify_button_selectors:
                    try:
                        verify_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                        if verify_button.is_displayed():
                            self.safe_click(verify_button)
                            self.logger.info(f"Clicked verify button: {selector}")
                            time.sleep(3)
                            break
                    except Exception:
                        continue

                self.logger.info("Waiting for verification to complete...")
                time.sleep(8)

                success_indicators = [
                    "//div[contains(text(), 'Verification successful')]",
                    "//div[contains(text(), 'Success')]",
                    "//div[contains(@class, 'success')]"
                ]

                verification_successful = False
                for indicator in success_indicators:
                    try:
                        element = self.driver.find_element(By.XPATH, indicator)
                        if element.is_displayed():
                            verification_successful = True
                            self.logger.info("Human verification successful!")
                            break
                    except Exception:
                        continue

                current_url = self.driver.current_url
                if "challenge" not in current_url.lower() and "verify" not in current_url.lower():
                    verification_successful = True
                    self.logger.info("Redirected away from verification page - assuming success")

                if verification_successful:
                    return True

                self.logger.warning(f"Verification attempt {attempt + 1} may have failed, retrying...")
                time.sleep(5)

            except Exception as e:
                self.logger.error(f"Error in human verification attempt {attempt + 1}: {str(e)}")
                time.sleep(5)
                continue

        self.logger.error("Human verification failed after all attempts")
        return False

    # ------------------------------------------------------------------
    # MYJOBMAG  (this one was already working well - light-touch robustness
    # improvements only: safe_type/safe_click and get_element_text so it
    # doesn't regress if the site's markup shifts slightly)
    # ------------------------------------------------------------------
    def scrape_myjobmag(self) -> List[Dict]:
        """Scrape jobs from MyJobMag Kenya with smart date-based pagination"""
        jobs = []
        self.logger.info("Starting MyJobMag scraping...")

        try:
            cache_key = self.get_cache_key_with_config("myjobmag")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached MyJobMag data ({len(cached_jobs)} jobs)")
                return cached_jobs

            self.setup_driver()
            self.driver.get("https://www.myjobmag.co.ke")
            time.sleep(4)
            self.handle_popups()

            keywords_to_use = self.search_keywords

            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching MyJobMag for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")

                    if keyword_idx > 0:
                        self.driver.get("https://www.myjobmag.co.ke")
                        time.sleep(3)
                        self.handle_popups()

                    search_input = self.wait.until(EC.presence_of_element_located((By.ID, "search-key")))
                    self.safe_type(search_input, keyword)
                    time.sleep(1)

                    search_btn = self.driver.find_element(By.ID, "search-but")
                    self.safe_click(search_btn)
                    time.sleep(4)

                    page = 1
                    should_continue = True

                    while should_continue and page <= 5:  # Max 5 pages safety limit
                        job_links_data = []
                        page_jobs = []

                        try:
                            job_link_elements = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/job/')]")
                            for elem in job_link_elements:
                                try:
                                    href = elem.get_attribute('href')
                                    text = self.get_element_text(elem)
                                    if href and text and self.is_relevant_job(text):
                                        job_links_data.append({'href': href, 'title': text})
                                except Exception:
                                    continue
                        except Exception as e:
                            self.logger.error(f"Error collecting job links: {str(e)}")
                            break

                        self.logger.info(f"Page {page}: Found {len(job_links_data)} relevant job links for '{keyword}'")

                        for job_data in job_links_data:
                            try:
                                job_link = job_data['href']
                                job_title = job_data['title']

                                if job_link in self.duplicate_urls:
                                    continue

                                self.driver.get(job_link)
                                time.sleep(3)

                                extracted_data = self.extract_myjobmag_job_details(job_title, job_link)

                                if extracted_data:
                                    if extracted_data['date_posted'] != 'Not specified':
                                        if not self.is_recent_job(extracted_data['date_posted']):
                                            self.logger.info(f"Job older than 7 days detected: {job_title}. Stopping page scraping.")
                                            should_continue = False
                                            break

                                    if extracted_data['date_expires'] != 'Not specified':
                                        if not self.is_not_expired(extracted_data['date_expires']):
                                            self.logger.info(f"Expired job detected: {job_title}. Stopping page scraping.")
                                            should_continue = False
                                            break

                                    page_jobs.append(extracted_data)

                                    if self.is_recent_job(extracted_data['date_posted'], extracted_data['date_expires']) and self.is_not_expired(extracted_data['date_expires']):
                                        self.duplicate_urls.add(job_link)
                                        self.save_job_data(extracted_data)
                                        jobs.append(extracted_data)

                            except Exception as e:
                                self.logger.error(f"Error processing MyJobMag job: {str(e)}")
                                continue

                        if not should_continue:
                            break

                        if page_jobs:
                            should_continue = self.should_continue_to_next_page(page_jobs)
                            if not should_continue:
                                self.logger.info(f"Stopping pagination for '{keyword}' - older jobs detected on page {page}")

                        if should_continue:
                            try:
                                self.driver.back()
                                time.sleep(2)
                                next_page_link = self.driver.find_element(
                                    By.XPATH, f"//a[@href='/page/{page + 1}' or contains(text(), '{page + 1}')]"
                                )
                                self.safe_click(next_page_link)
                                time.sleep(3)
                                page += 1
                            except Exception:
                                should_continue = False

                except Exception as e:
                    self.logger.error(f"Error searching MyJobMag for '{keyword}': {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in MyJobMag scraping: {str(e)}")

        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()

        self.logger.info(f"MyJobMag scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    def extract_myjobmag_job_details(self, job_title: str, job_link: str) -> Optional[Dict]:
        """Extract detailed job information from MyJobMag job page"""
        try:
            job_data = {
                'job_title': job_title,
                'link': job_link,
                'date_posted': 'Not specified',
                'date_expires': 'Not specified',
                'qualification': 'Not specified',
                'years_of_experience': 'Not specified',
                'location': 'Not specified',
                'source': 'MyJobMag Kenya'
            }

            try:
                posted_elem = self.driver.find_element(By.ID, "posted-date")
                posted_text = posted_elem.text
                if 'Posted:' in posted_text:
                    job_data['date_posted'] = posted_text.split('Posted:')[1].strip()
            except Exception:
                try:
                    posted_elem = self.driver.find_element(
                        By.XPATH, "//div[contains(@class, 'read-date-sec-li') and contains(text(), 'Posted')]"
                    )
                    posted_text = posted_elem.text
                    if 'Posted:' in posted_text:
                        job_data['date_posted'] = posted_text.split('Posted:')[1].strip()
                except Exception:
                    pass

            try:
                deadline_elem = self.driver.find_element(
                    By.XPATH, "//div[@class='read-date-sec-li']//b[contains(text(), 'Deadline:')]//parent::div"
                )
                deadline_text = deadline_elem.text
                if 'Deadline:' in deadline_text:
                    job_data['date_expires'] = deadline_text.split('Deadline:')[1].strip()
            except Exception:
                pass

            try:
                qual_links = self.driver.find_elements(By.XPATH, "//span[@class='jkey-info']//a[contains(@href, '/jobs-by-education/')]")
                qualifications = [link.text.strip() for link in qual_links]
                if qualifications:
                    job_data['qualification'] = ', '.join(qualifications)
            except Exception:
                pass

            try:
                exp_elem = self.driver.find_element(
                    By.XPATH, "//span[@class='jkey-title' and text()='Experience']/following-sibling::span[@class='jkey-info']"
                )
                job_data['years_of_experience'] = exp_elem.text.strip()
            except Exception:
                pass

            try:
                location_elem = self.driver.find_element(
                    By.XPATH, "//span[@class='jkey-title' and text()='Location']/following-sibling::span//a"
                )
                job_data['location'] = location_elem.text.strip()
            except Exception:
                pass

            return job_data

        except Exception as e:
            self.logger.error(f"Error extracting MyJobMag job details: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # BRIGHTERMONDAY  (rewritten)
    # ------------------------------------------------------------------
    # The old version hunted for a search box across many keyword loops and
    # regularly hit ElementNotInteractableException, because the box was
    # sometimes present in the DOM but covered/animated/not yet hydrated.
    # Navigating straight to a keyword-scoped URL sidesteps that entire
    # failure class; is_relevant_job() still filters whatever comes back.
    def scrape_brightermonday(self) -> List[Dict]:
        """Scrape jobs from BrighterMonday Kenya"""
        jobs = []
        self.logger.info("Starting BrighterMonday scraping...")

        try:
            cache_key = self.get_cache_key_with_config("brightermonday")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached BrighterMonday data ({len(cached_jobs)} jobs)")
                return cached_jobs

            self.setup_driver()
            keywords_to_use = self.search_keywords

            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching BrighterMonday for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")

                    search_url = f"https://www.brightermonday.co.ke/jobs?q={quote_plus(keyword)}"
                    self.driver.get(search_url)
                    time.sleep(4)
                    self.handle_popups()

                    job_selectors = [
                        "//a[contains(@href, '/listings/')]",
                        "//a[contains(@href, '/job/')]",
                        "//h3//a | //h2//a",
                    ]

                    job_elements = []
                    for selector in job_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except Exception:
                            continue

                    self.logger.info(f"Found {len(job_elements)} potential job elements for '{keyword}'")

                    for i, job_element in enumerate(job_elements[:10]):
                        try:
                            job_link = job_element.get_attribute('href')
                            if not job_link or job_link in self.duplicate_urls:
                                continue

                            job_title = self.get_element_text(job_element)
                            if not job_title or not self.is_relevant_job(job_title):
                                continue

                            job_data = {
                                'job_title': job_title,
                                'link': job_link,
                                'date_posted': 'Recently posted',
                                'date_expires': 'Not specified',
                                'qualification': 'Not specified',
                                'years_of_experience': 'Not specified',
                                'location': 'Kenya',
                                'source': 'BrighterMonday Kenya'
                            }

                            self.duplicate_urls.add(job_link)
                            self.save_job_data(job_data)
                            jobs.append(job_data)

                        except Exception as e:
                            self.logger.error(f"Error processing BrighterMonday job {i+1}: {str(e)}")
                            continue

                except Exception as e:
                    self.logger.error(f"Error searching BrighterMonday for '{keyword}': {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in BrighterMonday scraping: {str(e)}")

        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()

        self.logger.info(f"BrighterMonday scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    # ------------------------------------------------------------------
    # FUZU  (rewritten again - see note)
    # ------------------------------------------------------------------
    # Two runs of real logs now show Fuzu's own search box/URL filter does
    # not reliably change what's on the page (100+ "potential" elements
    # every single keyword, 0 ever relevant - across two different search
    # strategies). Rather than keep chasing a moving, unreliable client-side
    # search, this scans the general/paginated job feed directly and runs
    # our own is_relevant_job() filter across it once - faster (one pass
    # instead of 12 searches) and independent of whatever Fuzu's search box
    # is doing. get_richest_text_by_href() also fixes the blank-title cause:
    # each job card wraps several overlapping <a href="/job/..."> elements
    # (title, apply button, bookmark icon...) all pointing at the same URL;
    # picking whichever has the most text reliably lands on the title link.
    def scrape_fuzu(self, max_pages: int = 4) -> List[Dict]:
        """Scrape jobs from Fuzu Kenya by scanning its general job feed"""
        jobs = []
        self.logger.info("Starting Fuzu scraping...")

        try:
            cache_key = self.get_cache_key_with_config("fuzu")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached Fuzu data ({len(cached_jobs)} jobs)")
                return cached_jobs

            self.setup_driver()

            self.logger.info("Navigating to Fuzu Kenya...")
            self.driver.get("https://www.fuzu.com/kenya/job")
            time.sleep(5)

            if not self.handle_human_verification():
                self.logger.error("Failed to complete human verification for Fuzu")
                return jobs

            self.handle_popups()
            time.sleep(3)

            job_selectors = [
                "//a[contains(@href, '/job/')]",
                "//div[contains(@class, 'job')]//a",
                "//h2//a | //h3//a",
            ]

            for page_num in range(1, max_pages + 1):
                try:
                    if page_num > 1:
                        self.driver.get(f"https://www.fuzu.com/kenya/job?page={page_num}")
                        time.sleep(4)
                        self.handle_popups()

                    job_elements = []
                    for selector in job_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except Exception:
                            continue

                    if not job_elements:
                        self.logger.info(f"Fuzu page {page_num}: no job elements found - stopping pagination")
                        break

                    candidates = self.get_richest_text_by_href(job_elements)
                    self.logger.info(f"Fuzu page {page_num}: {len(candidates)} unique job links found")

                    saved_this_page = 0
                    for job_link, job_title in candidates.items():
                        try:
                            if job_link in self.duplicate_urls:
                                continue
                            if not job_title or not self.is_relevant_job(job_title):
                                continue

                            job_data = {
                                'job_title': job_title,
                                'link': job_link,
                                'date_posted': 'Not specified',
                                'date_expires': 'Not specified',
                                'qualification': 'Not specified',
                                'years_of_experience': 'Not specified',
                                'location': 'Not specified',
                                'source': 'Fuzu'
                            }

                            self.duplicate_urls.add(job_link)
                            self.save_job_data(job_data)
                            jobs.append(job_data)
                            saved_this_page += 1

                        except Exception as e:
                            self.logger.error(f"Error processing Fuzu job: {str(e)}")
                            continue

                    self.logger.info(f"Fuzu page {page_num}: saved {saved_this_page} new relevant job(s)")

                    # Fuzu's feed isn't keyword-sorted, so an empty page doesn't
                    # necessarily mean later pages are empty too - but bail out
                    # after two quiet pages in a row to avoid scanning forever.
                    if saved_this_page == 0 and page_num >= 2:
                        break

                except Exception as e:
                    self.logger.error(f"Error scraping Fuzu page {page_num}: {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in Fuzu scraping: {str(e)}")

        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()

        self.logger.info(f"Fuzu scraping completed. Found {len(jobs)} relevant jobs")
        return jobs


    # ------------------------------------------------------------------
    # CAREERPOINT KENYA  (fixed)
    # ------------------------------------------------------------------
    # The old version never actually searched the site - it just re-read
    # whatever links happened to be on the homepage / "Browse Latest Jobs"
    # page and filtered those, which is why every keyword returned 0
    # results. CareerPoint Kenya is WordPress, so its native `?s=` search
    # endpoint is used instead.
    def scrape_careerpointkenya(self) -> List[Dict]:
        """Scrape jobs from CareerPoint Kenya using its WordPress search"""
        jobs = []
        self.logger.info("Starting CareerPoint Kenya scraping...")

        try:
            cache_key = self.get_cache_key_with_config("careerpointkenya")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached CareerPoint data ({len(cached_jobs)} jobs)")
                return cached_jobs

            self.setup_driver()
            keywords_to_use = self.search_keywords

            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching CareerPoint for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")

                    search_url = f"https://www.careerpointkenya.co.ke/?s={quote_plus(keyword)}"
                    self.driver.get(search_url)
                    time.sleep(3)
                    self.handle_popups()

                    listing_selectors = [
                        "//article//h1[contains(@class,'entry-title')]//a",
                        "//article//h2[contains(@class,'entry-title')]//a",
                        "//h1[contains(@class,'entry-title')]//a",
                        "//h2[contains(@class,'entry-title')]//a",
                        "//article//h2//a",
                        "//article//h3//a",
                        "//a[contains(@href, '/20') and contains(@href, '-job')]",
                        "//a[contains(@href, '/20') and string-length(@href) > 45]",
                    ]

                    job_elements = []
                    for selector in listing_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except Exception:
                            continue

                    if not job_elements:
                        # Could be a genuine "no matches" or the page simply
                        # failing to load (e.g. an SSL handshake error on a
                        # restrictive network). One retry, then log enough to
                        # tell the two apart.
                        time.sleep(3)
                        self.driver.get(search_url)
                        time.sleep(3)
                        for selector in listing_selectors:
                            try:
                                elements = self.driver.find_elements(By.XPATH, selector)
                                if elements:
                                    job_elements = elements
                                    break
                            except Exception:
                                continue
                        if not job_elements:
                            self.logger.info(
                                f"CareerPoint: still 0 candidates after retry - "
                                f"page title was '{self.driver.title}' at {self.driver.current_url}"
                            )

                    self.logger.info(f"Found {len(job_elements)} candidate listings for '{keyword}'")

                    saved_this_keyword = 0
                    for job_element in job_elements[:8]:
                        try:
                            job_link = job_element.get_attribute('href')
                            if not job_link or job_link in self.duplicate_urls:
                                continue

                            job_title = self.get_element_text(job_element)
                            if not job_title or not self.is_relevant_job(job_title):
                                continue

                            date_posted = 'Not specified'
                            try:
                                container = job_element.find_element(By.XPATH, "./ancestor::article")
                                date_elem = container.find_element(By.XPATH, ".//time")
                                date_posted = self.get_element_text(date_elem) or 'Not specified'
                            except Exception:
                                pass

                            if date_posted != 'Not specified' and not self.is_recent_job(date_posted):
                                continue

                            job_data = {
                                'job_title': job_title,
                                'link': job_link,
                                'date_posted': date_posted,
                                'date_expires': 'Not specified',
                                'qualification': 'Not specified',
                                'years_of_experience': 'Not specified',
                                'location': 'Not specified',
                                'source': 'CareerPoint Kenya'
                            }

                            self.duplicate_urls.add(job_link)
                            self.save_job_data(job_data)
                            jobs.append(job_data)
                            saved_this_keyword += 1

                        except Exception as e:
                            self.logger.error(f"Error processing CareerPoint job: {str(e)}")
                            continue

                    self.logger.info(f"CareerPoint: saved {saved_this_keyword} new relevant job(s) for '{keyword}'")

                except Exception as e:
                    self.logger.error(f"Error searching CareerPoint for '{keyword}': {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in CareerPoint scraping: {str(e)}")

        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()

        self.logger.info(f"CareerPoint scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    # ------------------------------------------------------------------
    # MYJOBSINKENYA  (rewritten again - see note)
    # ------------------------------------------------------------------
    # The real-run log shows the exact same "14 job listings" on every
    # single one of the 12 keyword searches - a strong sign the search
    # box was never actually filtering anything, so is_relevant_job() was
    # correctly rejecting the same 14 generic (non-data) jobs 12 times
    # over. Same fix as Fuzu: stop trusting the client-side search and
    # scan the naturally-loaded listing page(s) directly, filtering with
    # is_relevant_job() once.
    def scrape_myjobsinkenya(self, max_pages: int = 3) -> List[Dict]:
        """Scrape jobs from MyJobsInKenya by scanning its listing pages"""
        jobs = []
        self.logger.info("Starting MyJobsInKenya scraping...")

        try:
            cache_key = self.get_cache_key_with_config("myjobsinkenya")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached MyJobsInKenya data ({len(cached_jobs)} jobs)")
                return cached_jobs

            self.setup_driver()

            job_selectors = [
                "//a[contains(@href, '/jobs/') and contains(@href, '/view')]",
                "//a[contains(@href, '/job/')]",
                "//div[contains(@class, 'job')]//a",
                "//h2//a | //h3//a"
            ]

            for page_num in range(1, max_pages + 1):
                try:
                    url = "https://www.myjobsinkenya.com/"
                    if page_num > 1:
                        url = f"https://www.myjobsinkenya.com/?page={page_num}"
                    self.driver.get(url)
                    time.sleep(4)
                    self.handle_popups()

                    job_elements = []
                    for selector in job_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except Exception:
                            continue

                    if not job_elements:
                        self.logger.info(f"MyJobsInKenya page {page_num}: no listings found - stopping pagination")
                        break

                    candidates = self.get_richest_text_by_href(job_elements)
                    self.logger.info(f"MyJobsInKenya page {page_num}: {len(candidates)} unique job links found")

                    saved_this_page = 0
                    for job_link, job_title in candidates.items():
                        try:
                            if job_link in self.duplicate_urls:
                                continue
                            if not job_title or not self.is_relevant_job(job_title):
                                continue

                            job_data = {
                                'job_title': job_title,
                                'link': job_link,
                                'date_posted': 'Recently posted',
                                'date_expires': 'Not specified',
                                'qualification': 'Not specified',
                                'years_of_experience': 'Not specified',
                                'location': 'Kenya',
                                'source': 'MyJobsInKenya'
                            }

                            self.duplicate_urls.add(job_link)
                            self.save_job_data(job_data)
                            jobs.append(job_data)
                            saved_this_page += 1

                        except Exception as e:
                            self.logger.error(f"Error processing MyJobsInKenya job: {str(e)}")
                            continue

                    self.logger.info(f"MyJobsInKenya page {page_num}: saved {saved_this_page} new relevant job(s)")

                    if saved_this_page == 0 and page_num >= 2:
                        break

                except Exception as e:
                    self.logger.error(f"Error scraping MyJobsInKenya page {page_num}: {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in MyJobsInKenya scraping: {str(e)}")

        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()

        self.logger.info(f"MyJobsInKenya scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    # ------------------------------------------------------------------
    # HISTORICAL DATA  (v22)
    # ------------------------------------------------------------------
    # Every run writes a single kenya_jobs_YYYY-MM-DD.json snapshot. On its
    # own that only shows *today*. To power a real "hiring trend over time"
    # chart and week-over-week KPIs, this reads every snapshot ever saved
    # in the folder, tags any job missing date_scraped with the date from
    # its filename (so old pre-v22 files still work), and de-duplicates by
    # link. No database needed - the daily JSON files already are one.
    def load_historical_jobs(self) -> List[Dict]:
        pattern = os.path.join(self.save_path, "kenya_jobs_*.json")
        all_jobs: Dict[str, Dict] = {}

        for filepath in sorted(glob.glob(pattern)):
            filename = os.path.basename(filepath)
            date_match = re.search(r'kenya_jobs_(\d{4}-\d{2}-\d{2})\.json', filename)
            file_date = date_match.group(1) if date_match else None

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    jobs = json.load(f)
            except Exception as e:
                self.logger.warning(f"Could not read historical file {filename}: {str(e)}")
                continue

            for job in jobs:
                link = job.get('link')
                title = (job.get('job_title') or '').strip()
                if not link or not title:
                    continue
                if 'date_scraped' not in job:
                    job = dict(job)
                    job['date_scraped'] = file_date or self.today.isoformat()
                    job.setdefault('city', self._extract_city(job.get('location', '')))
                    job.setdefault('title_bucket', self.bucket_job_title(title))
                # Keep the earliest-seen record for a given link so a job
                # doesn't get double counted across multiple daily files.
                if link not in all_jobs:
                    all_jobs[link] = job

        return list(all_jobs.values())

    # ------------------------------------------------------------------
    # DASHBOARD  (complete visual rebuild - navy/blue, data-professional
    # styling; see DASHBOARD_TEMPLATE below the class for the markup)
    # ------------------------------------------------------------------
    @staticmethod
    def _escape_html(value) -> str:
        return (
            str(value)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
        )

    def _render_job_rows(self, jobs: List[Dict]) -> str:
        """Build the <tr> rows for the dashboard table, skipping any job
        that somehow still has a blank title (defensive - shouldn't happen
        now that save_job_data() and every scraper filter these out).

        v22 adds conditional formatting: a "New today" pill for jobs
        scraped today, an amber "Expiring soon" pill for jobs whose
        deadline is within 3 days, and a small quality dot (green/amber/
        red) reflecting how complete the listing is."""
        palette = ["#3B82F6", "#22D3EE", "#818CF8", "#38BDF8", "#2DD4BF", "#60A5FA", "#F2B84B"]
        seen_sources: List[str] = []
        rows = []
        esc = self._escape_html

        for job in jobs:
            title = (job.get('job_title') or '').strip()
            if not title:
                continue

            source = job.get('source') or 'Unknown'
            if source not in seen_sources:
                seen_sources.append(source)
            color = palette[seen_sources.index(source) % len(palette)]

            location = job.get('location') or 'Not specified'
            posted = job.get('date_posted') or 'Not specified'
            expires = job.get('date_expires') or 'Not specified'
            qualification = job.get('qualification') or 'Not specified'
            link = job.get('link') or '#'
            quality = job.get('quality_score')
            if quality is None:
                quality = self._compute_quality_score(job)

            quality_class = 'q-high' if quality >= 70 else ('q-mid' if quality >= 40 else 'q-low')

            flags = ""
            if job.get('date_scraped') == self.today.isoformat():
                flags += '<span class="flag flag-new">New today</span>'
            expire_dt = self.parse_date(expires) if expires not in ('Not specified', 'Unknown') else None
            if expire_dt:
                days_left = (expire_dt.date() - self.today).days
                if 0 <= days_left <= 3:
                    flags += '<span class="flag flag-warn">Expiring soon</span>'

            rows.append(f"""<tr data-source="{esc(source)}" data-location="{esc(location)}" data-title="{esc(title.lower())}" data-quality="{quality}" data-new="{1 if 'flag-new' in flags else 0}">
<td class="cell-title">{esc(title)}{flags}</td>
<td><span class="badge" style="--badge-color:{color}"><span class="badge-dot"></span>{esc(source)}</span></td>
<td class="cell-muted">{esc(location)}</td>
<td class="cell-date" data-raw="{esc(posted)}">{esc(posted)}</td>
<td class="cell-date">{esc(expires)}</td>
<td class="cell-muted">{esc(qualification)}</td>
<td><span class="quality-dot {quality_class}" title="Listing completeness: {quality}/100"></span>{quality}</td>
<td><a href="{esc(link)}" target="_blank" rel="noopener" class="apply-link">Apply<svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2.5 9.5L9.5 2.5M9.5 2.5H4.5M9.5 2.5V7.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></a></td>
</tr>""")

        return "".join(rows)

    def _render_calendar_heatmap(self, hist_df: pd.DataFrame) -> str:
        """Build a lightweight 5-week x 7-day calendar heatmap as plain
        HTML/CSS grid cells (no Chart.js plugin dependency - one less thing
        that can fail to load). Cells are shaded relative to the busiest
        day seen in the window."""
        counts_by_date = hist_df.groupby('date_scraped').size().to_dict() if len(hist_df) else {}

        end = self.today
        start = end - timedelta(days=34)          # ~5 weeks back
        start -= timedelta(days=start.weekday())  # align to a Monday

        days = []
        cursor = start
        while cursor <= end:
            days.append(cursor)
            cursor += timedelta(days=1)

        max_count = max(counts_by_date.values(), default=0) or 1
        esc = self._escape_html
        cells = []
        for d in days:
            key = d.isoformat()
            count = int(counts_by_date.get(key, 0))
            if d > end:
                cells.append('<div class="cal-cell cal-future"></div>')
                continue
            if count == 0:
                cells.append(f'<div class="cal-cell" title="{esc(d.strftime("%a, %b %d"))}: 0 jobs"></div>')
                continue
            intensity = min(1.0, 0.25 + 0.75 * (count / max_count))
            cells.append(
                f'<div class="cal-cell" style="--cal-alpha:{intensity:.2f}" '
                f'title="{esc(d.strftime("%a, %b %d"))}: {count} job(s)"></div>'
            )
        return "".join(cells)

    def generate_dashboard(self):
        """Generate a professional, navy-blue interactive analytics dashboard.

        KPIs and the trend/title/day-of-week/quality charts are computed
        from load_historical_jobs() (every daily snapshot ever saved in this
        folder), so they get more meaningful as the scraper accumulates
        days of data. The source/location charts and the results table stay
        scoped to *this run* (self.jobs_data), matching what a person
        expects to review right after clicking "Run scraper"."""
        try:
            if not self.jobs_data:
                if os.path.exists(self.json_filename):
                    with open(self.json_filename, 'r', encoding='utf-8') as f:
                        self.jobs_data = json.load(f)

            # Blank-title rows are junk data (a symptom of the old Fuzu bug) -
            # keep them out of the dashboard even if they somehow made it
            # into the JSON from an earlier run. Also backfill v22 fields
            # for any job that predates this version (e.g. re-generating a
            # dashboard from an older JSON file).
            valid_jobs = []
            for j in self.jobs_data:
                if not (j.get('job_title') or '').strip():
                    continue
                if 'quality_score' not in j:
                    j = self.enrich_job_data(dict(j))
                valid_jobs.append(j)

            if not valid_jobs:
                self.logger.warning("No job data available for dashboard")
                return False

            today_df = pd.DataFrame(valid_jobs)

            # ---------------- historical (all-time) dataset ----------------
            historical_jobs = self.load_historical_jobs()
            if not historical_jobs:
                historical_jobs = valid_jobs
            hist_df = pd.DataFrame(historical_jobs)
            for col, default in [
                ('city', 'Not specified'), ('title_bucket', 'Other'),
                ('day_of_week', ''), ('date_scraped', self.today.isoformat()),
                ('quality_score', 0), ('source', 'Unknown'),
            ]:
                if col not in hist_df.columns:
                    hist_df[col] = default
            hist_df['quality_score'] = pd.to_numeric(hist_df['quality_score'], errors='coerce').fillna(0)

            snapshot_count = len(glob.glob(os.path.join(self.save_path, "kenya_jobs_*.json"))) or 1

            # ---------------- KPIs ----------------
            total_jobs = len(hist_df)
            today_str = self.today.isoformat()
            week_ago_str = (self.today - timedelta(days=7)).isoformat()
            new_today = int((hist_df['date_scraped'] == today_str).sum())
            new_this_week = int((hist_df['date_scraped'] >= week_ago_str).sum())
            job_boards = int(hist_df['source'].nunique())
            cities_series = hist_df['city'][hist_df['city'] != 'Not specified']
            cities_covered = int(cities_series.nunique())
            avg_quality = round(hist_df['quality_score'].mean()) if total_jobs else 0

            # ---------------- this run: source / location ----------------
            sources = today_df['source'].value_counts().to_dict()
            locations_series = today_df['location'][today_df['location'] != 'Not specified']
            top_locations = locations_series.value_counts().head(6).to_dict()

            # ---------------- trend: jobs scraped per day (last 30 days) ----------------
            daily_counts = hist_df.groupby('date_scraped').size().sort_index().tail(30)
            trend_labels = [str(d) for d in daily_counts.index]
            trend_values = [int(v) for v in daily_counts.values]

            # ---------------- day-of-week distribution ----------------
            dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            dow_counts_raw = hist_df['day_of_week'].value_counts().to_dict()
            dow_values = [int(dow_counts_raw.get(d, 0)) for d in dow_order]
            dow_labels = [d[:3] for d in dow_order]

            # ---------------- top job titles (bucketed) ----------------
            bucket_counts = hist_df['title_bucket'].value_counts()
            named_buckets = bucket_counts[bucket_counts.index != 'Other']
            title_counts = named_buckets.head(8) if not named_buckets.empty else bucket_counts.head(8)
            title_labels = list(title_counts.index)
            title_values = [int(v) for v in title_counts.values]

            # ---------------- source quality ----------------
            src_quality = (
                hist_df.groupby('source')['quality_score']
                .mean().round().astype(int)
                .sort_values(ascending=False)
            )
            srcq_labels = list(src_quality.index)
            srcq_values = [int(v) for v in src_quality.values]

            # ---------------- calendar heatmap ----------------
            calendar_cells = self._render_calendar_heatmap(hist_df)

            job_rows_html = self._render_job_rows(valid_jobs)

            source_options = "".join(
                f'<option value="{self._escape_html(s)}">{self._escape_html(s)} ({c})</option>'
                for s, c in sorted(sources.items(), key=lambda x: -x[1])
            )
            location_options = "".join(
                f'<option value="{self._escape_html(loc)}">{self._escape_html(loc)}</option>'
                for loc in sorted(top_locations.keys())
            )

            replacements = {
                '__TOTAL_JOBS__': f"{total_jobs:,}",
                '__NEW_TODAY__': f"{new_today:,}",
                '__NEW_WEEK__': f"{new_this_week:,}",
                '__SOURCE_COUNT__': str(job_boards),
                '__CITIES_COVERED__': str(cities_covered),
                '__AVG_QUALITY__': str(avg_quality),
                '__TOTAL_ROWS__': str(len(valid_jobs)),
                '__GENERATED_AT__': datetime.now().strftime('%B %d, %Y \u00b7 %I:%M %p'),
                '__DASHBOARD_DATE__': str(self.today),
                '__JOB_ROWS__': job_rows_html,
                '__SOURCE_OPTIONS__': source_options,
                '__LOCATION_OPTIONS__': location_options,
                '__SOURCE_LABELS_JSON__': json.dumps(list(sources.keys())),
                '__SOURCE_COUNTS_JSON__': json.dumps([int(v) for v in sources.values()]),
                '__LOCATION_LABELS_JSON__': json.dumps(list(top_locations.keys())),
                '__LOCATION_COUNTS_JSON__': json.dumps([int(v) for v in top_locations.values()]),
                '__TREND_LABELS_JSON__': json.dumps(trend_labels),
                '__TREND_VALUES_JSON__': json.dumps(trend_values),
                '__DOW_LABELS_JSON__': json.dumps(dow_labels),
                '__DOW_VALUES_JSON__': json.dumps(dow_values),
                '__TITLE_LABELS_JSON__': json.dumps(title_labels),
                '__TITLE_VALUES_JSON__': json.dumps(title_values),
                '__SRCQ_LABELS_JSON__': json.dumps(srcq_labels),
                '__SRCQ_VALUES_JSON__': json.dumps(srcq_values),
                '__CALENDAR_CELLS__': calendar_cells,
                '__CSV_FILENAME__': f"kenya_jobs_{self.today}.csv",
                '__XLSX_FILENAME__': f"kenya_jobs_{self.today}.xlsx",
                '__HISTORY_FILE_COUNT__': str(snapshot_count),
                '__RUN_STATUS_DEFAULT__': "Click to re-scrape all sources (needs dashboard_server.py running).",
            }

            html_content = DASHBOARD_TEMPLATE
            for token, value in replacements.items():
                html_content = html_content.replace(token, value)

            with open(self.dashboard_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.logger.info(f"Interactive dashboard generated: {self.dashboard_filename}")
            return True

        except Exception as e:
            self.logger.error(f"Error generating dashboard: {str(e)}")
            return False

    def run(self):
        """Main method to run the scraper with comprehensive reporting"""
        self.logger.info("=== Kenya Job Scraper v22 Started ===")
        start_time = datetime.now()
        initial_job_count = len(self.jobs_data)

        try:
            print("Kenya Job Scraper v22 - Analytics Edition")
            print(f"Date: {self.today}")
            print(f"Save Path: {self.save_path}")
            print(f"Keywords to search: {len(self.search_keywords)}")
            print(f"Existing jobs: {initial_job_count}")
            print(f"Run Config: {self.current_run_config[:8]}...")
            print("-" * 60)

            scraping_results = {}

            try:
                print("Scraping MyJobMag...")
                myjobmag_jobs = self.scrape_myjobmag()
                scraping_results['MyJobMag'] = len(myjobmag_jobs)
                print(f"  MyJobMag: {len(myjobmag_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"MyJobMag failed: {str(e)}")
                scraping_results['MyJobMag'] = 0
                print("  MyJobMag: Failed")

            try:
                print("Scraping BrighterMonday...")
                brightermonday_jobs = self.scrape_brightermonday()
                scraping_results['BrighterMonday'] = len(brightermonday_jobs)
                print(f"  BrighterMonday: {len(brightermonday_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"BrighterMonday failed: {str(e)}")
                scraping_results['BrighterMonday'] = 0
                print("  BrighterMonday: Failed")

            try:
                print("Scraping Fuzu...")
                fuzu_jobs = self.scrape_fuzu()
                scraping_results['Fuzu'] = len(fuzu_jobs)
                print(f"  Fuzu: {len(fuzu_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"Fuzu failed: {str(e)}")
                scraping_results['Fuzu'] = 0
                print("  Fuzu: Failed")

            try:
                print("Scraping CareerPoint Kenya...")
                careerpointkenya_jobs = self.scrape_careerpointkenya()
                scraping_results['CareerPoint Kenya'] = len(careerpointkenya_jobs)
                print(f"  CareerPoint Kenya: {len(careerpointkenya_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"CareerPoint Kenya failed: {str(e)}")
                scraping_results['CareerPoint Kenya'] = 0
                print("  CareerPoint Kenya: Failed")

            try:
                print("Scraping MyJobsInKenya...")
                myjobsinkenya_jobs = self.scrape_myjobsinkenya()
                scraping_results['MyJobsInKenya'] = len(myjobsinkenya_jobs)
                print(f"  MyJobsInKenya: {len(myjobsinkenya_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"MyJobsInKenya failed: {str(e)}")
                scraping_results['MyJobsInKenya'] = 0
                print("  MyJobsInKenya: Failed")

            dashboard_created = False
            try:
                print("Generating dashboard...")
                dashboard_created = self.generate_dashboard()
                if dashboard_created:
                    print(f"  Dashboard: {os.path.basename(self.dashboard_filename)}")
                else:
                    print("  Dashboard: Failed to generate")
            except Exception as e:
                self.logger.error(f"Dashboard generation failed: {str(e)}")
                print("  Dashboard: Error occurred")

            new_jobs_count = len(self.jobs_data) - initial_job_count
            total_time = datetime.now() - start_time

            print("\n" + "=" * 70)
            print("SCRAPING RESULTS")
            print("=" * 70)
            print(f"Jobs in database: {len(self.jobs_data)}")
            print(f"New jobs added:   {new_jobs_count}")
            print(f"Time taken:       {total_time}")
            success_rate = sum(1 for c in scraping_results.values() if c > 0) / len(scraping_results) * 100
            print(f"Success rate:     {success_rate:.1f}%")

            print("\nRESULTS BY SOURCE:")
            for source, count in scraping_results.items():
                status = "OK" if count > 0 else "--"
                print(f"   [{status}] {source:<20}: {count:>3} jobs")

            print("\nFILES GENERATED:")
            print(f"   JSON: {os.path.basename(self.json_filename)}")
            print(f"   CSV:  {os.path.basename(self.csv_filename)}")
            if dashboard_created:
                print(f"   Dashboard: {os.path.basename(self.dashboard_filename)}")

            print("\nFULL FILE PATHS:")
            print(f"   JSON: {self.json_filename}")
            print(f"   CSV:  {self.csv_filename}")
            if dashboard_created:
                print(f"   HTML: {self.dashboard_filename}")
                print("\nTo view the dashboard, open the HTML file in your browser.")

            if new_jobs_count > 0:
                print(f"\nNEW JOBS FOUND ({new_jobs_count} total, showing up to 5):")
                recent_jobs = self.jobs_data[-new_jobs_count:]
                for i, job in enumerate(recent_jobs[:5], 1):
                    print(f"   {i}. {job.get('job_title', 'N/A')}")
                    print(f"      Source: {job.get('source', 'N/A')}")
                    if job.get('date_posted') != 'Not specified':
                        print(f"      Posted: {job.get('date_posted')}")
                    if job.get('location') != 'Not specified':
                        print(f"      Location: {job.get('location')}")
                if new_jobs_count > 5:
                    print(f"   ... and {new_jobs_count - 5} more jobs")
            else:
                print("\nNO NEW JOBS FOUND")
                print("   Possible reasons:")
                print("   - All recent jobs are already in today's database")
                print("   - No jobs matched the keywords in the last 7 days")
                print("   - A site changed its layout - check the log file for details")

            print(f"\nCache entries: {len(self.cache)}")
            print(f"Run config:    {self.current_run_config[:12]}...")

        except Exception as e:
            self.logger.error(f"Error in main execution: {str(e)}")
            print(f"Fatal error: {str(e)}")
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")

        self.logger.info("=== Kenya Job Scraper v22 Finished ===")


# ==========================================================================
# DASHBOARD TEMPLATE (navy-blue, data/fintech-inspired professional design)
# ==========================================================================
# Deliberately NOT an f-string - it is a plain triple-quoted string with
# __TOKEN__ placeholders swapped in via str.replace() in generate_dashboard().
# That keeps every literal `{` and `}` in the CSS/JS safe, with zero risk of
# the escaping mistakes that come with giant f-string HTML templates.

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kenya Data Jobs &middot; __DASHBOARD_DATE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script>
  /* Set the theme before first paint so there's no flash of the wrong
     theme. Falls back to the OS preference, then dark. */
  (function () {
    var saved = null;
    try { saved = localStorage.getItem('kdj-theme'); } catch (e) {}
    var theme = saved || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.setAttribute('data-theme', theme);
  })();
</script>
<style>
:root{
  --font-body:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --radius-lg:14px;
  --radius-md:12px;
  --radius-sm:10px;

  --green-950:#0F7300;
  --green-900:#128A00;
  --green-700:#14A800;
  --green-500:#8EDB7D;
  --green-300:#CFF2C8;
  --green-100:#EAF9E7;

  --warning:#F59E0B;
  --error:#DC2626;
  --info:#2563EB;
}

[data-theme="dark"]{
  --bg:#121212;
  --bg-secondary:#1A1A1A;
  --card:#222222;
  --card-alt:#1c1c1c;
  --border:#2F2F2F;
  --border-soft:rgba(255,255,255,0.06);
  --text-primary:#F5F5F5;
  --text-secondary:#B3B3B3;
  --text-muted:#8A8A8A;
  --accent:#14A800;
  --accent-hover:#128A00;
  --accent-active:#0F7300;
  --accent-tint:rgba(20,168,0,0.14);
  --shadow-card:0 8px 24px rgba(0,0,0,0.35);
  --chart-grid:rgba(255,255,255,0.08);
}
[data-theme="light"]{
  --bg:#F8F9FA;
  --bg-secondary:#F1F3F5;
  --card:#FFFFFF;
  --card-alt:#FAFBFC;
  --border:#E5E7EB;
  --border-soft:rgba(31,41,55,0.06);
  --text-primary:#1F2937;
  --text-secondary:#6B7280;
  --text-muted:#9CA3AF;
  --accent:#14A800;
  --accent-hover:#128A00;
  --accent-active:#0F7300;
  --accent-tint:#EAF9E7;
  --shadow-card:0 4px 18px rgba(31,41,55,0.08);
  --chart-grid:rgba(31,41,55,0.08);
}

*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{
  margin:0;
  font-family:var(--font-body);
  background:var(--bg);
  color:var(--text-primary);
  padding:32px 20px 64px;
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
  transition:background .15s ease, color .15s ease;
}
a{color:inherit;}
.shell{max-width:1320px;margin:0 auto;}

/* ---------- header ---------- */
.topbar{
  display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:16px;
  padding-bottom:26px;
  border-bottom:1px solid var(--border-soft);
  margin-bottom:28px;
}
.brand{display:flex;align-items:center;gap:14px;}
.brand-mark{
  width:42px;height:42px;border-radius:12px;flex:none;
  background:linear-gradient(135deg,var(--green-700),var(--green-500));
  position:relative;
}
.brand-mark::before{
  content:"";position:absolute;inset:9px;
  border-radius:5px;background:var(--bg);
}
.brand-mark::after{
  content:"";position:absolute;inset:15px;
  border-radius:3px;background:var(--green-700);
}
.brand h1{
  font-size:1.45rem;font-weight:700;letter-spacing:-0.01em;
  margin:0;color:var(--text-primary);
}
.brand p{margin:2px 0 0;font-size:0.85rem;color:var(--text-secondary);}
.meta{
  display:flex;align-items:center;gap:12px;
  flex-wrap:wrap;
}
.meta-updated{
  display:flex;align-items:center;gap:9px;
  font-size:0.82rem;color:var(--text-secondary);
}
.live-dot{
  width:8px;height:8px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 0 0 var(--accent-tint);
  animation:pulse 2.2s infinite;
}
@keyframes pulse{
  0%{box-shadow:0 0 0 0 rgba(20,168,0,0.45);}
  70%{box-shadow:0 0 0 8px rgba(20,168,0,0);}
  100%{box-shadow:0 0 0 0 rgba(20,168,0,0);}
}
@keyframes spin{ to { transform: rotate(360deg); } }

.icon-btn{
  display:inline-flex;align-items:center;justify-content:center;
  width:38px;height:38px;flex:none;
  background:var(--card);
  color:var(--text-secondary);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  cursor:pointer;transition:border-color .15s ease, color .15s ease;
}
.icon-btn:hover{border-color:var(--accent);color:var(--accent);}
.icon-btn svg{display:block;}
.icon-btn .sun{display:none;}
[data-theme="light"] .icon-btn .moon{display:none;}
[data-theme="light"] .icon-btn .sun{display:block;}

.refresh-btn{
  display:inline-flex;align-items:center;gap:8px;
  background:var(--accent);
  color:#ffffff;
  border:1px solid var(--accent);
  border-radius:var(--radius-sm);
  padding:9px 16px;font-weight:600;font-size:0.84rem;cursor:pointer;
  font-family:var(--font-body);transition:background .15s ease;
}
.refresh-btn:hover:not(:disabled){background:var(--accent-hover);}
.refresh-btn:disabled{cursor:progress;opacity:0.75;}
.refresh-btn svg{transition:transform .4s ease;}
.refresh-btn.loading svg{animation:spin 1s linear infinite;}
.run-status{
  font-size:0.78rem;color:var(--text-muted);
  max-width:340px;
}
.run-status.warn{color:var(--warning);}

/* ---------- kpi grid ---------- */
.kpi-grid{
  display:grid;grid-template-columns:repeat(6,1fr);gap:14px;
  margin-bottom:20px;
}
.kpi-card{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  padding:18px;
  box-shadow:var(--shadow-card);
}
.kpi-label{
  display:block;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;
  color:var(--text-muted);margin-bottom:9px;font-weight:600;
}
.kpi-value{
  font-size:1.65rem;font-weight:700;
  color:var(--text-primary);letter-spacing:-0.01em;
}
.kpi-value.accent{color:var(--accent);}
.kpi-value.warn{color:var(--warning);}

/* ---------- charts ---------- */
.charts-row{
  display:grid;grid-template-columns:1.1fr 1fr;gap:16px;margin-bottom:16px;
}
.charts-row-wide{
  display:grid;grid-template-columns:1fr;gap:16px;margin-bottom:16px;
}
.panel{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  padding:22px;
  box-shadow:var(--shadow-card);
}
.panel h2{
  font-size:1rem;font-weight:600;
  margin:0 0 4px;color:var(--text-primary);
}
.panel .panel-sub{
  margin:0 0 16px;font-size:0.78rem;color:var(--text-muted);
}
.panel .chart-wrap{position:relative;height:230px;}
.panel .chart-wrap.tall{height:270px;}

/* ---------- calendar heatmap ---------- */
.cal-shell{display:flex;gap:8px;align-items:flex-start;}
.cal-labels{
  display:grid;grid-template-rows:repeat(7,1fr);gap:4px;
  font-size:0.62rem;color:var(--text-muted);
  padding-top:0;height:154px;
}
.cal-labels span{display:flex;align-items:center;height:20px;}
.cal-grid{
  display:grid;grid-auto-flow:column;grid-template-rows:repeat(7,1fr);
  gap:4px;overflow-x:auto;padding-bottom:4px;
}
.cal-cell{
  width:20px;height:20px;border-radius:5px;
  background:var(--bg-secondary);
  border:1px solid var(--border-soft);
}
.cal-cell[style]{
  background:rgba(20,168,0,var(--cal-alpha,0));
  border-color:rgba(20,168,0,0.3);
}
.cal-cell.cal-future{background:transparent;border-color:transparent;}
.cal-legend{
  display:flex;align-items:center;gap:6px;margin-top:12px;
  font-size:0.7rem;color:var(--text-muted);
}
.cal-legend .cal-cell{width:12px;height:12px;}

/* ---------- toolbar ---------- */
.toolbar{
  display:flex;flex-wrap:wrap;gap:12px;align-items:center;
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  padding:16px 18px;margin-bottom:16px;
  box-shadow:var(--shadow-card);
}
.toolbar input[type="text"],.toolbar select{
  background:var(--bg-secondary);
  border:1px solid var(--border);
  color:var(--text-primary);
  border-radius:var(--radius-sm);
  padding:9px 12px;font-family:var(--font-body);font-size:0.86rem;
  outline:none;transition:border-color .15s ease;
}
.toolbar input[type="text"]:focus,.toolbar select:focus{border-color:var(--accent);}
.toolbar input[type="text"]{flex:1 1 200px;min-width:160px;}
.toolbar select{min-width:140px;}
.toolbar .spacer{flex:1;}
.toolbar-check{
  display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--text-secondary);
  white-space:nowrap;
}
.toolbar-check input{accent-color:var(--accent);}
.count-pill{
  font-size:0.78rem;color:var(--text-secondary);
  padding:8px 12px;border:1px dashed var(--border);border-radius:999px;
  white-space:nowrap;
}
.export-btn{
  background:var(--accent);
  color:#ffffff;border:1px solid var(--accent);border-radius:var(--radius-sm);
  padding:10px 16px;font-weight:600;font-size:0.84rem;cursor:pointer;
  font-family:var(--font-body);transition:background .15s ease, transform .15s ease;
  white-space:nowrap;
}
.export-btn:hover{background:var(--accent-hover);transform:translateY(-1px);}
.export-btn.secondary{
  background:var(--bg-secondary);color:var(--text-primary);
  border:1px solid var(--border);
}
.export-btn.secondary:hover{border-color:var(--accent);color:var(--accent);background:var(--bg-secondary);}

/* ---------- table ---------- */
.table-panel{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  box-shadow:var(--shadow-card);
  overflow:hidden;
}
.table-scroll{overflow-x:auto;}
table{width:100%;border-collapse:collapse;min-width:960px;}
thead th{
  position:sticky;top:0;z-index:2;
  background:var(--bg-secondary);
  text-align:left;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;
  color:var(--text-muted);font-weight:700;
  padding:14px 18px;border-bottom:1px solid var(--border);
}
tbody td{
  padding:14px 18px;font-size:0.86rem;color:var(--text-secondary);
  border-bottom:1px solid var(--border-soft);
  white-space:nowrap;
}
tbody tr{transition:background .12s ease;}
tbody tr:hover{background:var(--accent-tint);}
.cell-title{color:var(--text-primary);font-weight:600;white-space:normal;max-width:300px;}
.cell-muted{color:var(--text-muted);}
.cell-date{font-size:0.8rem;}
.badge{
  --badge-color:var(--accent);
  display:inline-flex;align-items:center;gap:7px;
  background:color-mix(in srgb, var(--badge-color) 14%, transparent);
  border:1px solid color-mix(in srgb, var(--badge-color) 40%, transparent);
  color:var(--text-primary);
  padding:5px 11px;border-radius:999px;font-size:0.76rem;font-weight:600;
  white-space:nowrap;
}
.badge-dot{width:6px;height:6px;border-radius:50%;background:var(--badge-color);flex:none;}
.flag{
  display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;
  font-size:0.66rem;font-weight:700;text-transform:uppercase;letter-spacing:0.03em;
  vertical-align:middle;
}
.flag-new{background:rgba(20,168,0,0.14);color:var(--accent);border:1px solid rgba(20,168,0,0.35);}
.flag-warn{background:rgba(245,158,11,0.14);color:var(--warning);border:1px solid rgba(245,158,11,0.35);}
.quality-dot{
  display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;
}
.q-high{background:var(--accent);}
.q-mid{background:var(--warning);}
.q-low{background:var(--error);}
.apply-link{
  display:inline-flex;align-items:center;gap:6px;
  color:var(--accent);text-decoration:none;font-weight:600;font-size:0.82rem;
  border:1px solid rgba(20,168,0,0.35);border-radius:var(--radius-sm);
  padding:6px 11px;transition:background .15s ease;
}
.apply-link:hover{background:var(--accent-tint);}

.empty-state{
  display:none;text-align:center;padding:64px 20px;color:var(--text-muted);
}
.empty-state.visible{display:block;}
.empty-state strong{display:block;color:var(--text-secondary);font-size:1rem;margin-bottom:6px;}

.footer-note{
  text-align:center;color:var(--text-muted);font-size:0.78rem;
  margin-top:22px;
}

@media (max-width: 1080px){
  .kpi-grid{grid-template-columns:repeat(3,1fr);}
}
@media (max-width: 900px){
  .charts-row{grid-template-columns:1fr;}
}
@media (max-width: 560px){
  .kpi-grid{grid-template-columns:repeat(2,1fr);}
  body{padding:20px 12px 48px;}
}
@media (prefers-reduced-motion: reduce){
  .live-dot{animation:none;}
  .refresh-btn.loading svg{animation:none;}
  html{scroll-behavior:auto;}
}
@media print{
  .toolbar, .refresh-btn, .run-status, .export-btn, .apply-link, .live-dot, .icon-btn{display:none !important;}
  body{background:#fff;color:#000;padding:0;}
  .panel, .kpi-card, .table-panel{box-shadow:none;border:1px solid #ccc;background:#fff;color:#000;}
}
</style>
</head>
<body>
<div class="shell">

  <header class="topbar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <div>
        <h1>Kenya Data Jobs</h1>
        <p>Data, Analytics &amp; BI opportunities &middot; curated daily</p>
      </div>
    </div>
    <div class="meta">
      <div class="meta-updated">
        <span class="live-dot" aria-hidden="true"></span>
        <span>Updated __GENERATED_AT__</span>
      </div>
      <button class="refresh-btn" id="runScraperBtn" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v6h-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Run scraper
      </button>
      <span class="run-status" id="runStatus">__RUN_STATUS_DEFAULT__</span>
      <button class="icon-btn" id="themeToggle" type="button" aria-label="Toggle light/dark theme" title="Toggle light/dark theme">
        <svg class="moon" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <svg class="sun" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4.5" stroke="currentColor" stroke-width="1.7"/><path d="M12 2.5v2.5M12 19v2.5M4.5 12H2M22 12h-2.5M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>
      </button>
    </div>
  </header>

  <section class="kpi-grid">
    <div class="kpi-card">
      <span class="kpi-label">Total Jobs (all-time)</span>
      <span class="kpi-value">__TOTAL_JOBS__</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">New Today</span>
      <span class="kpi-value accent">__NEW_TODAY__</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">New This Week</span>
      <span class="kpi-value accent">__NEW_WEEK__</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Job Boards</span>
      <span class="kpi-value">__SOURCE_COUNT__</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Cities Covered</span>
      <span class="kpi-value">__CITIES_COVERED__</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Avg. Listing Quality</span>
      <span class="kpi-value accent">__AVG_QUALITY__<span style="font-size:0.9rem;color:var(--text-muted);font-weight:500;">/100</span></span>
    </div>
  </section>

  <section class="charts-row-wide">
    <div class="panel">
      <h2>Hiring Trend</h2>
      <p class="panel-sub">Jobs scraped per day, across every saved snapshot in this folder (last 30 days shown)</p>
      <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
    </div>
  </section>

  <section class="charts-row">
    <div class="panel">
      <h2>Top Job Titles</h2>
      <p class="panel-sub">Roles bucketed from free-text titles, all-time</p>
      <div class="chart-wrap"><canvas id="titlesChart"></canvas></div>
    </div>
    <div class="panel">
      <h2>Jobs by Day of Week</h2>
      <p class="panel-sub">When listings tend to get posted, all-time</p>
      <div class="chart-wrap"><canvas id="dowChart"></canvas></div>
    </div>
  </section>

  <section class="charts-row">
    <div class="panel">
      <h2>Jobs by Source</h2>
      <p class="panel-sub">This run &middot; __DASHBOARD_DATE__</p>
      <div class="chart-wrap"><canvas id="sourceChart"></canvas></div>
    </div>
    <div class="panel">
      <h2>Top Locations</h2>
      <p class="panel-sub">This run &middot; __DASHBOARD_DATE__</p>
      <div class="chart-wrap"><canvas id="locationChart"></canvas></div>
    </div>
  </section>

  <section class="charts-row">
    <div class="panel">
      <h2>Source Quality</h2>
      <p class="panel-sub">Avg. listing completeness score by job board, all-time</p>
      <div class="chart-wrap"><canvas id="qualityChart"></canvas></div>
    </div>
    <div class="panel">
      <h2>Hiring Calendar</h2>
      <p class="panel-sub">Last 5 weeks &middot; darker = more jobs scraped that day</p>
      <div class="cal-shell">
        <div class="cal-labels"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span></div>
        <div class="cal-grid">
          __CALENDAR_CELLS__
        </div>
      </div>
      <div class="cal-legend">
        <span>Less</span>
        <span class="cal-cell" style="--cal-alpha:0.15"></span>
        <span class="cal-cell" style="--cal-alpha:0.4"></span>
        <span class="cal-cell" style="--cal-alpha:0.7"></span>
        <span class="cal-cell" style="--cal-alpha:1"></span>
        <span>More</span>
      </div>
    </div>
  </section>

  <div class="toolbar">
    <input type="text" id="jobSearch" placeholder="Search job titles...">
    <select id="sourceFilter">
      <option value="">All sources</option>
      __SOURCE_OPTIONS__
    </select>
    <select id="locationFilter">
      <option value="">All locations</option>
      __LOCATION_OPTIONS__
    </select>
    <select id="qualityFilter">
      <option value="">Any quality</option>
      <option value="high">High quality (70+)</option>
      <option value="mid">Medium quality (40-69)</option>
      <option value="low">Low quality (&lt;40)</option>
    </select>
    <label class="toolbar-check"><input type="checkbox" id="newOnlyFilter"> New today only</label>
    <span class="spacer"></span>
    <span class="count-pill" id="resultCount">__TOTAL_ROWS__ jobs</span>
    <button class="export-btn secondary" onclick="window.print()">Print / PDF</button>
    <button class="export-btn secondary" onclick="exportToXLSX()">Export Excel</button>
    <button class="export-btn" onclick="exportToCSV()">Export CSV</button>
  </div>

  <div class="table-panel">
    <div class="table-scroll">
      <table id="jobsTable">
        <thead>
          <tr>
            <th>Job Title</th>
            <th>Source</th>
            <th>Location</th>
            <th>Posted</th>
            <th>Expires</th>
            <th>Qualification</th>
            <th>Quality</th>
            <th>Link</th>
          </tr>
        </thead>
        <tbody id="jobsTableBody">
          __JOB_ROWS__
        </tbody>
      </table>
    </div>
    <div class="empty-state" id="emptyState">
      <strong>No jobs match these filters</strong>
      Try clearing the search box or choosing a different source.
    </div>
  </div>

  <p class="footer-note">Kenya Job Scraper &middot; generated __GENERATED_AT__ &middot; __HISTORY_FILE_COUNT__ daily snapshot(s) in this folder</p>
</div>

<script>
const sourceLabels = __SOURCE_LABELS_JSON__;
const sourceCounts = __SOURCE_COUNTS_JSON__;
const locationLabels = __LOCATION_LABELS_JSON__;
const locationCounts = __LOCATION_COUNTS_JSON__;
const trendLabels = __TREND_LABELS_JSON__;
const trendValues = __TREND_VALUES_JSON__;
const dowLabels = __DOW_LABELS_JSON__;
const dowValues = __DOW_VALUES_JSON__;
const titleLabels = __TITLE_LABELS_JSON__;
const titleValues = __TITLE_VALUES_JSON__;
const qualitySourceLabels = __SRCQ_LABELS_JSON__;
const qualitySourceValues = __SRCQ_VALUES_JSON__;

/* Monochromatic green palette (darkest -> lightest), per the design
   system, used for every multi-series chart so nothing needs a separate
   ad-hoc color scheme. */
const greenPalette = ["#14A800", "#128A00", "#0F7300", "#8EDB7D", "#CFF2C8", "#EAF9E7"];

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

Chart.defaults.font.family = "'Inter', sans-serif";

const charts = [];

function themedTextColor() { return cssVar('--text-secondary'); }
function themedGridColor() { return cssVar('--chart-grid'); }

function makeChart(id, config) {
  const chart = new Chart(document.getElementById(id), config);
  charts.push(chart);
  return chart;
}

makeChart('trendChart', {
  type: 'line',
  data: {
    labels: trendLabels,
    datasets: [{
      label: 'Jobs scraped',
      data: trendValues,
      borderColor: '#14A800',
      backgroundColor: 'rgba(20,168,0,0.12)',
      fill: true,
      tension: 0.35,
      pointRadius: 3,
      pointBackgroundColor: '#14A800'
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { color: themedTextColor(), maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
      y: { beginAtZero: true, grid: { color: themedGridColor() }, ticks: { color: themedTextColor(), precision: 0 } }
    }
  }
});

makeChart('titlesChart', {
  type: 'bar',
  data: {
    labels: titleLabels,
    datasets: [{ label: 'Jobs', data: titleValues, backgroundColor: '#14A800', borderRadius: 6, maxBarThickness: 22 }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { beginAtZero: true, grid: { color: themedGridColor() }, ticks: { color: themedTextColor(), precision: 0 } },
      y: { grid: { display: false }, ticks: { color: themedTextColor() } }
    }
  }
});

makeChart('dowChart', {
  type: 'bar',
  data: {
    labels: dowLabels,
    datasets: [{ label: 'Jobs', data: dowValues, backgroundColor: '#128A00', borderRadius: 6, maxBarThickness: 30 }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { color: themedTextColor() } },
      y: { beginAtZero: true, grid: { color: themedGridColor() }, ticks: { color: themedTextColor(), precision: 0 } }
    }
  }
});

makeChart('sourceChart', {
  type: 'doughnut',
  data: {
    labels: sourceLabels,
    datasets: [{
      data: sourceCounts,
      backgroundColor: greenPalette,
      borderColor: cssVar('--card'),
      borderWidth: 3,
      hoverOffset: 6
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '64%',
    plugins: {
      legend: { position: 'bottom', labels: { color: themedTextColor(), boxWidth: 10, padding: 14, font: { size: 11 } } }
    }
  }
});

makeChart('locationChart', {
  type: 'bar',
  data: {
    labels: locationLabels,
    datasets: [{
      label: 'Jobs',
      data: locationCounts,
      backgroundColor: '#14A800',
      borderRadius: 6,
      maxBarThickness: 28
    }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { beginAtZero: true, grid: { color: themedGridColor() }, ticks: { color: themedTextColor(), precision: 0 } },
      y: { grid: { display: false }, ticks: { color: themedTextColor() } }
    }
  }
});

makeChart('qualityChart', {
  type: 'bar',
  data: {
    labels: qualitySourceLabels,
    datasets: [{
      label: 'Avg. quality',
      data: qualitySourceValues,
      backgroundColor: qualitySourceValues.map(v => v >= 70 ? '#14A800' : (v >= 40 ? '#F59E0B' : '#DC2626')),
      borderRadius: 6,
      maxBarThickness: 28
    }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { beginAtZero: true, max: 100, grid: { color: themedGridColor() }, ticks: { color: themedTextColor() } },
      y: { grid: { display: false }, ticks: { color: themedTextColor() } }
    }
  }
});

/* ---------- theme toggle ---------- */
const themeToggleBtn = document.getElementById('themeToggle');
themeToggleBtn.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('kdj-theme', next); } catch (e) {}

  // Re-theme every chart's text/grid colors and repaint.
  requestAnimationFrame(() => {
    const textColor = themedTextColor();
    const gridColor = themedGridColor();
    const cardColor = cssVar('--card');
    charts.forEach(chart => {
      if (chart.options.scales) {
        Object.values(chart.options.scales).forEach(scale => {
          if (scale.ticks) scale.ticks.color = textColor;
          if (scale.grid) scale.grid.color = gridColor;
        });
      }
      if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
        chart.options.plugins.legend.labels.color = textColor;
      }
      chart.data.datasets.forEach(ds => {
        if (ds.borderColor === '#121212' || ds.borderColor === '#222222' || ds.borderColor === '#FFFFFF' || ds.borderColor === cardColor) {
          ds.borderColor = cardColor;
        }
      });
      chart.update();
    });
  });
});

function filterTable() {
  const sourceVal = document.getElementById('sourceFilter').value;
  const locationVal = document.getElementById('locationFilter').value;
  const searchVal = document.getElementById('jobSearch').value.toLowerCase();
  const qualityVal = document.getElementById('qualityFilter').value;
  const newOnly = document.getElementById('newOnlyFilter').checked;
  const rows = document.querySelectorAll('#jobsTableBody tr');
  let visibleCount = 0;

  rows.forEach(row => {
    const source = row.getAttribute('data-source') || '';
    const location = row.getAttribute('data-location') || '';
    const title = row.getAttribute('data-title') || '';
    const quality = parseInt(row.getAttribute('data-quality') || '0', 10);
    const isNew = row.getAttribute('data-new') === '1';

    const matchesSource = !sourceVal || source === sourceVal;
    const matchesLocation = !locationVal || location === locationVal;
    const matchesSearch = !searchVal || title.includes(searchVal);
    const matchesQuality = !qualityVal
      || (qualityVal === 'high' && quality >= 70)
      || (qualityVal === 'mid' && quality >= 40 && quality < 70)
      || (qualityVal === 'low' && quality < 40);
    const matchesNew = !newOnly || isNew;

    const show = matchesSource && matchesLocation && matchesSearch && matchesQuality && matchesNew;
    row.style.display = show ? '' : 'none';
    if (show) visibleCount++;
  });

  document.getElementById('resultCount').textContent = visibleCount + ' job' + (visibleCount === 1 ? '' : 's');
  document.getElementById('emptyState').classList.toggle('visible', visibleCount === 0);
}

document.getElementById('jobSearch').addEventListener('input', filterTable);
document.getElementById('sourceFilter').addEventListener('change', filterTable);
document.getElementById('locationFilter').addEventListener('change', filterTable);
document.getElementById('qualityFilter').addEventListener('change', filterTable);
document.getElementById('newOnlyFilter').addEventListener('change', filterTable);

function getVisibleRowsAsArray() {
  const rows = [['Job Title', 'Source', 'Location', 'Posted', 'Expires', 'Qualification', 'Quality', 'Link']];
  document.querySelectorAll('#jobsTableBody tr').forEach(row => {
    if (row.style.display === 'none') return;
    const cells = row.querySelectorAll('td');
    const link = cells[7].querySelector('a');
    rows.push([
      cells[0].childNodes[0] ? cells[0].childNodes[0].textContent.trim() : cells[0].textContent.trim(),
      cells[1].textContent.trim(),
      cells[2].textContent.trim(),
      cells[3].textContent.trim(),
      cells[4].textContent.trim(),
      cells[5].textContent.trim(),
      cells[6].textContent.trim(),
      link ? link.getAttribute('href') : ''
    ]);
  });
  return rows;
}

function exportToCSV() {
  const rows = getVisibleRowsAsArray();
  const csv = rows.map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',')).join('\\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.setAttribute('hidden', '');
  a.setAttribute('href', url);
  a.setAttribute('download', '__CSV_FILENAME__');
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

function exportToXLSX() {
  if (typeof XLSX === 'undefined') {
    alert('Excel export needs an internet connection to load the xlsx library.');
    return;
  }
  const rows = getVisibleRowsAsArray();
  const ws = XLSX.utils.aoa_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Jobs');
  XLSX.writeFile(wb, '__XLSX_FILENAME__');
}

/* ---------- live refresh (needs dashboard_server.py) ---------- */
const runBtn = document.getElementById('runScraperBtn');
const runStatus = document.getElementById('runStatus');
const servedLocally = window.location.protocol === 'http:' || window.location.protocol === 'https:';

runBtn.addEventListener('click', async () => {
  if (!servedLocally) {
    runStatus.textContent = 'Start dashboard_server.py and open it at http://localhost:8877 to enable one-click refresh.';
    runStatus.classList.add('warn');
    return;
  }
  runBtn.disabled = true;
  runBtn.classList.add('loading');
  runStatus.classList.remove('warn');
  runStatus.textContent = 'Starting scraper - this can take several minutes...';
  try {
    const startRes = await fetch('/api/refresh', { method: 'POST' });
    if (!startRes.ok) {
      const body = await startRes.json().catch(() => ({}));
      throw new Error(body.error || ('Server responded ' + startRes.status));
    }
    await pollRunStatus();
  } catch (err) {
    runStatus.textContent = 'Refresh failed: ' + err.message;
    runStatus.classList.add('warn');
    runBtn.disabled = false;
    runBtn.classList.remove('loading');
  }
});

async function pollRunStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    runStatus.textContent = data.message || (data.running ? 'Running...' : 'Done');
    if (data.running) {
      setTimeout(pollRunStatus, 2000);
      return;
    }
    if (data.error) {
      runStatus.textContent = 'Refresh failed: ' + data.error;
      runStatus.classList.add('warn');
      runBtn.disabled = false;
      runBtn.classList.remove('loading');
      return;
    }
    runStatus.textContent = 'Done - reloading with fresh data...';
    setTimeout(() => window.location.reload(), 900);
  } catch (err) {
    runStatus.textContent = 'Lost connection to dashboard_server.py: ' + err.message;
    runStatus.classList.add('warn');
    runBtn.disabled = false;
    runBtn.classList.remove('loading');
  }
}
</script>
</body>
</html>
"""

def main():
    """Main function with a small CLI for the save-path override.

    Uses parse_known_args() rather than parse_args() so this also runs
    cleanly inside Jupyter/IPython, Spyder, PyCharm's scientific mode, etc.
    Those environments inject their own arguments into sys.argv (Jupyter
    adds things like `-f kernel-xxxx.json`); parse_args() would treat that
    as an error and raise SystemExit, while parse_known_args() simply
    ignores anything it doesn't recognize.
    """
    parser = argparse.ArgumentParser(description="Kenya Job Scraper v22 - Analytics Edition")
    parser.add_argument(
        "--path", dest="save_path", default=None,
        help="Folder to save data/dashboard into (skips the first-run prompt)."
    )
    parser.add_argument(
        "--reset-path", dest="reset_path", action="store_true",
        help="Forget the remembered save folder and ask again."
    )
    args, _unknown_args = parser.parse_known_args()

    print("=" * 80)
    print("KENYA JOB SCRAPER v22 - ANALYTICS EDITION")
    print("=" * 80)
    print("Targeting: Data Analytics, Statistics, and BI roles")
    print("Sources:   MyJobMag, BrighterMonday, Fuzu, CareerPoint Kenya, MyJobsInKenya")
    print("Output:    JSON, CSV, and an interactive analytics HTML dashboard")
    print("-" * 80)

    try:
        scraper = KenyaJobScraper(save_path=args.save_path, force_path_prompt=args.reset_path)
        scraper.run()

        print("\nDone. Files are in:", scraper.save_path)
        print("Open the dashboard HTML file in a browser to explore the results.")
        print("Tip: run 'python dashboard_server.py' instead of opening the HTML")
        print("     directly to get the dashboard's one-click 'Run scraper' button.")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        print("Check the log file in the save folder for details.")


if __name__ == "__main__":
    main()
