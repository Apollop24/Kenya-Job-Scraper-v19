 #!/usr/bin/env python3
"""
Kenya Job Scraper v19 - Enhanced Production Version
A robust web scraper for Kenyan job boards with improved caching, error recovery, and interactive dashboard.
Handles BrighterMonday, MyJobMag, CareerPoint, Fuzu, and MyJobsInKenya.

Key Improvements:
- Enhanced Fuzu human verification handling with explicit wait and retry logic
- Improved caching system based on run changes rather than time limits
- Better error handling and recovery mechanisms
- More robust popup handling across all sites
- Enhanced logging and user feedback

Author: Data Scientist
Date: 2025-07-03
Version: 19.0
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import time
import logging
from urllib.parse import urljoin, urlparse, parse_qs
import re
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
import pickle
import hashlib

class KenyaJobScraper:
    def __init__(self, save_path: str = "C:\\Users\\USER\\Documents\\app\\Jobs\\"):
        """Initialize the Kenya Job Scraper with optimized settings"""
        self.save_path = save_path
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
        
        # Load existing data and cache
        self.load_existing_data()
        self.load_cache()
        
        # Initialize webdriver as None (lazy loading)
        self.driver = None
        self.wait = None
        self.long_wait = None  # For human verification
        
        # KEYWORD CONFIGURATION - Update this list to change search terms
        self.search_keywords = [
           "data","officer", "MONITORING",
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
            'version': '19.0'
        }
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def setup_logging(self):
        """Setup logging configuration without unicode characters"""
        log_filename = os.path.join(self.save_path, f"job_scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
        # Configure logging to handle unicode properly
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
        # Use visible browser for better compatibility with human verification
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
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 1  # Enable images for human verification
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

    def load_existing_data(self):
        """Load existing job data from today's files"""
        if os.path.exists(self.json_filename):
            try:
                with open(self.json_filename, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    self.jobs_data = existing_data
                    # Populate duplicate URLs
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
            # Check if run configuration has changed
            cached_config = cached_data.get('run_config')
            if cached_config != self.current_run_config:
                self.logger.info(f"Cache invalid for {cache_key}: configuration changed")
                return False
            
            # Check if it's the same day
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

    def handle_popups(self):
        """Enhanced popup handling with better selectors"""
        popup_handlers = [
            # Cookie consent
            ("button", "id", "onetrust-accept-btn-handler"),
            ("button", "class", "onetrust-accept-btn-handler"),
            ("button", "text", "Accept"),
            ("button", "text", "Accept All"),
            ("button", "text", "I Accept"),
            
            # Notification popups
            ("button", "id", "onesignal-slidedown-cancel-button"),
            ("button", "class", "onesignal-slidedown-cancel-button"),
            ("button", "text", "No Thanks"),
            ("button", "text", "Not Now"),
            
            # Modal closes
            ("img", "data-cy", "close-modal"),
            ("button", "class", "close"),
            ("button", "class", "modal-close"),
            ("div", "class", "modal-close"),
            ("span", "class", "close"),
            
            # Android app download popup (Fuzu specific)
            ("button", "text", "×"),
            ("button", "text", "✕"),
            ("span", "text", "×"),
            ("span", "text", "✕"),
            ("div", "class", "close-button"),
            ("button", "class", "app-download-close"),
            
            # Generic close buttons
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
                
                # Wait for the page to load completely
                time.sleep(3)
                
                # Check if we're on a human verification page
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
                    except:
                        continue
                
                if not verification_present:
                    self.logger.info("No human verification detected")
                    return True
                
                # Wait for and handle the checkbox
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
                        
                        # Wait for checkbox to be present and clickable
                        checkbox = self.long_wait.until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        
                        if checkbox.is_displayed() and checkbox.is_enabled():
                            # Scroll to checkbox
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
                            time.sleep(1)
                            
                            # Try multiple click methods
                            try:
                                checkbox.click()
                                self.logger.info("Checkbox clicked successfully")
                            except:
                                try:
                                    self.driver.execute_script("arguments[0].click();", checkbox)
                                    self.logger.info("Checkbox clicked via JavaScript")
                                except:
                                    # Try ActionChains
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(checkbox).click().perform()
                                    self.logger.info("Checkbox clicked via ActionChains")
                            
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
                    time.sleep(5)  # Wait a bit more
                    continue
                
                # Look for and click verify/continue button
                verify_button_selectors = [
                    "//button[contains(text(), 'Verify')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[contains(text(), 'Submit')]",
                    "//input[@type='submit']",
                    "//button[@type='submit']"
                ]
                
                for selector in verify_button_selectors:
                    try:
                        verify_button = self.wait.until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        
                        if verify_button.is_displayed():
                            self.driver.execute_script("arguments[0].click();", verify_button)
                            self.logger.info(f"Clicked verify button: {selector}")
                            time.sleep(3)
                            break
                            
                    except:
                        continue
                
                # Wait for verification to complete
                self.logger.info("Waiting for verification to complete...")
                time.sleep(8)
                
                # Check if verification was successful
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
                    except:
                        continue
                
                # Also check if we're redirected away from verification page
                current_url = self.driver.current_url
                if "challenge" not in current_url.lower() and "verify" not in current_url.lower():
                    verification_successful = True
                    self.logger.info("Redirected away from verification page - assuming success")
                
                if verification_successful:
                    return True
                
                # If we get here, verification might have failed
                self.logger.warning(f"Verification attempt {attempt + 1} may have failed, retrying...")
                time.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Error in human verification attempt {attempt + 1}: {str(e)}")
                time.sleep(5)
                continue
        
        self.logger.error("Human verification failed after all attempts")
        return False

    def parse_date(self, date_string: str) -> Optional[datetime]:
        """Parse various date formats to datetime object"""
        if not date_string or date_string.lower() in ['not specified', 'unknown']:
            return None
            
        date_string = date_string.strip()
        
        # Handle relative dates
        if 'ago' in date_string.lower():
            if 'day' in date_string.lower():
                days = int(re.search(r'(\d+)', date_string).group(1))
                return datetime.now() - timedelta(days=days)
            elif 'week' in date_string.lower():
                weeks = int(re.search(r'(\d+)', date_string).group(1))
                return datetime.now() - timedelta(weeks=weeks)
            elif 'hour' in date_string.lower():
                return datetime.now()
        
        # Handle absolute dates
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
        # First check posted date
        job_date = self.parse_date(date_posted)
        if job_date:
            seven_days_ago = self.today - timedelta(days=7)
            return job_date.date() >= seven_days_ago
        
        # If no posted date, check expiry date
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
        
        # Check the last job on the page (oldest)
        last_job = jobs_on_page[-1]
        
        # If job has posting date, check if it's within 7 days
        if last_job.get('date_posted') and last_job['date_posted'] != 'Not specified':
            if not self.is_recent_job(last_job['date_posted']):
                return False
        
        # If job has expiry date, check if it hasn't expired
        if last_job.get('date_expires') and last_job['date_expires'] != 'Not specified':
            if not self.is_not_expired(last_job['date_expires']):
                return False
        
        # If no dates available, continue to next page (don't miss opportunities)
        return True

    def get_cache_key_with_config(self, site_name: str) -> str:
        """Generate cache key that includes run configuration"""
        return f"{site_name}_{self.current_run_config}"

    def is_relevant_job(self, job_title: str, job_description: str = "") -> bool:
        """Check if job is relevant based on title and description"""
        title_lower = job_title.lower()
        desc_lower = job_description.lower()
        
        relevant_keywords = [
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
        
        for keyword in relevant_keywords:
            if keyword in title_lower or keyword in desc_lower:
                return True
        
        return False

    def save_job_data(self, job_data: Dict):
        """Save individual job data immediately to prevent data loss"""
        self.jobs_data.append(job_data)
        
        # Save to JSON file (single file per day)
        try:
            with open(self.json_filename, 'w', encoding='utf-8') as f:
                json.dump(self.jobs_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Updated JSON: {os.path.basename(self.json_filename)}")
        except Exception as e:
            self.logger.error(f"Error saving JSON: {str(e)}")
        
        # Save to CSV file (single file per day)
        try:
            df = pd.DataFrame(self.jobs_data)
            df.to_csv(self.csv_filename, index=False, encoding='utf-8')
            self.logger.info(f"Updated CSV: {os.path.basename(self.csv_filename)}")
        except Exception as e:
            self.logger.error(f"Error saving CSV: {str(e)}")
            
        self.logger.info(f"Saved job #{len(self.jobs_data)}: {job_data.get('job_title', 'Unknown')}")

    def scrape_myjobmag(self) -> List[Dict]:
        """Scrape jobs from MyJobMag Kenya with smart date-based pagination"""
        jobs = []
        self.logger.info("Starting MyJobMag scraping...")
        
        try:
            # Check cache with run configuration tracking
            cache_key = self.get_cache_key_with_config("myjobmag")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached MyJobMag data ({len(cached_jobs)} jobs)")
                return cached_jobs
            
            # Setup driver if not already done
            self.setup_driver()
            
            # Navigate to MyJobMag homepage
            self.driver.get("https://www.myjobmag.co.ke")
            time.sleep(4)
            
            # Handle popups
            self.handle_popups()
            
            # Use ALL keywords from configuration
            keywords_to_use = self.search_keywords
            
            # For each search keyword
            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching MyJobMag for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")
                    
                    # Navigate back to homepage for fresh start
                    if keyword_idx > 0:
                        self.driver.get("https://www.myjobmag.co.ke")
                        time.sleep(3)
                        self.handle_popups()
                    
                    # Find search input and enter keyword
                    search_input = self.wait.until(
                        EC.presence_of_element_located((By.ID, "search-key"))
                    )
                    search_input.clear()
                    search_input.send_keys(keyword)
                    time.sleep(1)
                    
                    # Click search button
                    search_btn = self.driver.find_element(By.ID, "search-but")
                    self.driver.execute_script("arguments[0].click();", search_btn)
                    time.sleep(4)
                    
                    # Smart pagination based on job dates
                    page = 1
                    should_continue = True
                    
                    while should_continue and page <= 5:  # Max 5 pages safety limit
                        # Get fresh job links for each page
                        job_links_data = []
                        page_jobs = []  # Track jobs on this page for date checking
                        
                        # Collect job link data first
                        try:
                            job_link_elements = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/job/')]")
                            
                            for elem in job_link_elements:  # Don't limit on page 1, especially
                                try:
                                    href = elem.get_attribute('href')
                                    text = elem.text.strip()
                                    if href and text and self.is_relevant_job(text):
                                        job_links_data.append({'href': href, 'title': text})
                                except:
                                    continue
                        except Exception as e:
                            self.logger.error(f"Error collecting job links: {str(e)}")
                            break
                        
                        self.logger.info(f"Page {page}: Found {len(job_links_data)} relevant job links for '{keyword}'")
                        
                        # Process each job link
                        for job_data in job_links_data:
                            try:
                                job_link = job_data['href']
                                job_title = job_data['title']
                                
                                if job_link in self.duplicate_urls:
                                    continue
                                
                                # Navigate directly to job page
                                self.driver.get(job_link)
                                time.sleep(3)
                                
                                # Extract job details
                                extracted_data = self.extract_myjobmag_job_details(job_title, job_link)
                                
                                if extracted_data:
                                    # Check if job is older than 7 days - if so, stop immediately
                                    if extracted_data['date_posted'] != 'Not specified':
                                        if not self.is_recent_job(extracted_data['date_posted']):
                                            self.logger.info(f"Job older than 7 days detected: {job_title}. Stopping page scraping.")
                                            should_continue = False
                                            break
                                    
                                    # Check if job has expired - if so, stop immediately
                                    if extracted_data['date_expires'] != 'Not specified':
                                        if not self.is_not_expired(extracted_data['date_expires']):
                                            self.logger.info(f"Expired job detected: {job_title}. Stopping page scraping.")
                                            should_continue = False
                                            break
                                    
                                    page_jobs.append(extracted_data)  # Track for date checking
                                    
                                    # Use improved date checking
                                    if self.is_recent_job(extracted_data['date_posted'], extracted_data['date_expires']) and self.is_not_expired(extracted_data['date_expires']):
                                        self.duplicate_urls.add(job_link)
                                        self.save_job_data(extracted_data)
                                        jobs.append(extracted_data)
                                
                            except Exception as e:
                                self.logger.error(f"Error processing MyJobMag job: {str(e)}")
                                continue
                        
                        # If we detected old/expired jobs, stop pagination
                        if not should_continue:
                            break
                        
                        # Smart pagination decision - check if should continue to next page
                        if page_jobs:
                            should_continue = self.should_continue_to_next_page(page_jobs)
                            if not should_continue:
                                self.logger.info(f"Stopping pagination for '{keyword}' - older jobs detected on page {page}")
                        
                        # Try to go to next page if should continue
                        if should_continue:
                            try:
                                # Go back to search results
                                self.driver.back()
                                time.sleep(2)
                                
                                next_page_link = self.driver.find_element(By.XPATH, f"//a[@href='/page/{page + 1}' or contains(text(), '{page + 1}')]")
                                self.driver.execute_script("arguments[0].click();", next_page_link)
                                time.sleep(3)
                                page += 1
                            except:
                                should_continue = False
                    
                except Exception as e:
                    self.logger.error(f"Error searching MyJobMag for '{keyword}': {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in MyJobMag scraping: {str(e)}")
        
        # Cache results with run configuration
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
            
            # Extract date posted
            try:
                posted_elem = self.driver.find_element(By.ID, "posted-date")
                posted_text = posted_elem.text
                if 'Posted:' in posted_text:
                    job_data['date_posted'] = posted_text.split('Posted:')[1].strip()
            except:
                # Alternative selector
                try:
                    posted_elem = self.driver.find_element(By.XPATH, "//div[contains(@class, 'read-date-sec-li') and contains(text(), 'Posted')]")
                    posted_text = posted_elem.text
                    if 'Posted:' in posted_text:
                        job_data['date_posted'] = posted_text.split('Posted:')[1].strip()
                except:
                    pass
            
            # Extract deadline
            try:
                deadline_elem = self.driver.find_element(By.XPATH, "//div[@class='read-date-sec-li']//b[contains(text(), 'Deadline:')]//parent::div")
                deadline_text = deadline_elem.text
                if 'Deadline:' in deadline_text:
                    job_data['date_expires'] = deadline_text.split('Deadline:')[1].strip()
            except:
                pass
            
            # Extract qualification
            try:
                qual_links = self.driver.find_elements(By.XPATH, "//span[@class='jkey-info']//a[contains(@href, '/jobs-by-education/')]")
                qualifications = [link.text.strip() for link in qual_links]
                if qualifications:
                    job_data['qualification'] = ', '.join(qualifications)
            except:
                pass
            
            # Extract experience
            try:
                exp_elem = self.driver.find_element(By.XPATH, "//span[@class='jkey-title' and text()='Experience']/following-sibling::span[@class='jkey-info']")
                job_data['years_of_experience'] = exp_elem.text.strip()
            except:
                pass
            
            # Extract location
            try:
                location_elem = self.driver.find_element(By.XPATH, "//span[@class='jkey-title' and text()='Location']/following-sibling::span//a")
                job_data['location'] = location_elem.text.strip()
            except:
                pass
            
            return job_data
            
        except Exception as e:
            self.logger.error(f"Error extracting MyJobMag job details: {str(e)}")
            return None

    def scrape_brightermonday(self) -> List[Dict]:
        """Scrape jobs from BrighterMonday Kenya with smart pagination"""
        jobs = []
        self.logger.info("Starting BrighterMonday scraping...")
        
        try:
            # Check cache with run configuration tracking
            cache_key = self.get_cache_key_with_config("brightermonday")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached BrighterMonday data ({len(cached_jobs)} jobs)")
                return cached_jobs
            
            # Setup driver if not already done
            self.setup_driver()
            
            # Navigate to BrighterMonday homepage
            self.driver.get("https://www.brightermonday.co.ke")
            time.sleep(4)
            
            # Handle popups
            self.handle_popups()
            
            # Try to click "Find a Job" button
            try:
                find_job_selectors = [
                    "//button[contains(text(), 'Find a Job')]",
                    "//a[contains(text(), 'Find a Job')]",
                    "//span[contains(text(), 'Find a Job')]//parent::button",
                    "//div[contains(text(), 'Find a Job')]//parent::a"
                ]
                
                navigation_success = False
                for selector in find_job_selectors:
                    try:
                        find_job_btn = self.driver.find_element(By.XPATH, selector)
                        self.driver.execute_script("arguments[0].click();", find_job_btn)
                        time.sleep(3)
                        navigation_success = True
                        self.logger.info("Successfully clicked 'Find a Job' button")
                        break
                    except:
                        continue
                
                if not navigation_success:
                    self.driver.get("https://www.brightermonday.co.ke/jobs")
                    time.sleep(3)
                    
            except Exception as e:
                self.logger.error(f"Error navigating to jobs page: {str(e)}")
                self.driver.get("https://www.brightermonday.co.ke/jobs")
                time.sleep(3)
            
            # Handle popups again
            self.handle_popups()
            
            # Use ALL keywords from configuration
            keywords_to_use = self.search_keywords
            
            # For each search keyword
            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching BrighterMonday for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")
                    
                    # Try multiple search strategies
                    search_selectors = [
                        "//input[@placeholder='Search']",
                        "//input[contains(@class, 'search')]",
                        "//input[@type='text' and not(@style) and not(@hidden)]",
                        "//div[contains(text(), 'Filter Results')]//following::input[@type='text'][1]",
                        "//form//input[@type='text']",
                        "//input[@name='search']"
                    ]
                    
                    search_input = None
                    for selector in search_selectors:
                        try:
                            search_input = self.driver.find_element(By.XPATH, selector)
                            if search_input.is_displayed() and search_input.is_enabled():
                                # Wait for element to be truly interactable
                                self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                                break
                        except:
                            continue
                    
                    if search_input:
                        search_input.clear()
                        search_input.send_keys(keyword)
                        time.sleep(1)
                        search_input.send_keys(Keys.RETURN)
                        time.sleep(4)
                    
                    # Find job listings
                    job_selectors = [
                        "//a[contains(@href, '/job/')]",
                        "//div[contains(@class, 'job')]//a",
                        "//h2//a | //h3//a",
                        "//a[contains(@class, 'job-title')]"
                    ]
                    
                    job_elements = []
                    for selector in job_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except:
                            continue
                    
                    self.logger.info(f"Found {len(job_elements)} potential job elements for '{keyword}'")
                    
                    # Process jobs
                    for i, job_element in enumerate(job_elements[:5]):
                        try:
                            job_link = job_element.get_attribute('href')
                            if not job_link or job_link in self.duplicate_urls:
                                continue
                            
                            job_title = job_element.text.strip() or job_element.get_attribute('title')
                            
                            if not job_title or not self.is_relevant_job(job_title):
                                continue
                            
                            # Create basic job data
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
        
        # Cache results with run configuration
        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()
        
        self.logger.info(f"BrighterMonday scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    def scrape_fuzu(self) -> List[Dict]:
        """Scrape jobs from Fuzu Kenya with enhanced human verification handling"""
        jobs = []
        self.logger.info("Starting Fuzu scraping...")
        
        try:
            # Check cache with run configuration tracking
            cache_key = self.get_cache_key_with_config("fuzu")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached Fuzu data ({len(cached_jobs)} jobs)")
                return cached_jobs
            
            # Setup driver if not already done
            self.setup_driver()
            
            # Navigate directly to Fuzu Kenya jobs page
            self.logger.info("Navigating to Fuzu Kenya...")
            self.driver.get("https://www.fuzu.com/kenya/job")
            time.sleep(5)
            
            # Handle human verification with enhanced method
            if not self.handle_human_verification():
                self.logger.error("Failed to complete human verification for Fuzu")
                return jobs
            
            # Handle additional popups after verification
            self.handle_popups()
            time.sleep(3)
            
            # Use ALL keywords from configuration
            keywords_to_use = self.search_keywords
            
            # For each search keyword
            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching Fuzu for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")
                    
                    # Multiple attempts to find search input
                    search_selectors = [
                        "//input[@placeholder='Show jobs']",
                        "//input[contains(@class, 'search')]",
                        "//input[@type='text' and contains(@placeholder, 'job')]",
                        "//form//input[@type='text']",
                        "//input[@name='q']",
                        "//input[@name='search']",
                        "//div[contains(@class, 'search')]//input[@type='text']"
                    ]
                    
                    search_input = None
                    for selector in search_selectors:
                        try:
                            search_input = self.wait.until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                            if search_input.is_displayed() and search_input.is_enabled():
                                # Additional wait to ensure it's truly interactable
                                self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                                break
                        except:
                            continue
                    
                    if not search_input:
                        self.logger.warning("Could not find search input on Fuzu")
                        continue
                    
                    # Clear and enter search term
                    search_input.clear()
                    search_input.send_keys(keyword)
                    time.sleep(1)
                    
                    # Find and click search button
                    
                    search_button_selectors = [
                        "//button[contains(@class, 'fz-btn') and contains(@class, 'b2c-button')]//div[contains(text(), 'Show jobs')]/..",
                        "//button[contains(@class, 'fz-btn')]//div[contains(@class, 'fz-btn__text') and contains(text(), 'Show jobs')]/..",
                        "//button[contains(@class, 'Button__StyledButton')]//div[contains(text(), 'Show jobs')]/..",
                        "//button[.//div[contains(text(), 'Show jobs')]]",
                        "//button[contains(@class, 'fz-btn')]",
                        "//button[contains(text(), 'Show jobs')]",
                        "//button[contains(@class, 'show-jobs')]",
                        "//button[@type='submit']",
                        "//input[@type='submit']"
                    ]
                    
                    search_button = None
                    for selector in search_button_selectors:
                        try:
                            search_button = self.driver.find_element(By.XPATH, selector)
                            if search_button.is_displayed() and search_button.is_enabled():
                                self.logger.info(f"Found search button using selector: {selector}")
                                break
                        except:
                            continue
                    
                    if search_button:
                        try:
                            # Try regular click first
                            search_button.click()
                            self.logger.info("Successfully clicked search button")
                            time.sleep(5)
                        except Exception as e:
                            # If regular click fails, try JavaScript click
                            self.logger.info(f"Regular click failed ({e}), trying JavaScript click")
                            self.driver.execute_script("arguments[0].click();", search_button)
                            time.sleep(5)
                    else:
                        self.logger.warning("Could not find search button on Fuzu")
                        continue
                    #search_button_selectors = [
                        #"//button[contains(text(), 'Show jobs')]",
                        #"//button[contains(@class, 'show-jobs')]",
                        #"//button[@type='submit']",
                        #"//input[@type='submit']"
                    #]
                    
                    #search_button = None
                    #for selector in search_button_selectors:
                        #try:
                            #search_button = self.driver.find_element(By.XPATH, selector)
                            #if search_button.is_displayed():
                                #break
                        #except:
                            #continue
                    
                
                    #if search_button:
                        #self.driver.execute_script("arguments[0].click();", search_button)
                        #time.sleep(5)
                    #else:
                        # Try pressing Enter
                        #search_input.send_keys(Keys.RETURN)
                        #time.sleep(5)
                    
                    # Find job listings with multiple selectors
                    # Clear and enter search term with enhanced interaction
                    search_input.clear()
                    time.sleep(1)
                    
                    # Type the keyword character by character to simulate human typing
                    for char in keyword:
                        search_input.send_keys(char)
                        time.sleep(0.1)
                    
                    # Trigger input events that JavaScript might be listening for
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", search_input)
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", search_input)
                    time.sleep(1)
                    
                    # Log current URL before search
                    url_before = self.driver.current_url
                    self.logger.info(f"URL before search: {url_before}")
                    
                    # Find and click search button - Updated selectors to match actual HTML
                    search_button_selectors = [
                        "//button[contains(@class, 'fz-btn') and contains(@class, 'b2c-button')]//div[contains(text(), 'Show jobs')]/..",
                        "//button[contains(@class, 'fz-btn')]//div[contains(@class, 'fz-btn__text') and contains(text(), 'Show jobs')]/..",
                        "//button[contains(@class, 'Button__StyledButton')]//div[contains(text(), 'Show jobs')]/..",
                        "//button[.//div[contains(text(), 'Show jobs')]]",
                        "//button[contains(@class, 'fz-btn')]",
                        "//button[contains(text(), 'Show jobs')]",
                        "//button[contains(@class, 'show-jobs')]",
                        "//button[@type='submit']",
                        "//input[@type='submit']"
                    ]
                    
                    search_button = None
                    for selector in search_button_selectors:
                        try:
                            search_button = self.driver.find_element(By.XPATH, selector)
                            if search_button.is_displayed() and search_button.is_enabled():
                                self.logger.info(f"Found search button using selector: {selector}")
                                break
                        except:
                            continue
                    
                    if search_button:
                        try:
                            # Scroll to the button to ensure it's in view
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
                            time.sleep(1)
                            
                            # Try multiple click methods
                            click_success = False
                            
                            # Method 1: Regular click
                            try:
                                search_button.click()
                                self.logger.info("Successfully clicked search button (regular click)")
                                click_success = True
                            except Exception as e:
                                self.logger.info(f"Regular click failed: {e}")
                            
                            # Method 2: JavaScript click if regular click failed
                            if not click_success:
                                try:
                                    self.driver.execute_script("arguments[0].click();", search_button)
                                    self.logger.info("Successfully clicked search button (JavaScript click)")
                                    click_success = True
                                except Exception as e:
                                    self.logger.info(f"JavaScript click failed: {e}")
                            
                            # Method 3: Submit form if button is in a form
                            if not click_success:
                                try:
                                    form = search_button.find_element(By.XPATH, "./ancestor::form")
                                    self.driver.execute_script("arguments[0].submit();", form)
                                    self.logger.info("Successfully submitted form")
                                    click_success = True
                                except Exception as e:
                                    self.logger.info(f"Form submit failed: {e}")
                            
                            # Method 4: Try pressing Enter on the search input
                            if not click_success:
                                try:
                                    search_input.send_keys(Keys.RETURN)
                                    self.logger.info("Successfully pressed Enter on search input")
                                    click_success = True
                                except Exception as e:
                                    self.logger.info(f"Enter key failed: {e}")
                            
                            if click_success:
                                # Wait for page to load/update
                                time.sleep(3)
                                
                                # Check if URL changed or page updated
                                url_after = self.driver.current_url
                                self.logger.info(f"URL after search: {url_after}")
                                
                                if url_before != url_after:
                                    self.logger.info("URL changed - search appears to have worked")
                                else:
                                    self.logger.info("URL didn't change - checking for dynamic content updates")
                                    
                                    # Wait for any loading indicators to disappear
                                    try:
                                        loading_selectors = [
                                            "//div[contains(@class, 'loading')]",
                                            "//div[contains(@class, 'spinner')]",
                                            "//div[contains(@class, 'loader')]"
                                        ]
                                        for loading_selector in loading_selectors:
                                            try:
                                                loading_element = self.driver.find_element(By.XPATH, loading_selector)
                                                if loading_element.is_displayed():
                                                    self.logger.info("Found loading indicator, waiting for it to disappear")
                                                    WebDriverWait(self.driver, 10).until(
                                                        EC.invisibility_of_element(loading_element)
                                                    )
                                                    break
                                            except:
                                                continue
                                    except:
                                        pass
                                
                                # Additional wait for results to load
                                time.sleep(5)
                                
                                # Try to detect if search results loaded
                                try:
                                    # Check for job results with the search keyword
                                    job_elements = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/job/')]")
                                    self.logger.info(f"Found {len(job_elements)} total job elements after search")
                                    
                                    # Check if any job contains the search keyword
                                    keyword_found = False
                                    for job in job_elements[:5]:  # Check first 5 jobs
                                        try:
                                            job_text = job.text.lower()
                                            if keyword.lower() in job_text:
                                                keyword_found = True
                                                break
                                        except:
                                            continue
                                    
                                    if keyword_found:
                                        self.logger.info(f"Search appears successful - found jobs containing '{keyword}'")
                                    else:
                                        self.logger.warning(f"Search may not have worked - no jobs found containing '{keyword}'")
                                        
                                except Exception as e:
                                    self.logger.error(f"Error checking search results: {e}")
                                    
                            else:
                                self.logger.error("All click methods failed")
                                continue
                                
                        except Exception as e:
                            self.logger.error(f"Error during search button interaction: {e}")
                            continue
                    else:
                        self.logger.warning("Could not find search button on Fuzu")
                        continue
                    # Find job listings with multiple selectors
                    job_selectors = [
                        "//a[contains(@href, '/job/')]",
                        "//div[contains(@class, 'job')]//a",
                        "//h2//a | //h3//a",
                        "//a[contains(@class, 'job-title')]"
                    ]
                    job_elements = []
                    for selector in job_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except:
                            continue

                    self.logger.info(f"Found {len(job_elements)} potential job elements for '{keyword}'")

                    for job_element in job_elements[:5]:
                        try:
                            # Extract posting date
                            date_selectors = [
                                ".//*[contains(text(), 'Posted') or contains(text(), 'Published')]",
                                ".//*[contains(@class, 'date')]",
                                ".//*[contains(text(), 'ago') or contains(text(), 'days')]"
                            ]
                            date_text = 'Not specified'
                            for selector in date_selectors:
                                try:
                                    date_elem = job_element.find_element(By.XPATH, selector)
                                    date_text_candidate = date_elem.text.strip()
                                    if date_text_candidate and len(date_text_candidate) < 50:
                                        date_text = date_text_candidate
                                        break
                                except Exception as e:
                                    self.logger.debug(f"Error extracting additional details: {str(e)}")
                                    continue

                            job_link = job_element.get_attribute('href')
                            job_title = job_element.text.strip() or job_element.get_attribute('title')
                            job_data = {
                                'job_title': job_title,
                                'link': job_link,
                                'date_posted': date_text,
                                'date_expires': 'Not specified',
                                'qualification': 'Not specified',
                                'years_of_experience': 'Not specified',
                                'location': 'Not specified',
                                'source': 'Fuzu'
                            }

                            if self.is_recent_job(job_data['date_posted']) and self.is_not_expired(job_data['date_expires']):
                                self.duplicate_urls.add(job_data['link'])
                                self.save_job_data(job_data)
                                jobs.append(job_data)
                        except Exception as e:
                            self.logger.error(f"Error processing Fuzu job: {str(e)}")
                            continue
                    
                except Exception as e:
                    self.logger.error(f"Error searching Fuzu for '{keyword}': {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in Fuzu scraping: {str(e)}")
        
        # Cache results with run configuration
        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()
        
        self.logger.info(f"Fuzu scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    def scrape_careerpointkenya(self) -> List[Dict]:
        """Scrape jobs from CareerPoint Kenya with enhanced error handling"""
        jobs = []
        self.logger.info("Starting CareerPoint Kenya scraping...")
        
        try:
            # Check cache with run configuration tracking
            cache_key = self.get_cache_key_with_config("careerpointkenya")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached CareerPoint data ({len(cached_jobs)} jobs)")
                return cached_jobs
            
            # Setup driver if not already done
            self.setup_driver()
            
            # Navigate to CareerPoint Kenya
            self.driver.get("https://www.careerpointkenya.co.ke")
            time.sleep(4)
            
            # Handle popups
            self.handle_popups()
            
            # Try to click Browse Latest Jobs
            try:
                browse_btn = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Browse Latest Jobs') or contains(@href, 'jobs')]"))
                )
                self.driver.execute_script("arguments[0].click();", browse_btn)
                time.sleep(3)
            except:
                try:
                    latest_jobs = self.driver.find_element(By.XPATH, "//a[contains(text(), 'Latest Jobs')]")
                    self.driver.execute_script("arguments[0].click();", latest_jobs)
                    time.sleep(3)
                except:
                    pass
            
            # Use ALL keywords from configuration
            keywords_to_use = self.search_keywords
            
            # For each search keyword, search in the current page content
            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching CareerPoint for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")
                    
                    # Look for job listings on current page
                    job_elements = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/20') and contains(text(), 'Job')] | //a[contains(@href, '/job/')]")
                    
                    relevant_jobs = []
                    for job_element in job_elements:
                        job_title = job_element.text.strip()
                        if self.is_relevant_job(job_title, keyword):
                            relevant_jobs.append(job_element)
                    
                    self.logger.info(f"Found {len(relevant_jobs)} relevant job listings for '{keyword}'")
                    
                    for job_element in relevant_jobs[:3]:  # Limit results per keyword
                        try:
                            job_title = job_element.text.strip()
                            job_link = job_element.get_attribute('href')
                            
                            if job_link in self.duplicate_urls:
                                continue
                            
                            # Extract date from same container
                            date_posted = 'Not specified'
                            try:
                                date_container = job_element.find_element(By.XPATH, ".//ancestor::article | .//ancestor::div")
                                date_elem = date_container.find_element(By.XPATH, ".//time[@class='entry-date published']")
                                date_posted = date_elem.text.strip()
                            except:
                                pass
                            
                            # Check if job is older than 7 days - if so, stop immediately
                            if date_posted != 'Not specified' and not self.is_recent_job(date_posted):
                                self.logger.info(f"Job older than 7 days detected: {job_title}. Stopping CareerPoint scraping.")
                                break
                            
                            if self.is_recent_job(date_posted):
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
                            
                        except Exception as e:
                            self.logger.error(f"Error processing CareerPoint job: {str(e)}")
                            continue
                    
                except Exception as e:
                    self.logger.error(f"Error searching CareerPoint for '{keyword}': {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in CareerPoint scraping: {str(e)}")
        
        # Cache results with run configuration
        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()
        
        self.logger.info(f"CareerPoint scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    def scrape_myjobsinkenya(self) -> List[Dict]:
        """Scrape jobs from MyJobsInKenya with enhanced error handling"""
        jobs = []
        self.logger.info("Starting MyJobsInKenya scraping...")
        
        try:
            # Check cache with run configuration tracking
            cache_key = self.get_cache_key_with_config("myjobsinkenya")
            if self.is_cache_valid_for_run(cache_key):
                cached_jobs = self.cache[cache_key].get('jobs', [])
                self.logger.info(f"Using cached MyJobsInKenya data ({len(cached_jobs)} jobs)")
                return cached_jobs
            
            # Setup driver if not already done
            self.setup_driver()
            
            # Navigate to MyJobsInKenya
            self.driver.get("https://www.myjobsinkenya.com/")
            time.sleep(4)
            
            # Handle popups
            self.handle_popups()
            
            # Use ALL keywords from configuration
            keywords_to_use = self.search_keywords
            
            # For each search keyword
            for keyword_idx, keyword in enumerate(keywords_to_use):
                try:
                    self.logger.info(f"Searching MyJobsInKenya for keyword {keyword_idx+1}/{len(keywords_to_use)}: {keyword}")
                    
                    # Find main search input
                    search_selectors = [
                        "//input[@placeholder='Search job title, skill or company']",
                        "//input[contains(@placeholder, 'Search')]",
                        "//input[@type='text' and contains(@class, 'search')]",
                        "//input[@name='search']"
                    ]
                    
                    search_input = None
                    for selector in search_selectors:
                        try:
                            search_input = self.driver.find_element(By.XPATH, selector)
                            if search_input.is_displayed():
                                break
                        except:
                            continue
                    
                    if search_input:
                        search_input.clear()
                        search_input.send_keys(keyword)
                        time.sleep(1)
                        
                        # Try multiple search button selectors
                        search_btn_selectors = [
                            "//button[contains(text(), 'Search')]",
                            "//input[@type='submit']",
                            "//a[contains(text(), 'Search')]",
                            "//button[contains(@class, 'search')]"
                        ]
                        
                        button_clicked = False
                        for btn_selector in search_btn_selectors:
                            try:
                                search_btn = self.driver.find_element(By.XPATH, btn_selector)
                                self.driver.execute_script("arguments[0].click();", search_btn)
                                button_clicked = True
                                break
                            except:
                                continue
                        
                        if not button_clicked:
                            search_input.send_keys(Keys.RETURN)
                        
                        time.sleep(4)
                    
                    # Find job listings
                    job_selectors = [
                        "//a[contains(@href, '/jobs/') and contains(@href, '/view')]",
                        "//a[contains(@href, '/job/')]",
                        "//div[contains(@class, 'job')]//a",
                        "//h2//a | //h3//a"
                    ]
                    
                    job_elements = []
                    for selector in job_selectors:
                        try:
                            elements = self.driver.find_elements(By.XPATH, selector)
                            if elements:
                                job_elements = elements
                                break
                        except:
                            continue
                    
                    self.logger.info(f"Found {len(job_elements)} job listings for '{keyword}'")
                    
                    for job_element in job_elements[:4]:  # Limit results per keyword
                        try:
                            job_title = job_element.text.strip()
                            job_link = job_element.get_attribute('href')
                            
                            if not self.is_relevant_job(job_title) or job_link in self.duplicate_urls:
                                continue
                            
                            # Create basic job data
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
                            
                            # Try to extract additional details if possible
                            try:
                                job_container = job_element.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'job') or contains(@class, 'listing') or contains(@class, 'card')]")
                                
                                # Extract location
                                try:
                                    location_elem = job_container.find_element(By.XPATH, ".//i[@class='fa fa-map-marker']//parent::*")
                                    job_data['location'] = location_elem.text.strip()
                                except:
                                    pass
                                
                                # Extract deadline
                                try:
                                    deadline_elem = job_container.find_element(By.XPATH, ".//*[contains(text(), 'Deadline')]")
                                    deadline_text = deadline_elem.text
                                    if 'Deadline' in deadline_text:
                                        job_data['date_expires'] = deadline_text.split('Deadline')[1].replace(':', '').strip()
                                except:
                                    pass
                            except:
                                pass
                            
                            self.duplicate_urls.add(job_link)
                            self.save_job_data(job_data)
                            jobs.append(job_data)
                            
                        except Exception as e:
                            self.logger.error(f"Error processing MyJobsInKenya job: {str(e)}")
                            continue
                    
                except Exception as e:
                    self.logger.error(f"Error searching MyJobsInKenya for '{keyword}': {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in MyJobsInKenya scraping: {str(e)}")
        
        # Cache results with run configuration
        self.cache[cache_key] = {
            'jobs': jobs,
            'run_config': self.current_run_config,
            'date': self.today.isoformat(),
            'timestamp': datetime.now().isoformat()
        }
        self.save_cache()
        
        self.logger.info(f"MyJobsInKenya scraping completed. Found {len(jobs)} relevant jobs")
        return jobs

    def generate_dashboard(self):
        """Generate an interactive HTML dashboard for scraped jobs"""
        try:
            # Load job data if not already loaded
            if not self.jobs_data:
                if os.path.exists(self.json_filename):
                    with open(self.json_filename, 'r', encoding='utf-8') as f:
                        self.jobs_data = json.load(f)
            
            if not self.jobs_data:
                self.logger.warning("No job data available for dashboard")
                return False
            
            # Prepare data for dashboard
            df = pd.DataFrame(self.jobs_data)
            
            # Generate statistics
            total_jobs = len(df)
            sources = df['source'].value_counts().to_dict()
            recent_jobs = len(df[df['date_posted'] != 'Not specified'])
            top_locations = df['location'].value_counts().head(5).to_dict()
            
            # Create job table rows
            job_rows = []
            for job in self.jobs_data:
                color_index = hash(job.get('source', '')) % 5
                colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FECA57"]
                row = f"""
                    <tr>
                        <td><strong>{job.get('job_title', 'N/A')}</strong></td>
                        <td><span class="source-badge" style="background: {colors[color_index]}">{job.get('source', 'N/A')}</span></td>
                        <td>{job.get('location', 'N/A')}</td>
                        <td>{job.get('date_posted', 'N/A')}</td>
                        <td>{job.get('date_expires', 'N/A')}</td>
                        <td>{job.get('qualification', 'N/A')}</td>
                        <td>{job.get('years_of_experience', 'N/A')}</td>
                        <td><a href="{job.get('link', '#')}" target="_blank" class="job-link">Apply</a></td>
                    </tr>"""
                job_rows.append(row)
            
            # Create dashboard HTML
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kenya Jobs Dashboard - {self.today}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 20px; color: #333;
        }}
        .container {{ 
            max-width: 1200px; margin: 0 auto; 
            background: white; border-radius: 15px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.1); overflow: hidden;
        }}
        .header {{ 
            background: linear-gradient(45deg, #FF6B6B, #4ECDC4); 
            color: white; padding: 30px; text-align: center;
        }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header p {{ font-size: 1.1em; opacity: 0.9; }}
        .stats-grid {{ 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
            gap: 20px; padding: 30px; background: #f8f9fa;
        }}
        .stat-card {{ 
            background: white; padding: 25px; border-radius: 10px; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.08); text-align: center;
            transition: transform 0.3s ease;
        }}
        .stat-card:hover {{ transform: translateY(-5px); }}
        .stat-number {{ font-size: 2.5em; font-weight: bold; color: #667eea; }}
        .stat-label {{ font-size: 1.1em; color: #666; margin-top: 10px; }}
        .charts-section {{ padding: 30px; }}
        .chart-container {{ 
            background: white; margin: 20px 0; padding: 20px; 
            border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        }}
        .jobs-table {{ 
            width: 100%; border-collapse: collapse; margin-top: 20px;
            background: white; border-radius: 10px; overflow: hidden;
        }}
        .jobs-table th {{ 
            background: #667eea; color: white; padding: 15px; 
            text-align: left; font-weight: 600;
        }}
        .jobs-table td {{ padding: 12px 15px; border-bottom: 1px solid #eee; }}
        .jobs-table tr:hover {{ background: #f8f9fa; }}
        .job-link {{ color: #667eea; text-decoration: none; font-weight: 500; }}
        .job-link:hover {{ text-decoration: underline; }}
        .source-badge {{ 
            padding: 4px 8px; border-radius: 15px; font-size: 0.8em; 
            color: white; font-weight: 500;
        }}
        .filter-section {{ 
            padding: 20px 30px; background: #f8f9fa; 
            border-bottom: 1px solid #eee;
        }}
        .filter-controls {{ 
            display: flex; gap: 15px; flex-wrap: wrap; align-items: center;
        }}
        .filter-controls select, .filter-controls input {{ 
            padding: 8px 12px; border: 1px solid #ddd; 
            border-radius: 5px; font-size: 1em;
        }}
        .export-btn {{ 
            background: #4ECDC4; color: white; padding: 10px 20px; 
            border: none; border-radius: 5px; cursor: pointer; 
            font-size: 1em; font-weight: 500;
        }}
        .export-btn:hover {{ background: #45B7B8; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Kenya Jobs Dashboard</h1>
            <p>Data Analytics & Statistics Jobs | Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_jobs}</div>
                <div class="stat-label">Total Jobs Found</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(sources)}</div>
                <div class="stat-label">Job Boards Scraped</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{recent_jobs}</div>
                <div class="stat-label">Jobs with Dates</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(df['qualification'].unique())}</div>
                <div class="stat-label">Qualification Types</div>
            </div>
        </div>
        
        <div class="filter-section">
            <div class="filter-controls">
                <label>Filter by Source:</label>
                <select id="sourceFilter" onchange="filterTable()">
                    <option value="">All Sources</option>
                    {chr(10).join([f'<option value="{source}">{source}</option>' for source in sources.keys()])}
                </select>
                
                <label>Filter by Location:</label>
                <select id="locationFilter" onchange="filterTable()">
                    <option value="">All Locations</option>
                    {chr(10).join([f'<option value="{loc}">{loc}</option>' for loc in df['location'].unique() if loc != 'Not specified'])}
                </select>
                
                <label>Search Jobs:</label>
                <input type="text" id="jobSearch" placeholder="Search job titles..." onkeyup="filterTable()">
                
                <button class="export-btn" onclick="exportToCSV()">Export CSV</button>
            </div>
        </div>
        
        <div class="charts-section">
            <div class="chart-container">
                <h3>Jobs by Source</h3>
                <canvas id="sourceChart" width="400" height="200"></canvas>
            </div>
            
            <div class="chart-container">
                <h3>Top Locations</h3>
                <canvas id="locationChart" width="400" height="200"></canvas>
            </div>
        </div>
        
        <div style="padding: 30px;">
            <h3>Job Listings</h3>
            <table class="jobs-table" id="jobsTable">
                <thead>
                    <tr>
                        <th>Job Title</th>
                        <th>Source</th>
                        <th>Location</th>
                        <th>Posted Date</th>
                        <th>Expires</th>
                        <th>Qualification</th>
                        <th>Experience</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody id="jobsTableBody">
                    {''.join(job_rows)}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Charts Data
        const sourceData = {json.dumps(list(sources.keys()))};
        const sourceCounts = {json.dumps(list(sources.values()))};
        const locationData = {json.dumps(list(top_locations.keys()))};
        const locationCounts = {json.dumps(list(top_locations.values()))};
        
        // Source Chart
        new Chart(document.getElementById('sourceChart'), {{
            type: 'doughnut',
            data: {{
                labels: sourceData,
                datasets: [{{
                    data: sourceCounts,
                    backgroundColor: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57', '#D63031', '#00B894']
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'bottom' }}
                }}
            }}
        }});
        
        // Location Chart
        new Chart(document.getElementById('locationChart'), {{
            type: 'bar',
            data: {{
                labels: locationData,
                datasets: [{{
                    label: 'Jobs',
                    data: locationCounts,
                    backgroundColor: '#667eea'
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});
        
        // Table Filtering
        function filterTable() {{
            const sourceFilter = document.getElementById('sourceFilter').value;
            const locationFilter = document.getElementById('locationFilter').value;
            const searchTerm = document.getElementById('jobSearch').value.toLowerCase();
            const rows = document.querySelectorAll('#jobsTableBody tr');
            
            rows.forEach(row => {{
                const source = row.cells[1].textContent;
                const location = row.cells[2].textContent;
                const title = row.cells[0].textContent.toLowerCase();
                
                const matchesSource = !sourceFilter || source.includes(sourceFilter);
                const matchesLocation = !locationFilter || location.includes(locationFilter);
                const matchesSearch = !searchTerm || title.includes(searchTerm);
                
                row.style.display = matchesSource && matchesLocation && matchesSearch ? '' : 'none';
            }});
        }}
        
        // Export to CSV
        function exportToCSV() {{
            const rows = Array.from(document.querySelectorAll('#jobsTable tr'));
            const csv = rows.map(row => 
                Array.from(row.querySelectorAll('th, td'))
                    .map(cell => '"' + cell.textContent.replace(/"/g, '""') + '"')
                    .join(',')
            ).join('\\n');
            
            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.setAttribute('hidden', '');
            a.setAttribute('href', url);
            a.setAttribute('download', 'kenya_jobs_{self.today}.csv');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }}
    </script>
</body>
</html>"""
            
            with open(self.dashboard_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            self.logger.info(f"Interactive dashboard generated: {self.dashboard_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error generating dashboard: {str(e)}")
            return False

    def run(self):
        """Main method to run the scraper with comprehensive reporting"""
        self.logger.info("=== Kenya Job Scraper v19 Started ===")
        start_time = datetime.now()
        initial_job_count = len(self.jobs_data)
        
        try:
            # Print initial status
            print("🚀 Kenya Job Scraper v19 - Enhanced Production Version")
            print(f"📅 Date: {self.today}")
            print(f"📂 Save Path: {self.save_path}")
            print(f"🔍 Keywords to search: {len(self.search_keywords)}")
            print(f"📊 Existing jobs: {initial_job_count}")
            print(f"🔧 Run Config: {self.current_run_config[:8]}...")
            print("-" * 60)
            
            # Scrape websites with error handling
            scraping_results = {}
            
            # MyJobMag (primary focus - most reliable)
            try:
                print("🔍 Scraping MyJobMag...")
                myjobmag_jobs = self.scrape_myjobmag()
                scraping_results['MyJobMag'] = len(myjobmag_jobs)
                print(f"✅ MyJobMag: {len(myjobmag_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"MyJobMag failed: {str(e)}")
                scraping_results['MyJobMag'] = 0
                print(f"❌ MyJobMag: Failed")
            
            # BrighterMonday
            try:
                print("🔍 Scraping BrighterMonday...")
                brightermonday_jobs = self.scrape_brightermonday()
                scraping_results['BrighterMonday'] = len(brightermonday_jobs)
                print(f"✅ BrighterMonday: {len(brightermonday_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"BrighterMonday failed: {str(e)}")
                scraping_results['BrighterMonday'] = 0
                print(f"❌ BrighterMonday: Failed")
            
            # Fuzu (enhanced with better human verification)
            try:
                print("🔍 Scraping Fuzu...")
                fuzu_jobs = self.scrape_fuzu()
                scraping_results['Fuzu'] = len(fuzu_jobs)
                print(f"✅ Fuzu: {len(fuzu_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"Fuzu failed: {str(e)}")
                scraping_results['Fuzu'] = 0
                print(f"❌ Fuzu: Failed")
            
            # CareerPoint Kenya
            try:
                print("🔍 Scraping CareerPoint Kenya...")
                careerpointkenya_jobs = self.scrape_careerpointkenya()
                scraping_results['CareerPoint Kenya'] = len(careerpointkenya_jobs)
                print(f"✅ CareerPoint Kenya: {len(careerpointkenya_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"CareerPoint Kenya failed: {str(e)}")
                scraping_results['CareerPoint Kenya'] = 0
                print(f"❌ CareerPoint Kenya: Failed")
            
            # MyJobsInKenya
            try:
                print("🔍 Scraping MyJobsInKenya...")
                myjobsinkenya_jobs = self.scrape_myjobsinkenya()
                scraping_results['MyJobsInKenya'] = len(myjobsinkenya_jobs)
                print(f"✅ MyJobsInKenya: {len(myjobsinkenya_jobs)} jobs")
            except Exception as e:
                self.logger.error(f"MyJobsInKenya failed: {str(e)}")
                scraping_results['MyJobsInKenya'] = 0
                print(f"❌ MyJobsInKenya: Failed")
            
            # Generate dashboard
            dashboard_created = False
            try:
                print("🎨 Generating dashboard...")
                dashboard_created = self.generate_dashboard()
                if dashboard_created:
                    print(f"✅ Dashboard: {os.path.basename(self.dashboard_filename)}")
                else:
                    print("❌ Dashboard: Failed to generate")
            except Exception as e:
                self.logger.error(f"Dashboard generation failed: {str(e)}")
                print("❌ Dashboard: Error occurred")
            
            # Calculate results
            new_jobs_count = len(self.jobs_data) - initial_job_count
            total_time = datetime.now() - start_time
            
            # Display comprehensive results
            print("\n" + "="*80)
            print("📋 ENHANCED SCRAPING RESULTS")
            print("="*80)
            print(f"📊 Jobs in database: {len(self.jobs_data)}")
            print(f"🆕 New jobs added: {new_jobs_count}")
            print(f"⏱️  Time taken: {total_time}")
            print(f"🎯 Success rate: {(sum(1 for count in scraping_results.values() if count > 0)/len(scraping_results)*100):.1f}%")
            print(f"🔧 Cache strategy: Run-based (no time limits)")
            
            print(f"\n📈 RESULTS BY SOURCE:")
            for source, count in scraping_results.items():
                status = "✅" if count > 0 else "❌"
                print(f"   {status} {source:<20}: {count:>3} jobs")
            
            print(f"\n📁 FILES GENERATED:")
            print(f"   📄 JSON: {os.path.basename(self.json_filename)}")
            print(f"   📊 CSV:  {os.path.basename(self.csv_filename)}")
            if dashboard_created:
                print(f"   🎨 Dashboard: {os.path.basename(self.dashboard_filename)}")
            
            print(f"\n🔍 SEARCH KEYWORDS USED:")
            for i, keyword in enumerate(self.search_keywords, 1):
                print(f"   {i:2d}. {keyword}")
            
            print(f"\n💡 ENHANCED FEATURES:")
            print(f"   🤖 Advanced human verification handling")
            print(f"   📋 Smart caching based on run configuration")
            print(f"   🔄 Better error recovery and retry logic")
            print(f"   🎯 Enhanced popup handling across all sites")
            print(f"   📊 Real-time progress tracking")
            
            if new_jobs_count > 0:
                print(f"\n🎉 NEW JOBS FOUND:")
                recent_jobs = self.jobs_data[-new_jobs_count:]
                for i, job in enumerate(recent_jobs[:5], 1):  # Show max 5
                    print(f"   {i}. {job.get('job_title', 'N/A')}")
                    print(f"      🏢 {job.get('source', 'N/A')}")
                    if job.get('date_posted') != 'Not specified':
                        print(f"      📅 Posted: {job.get('date_posted')}")
                    if job.get('location') != 'Not specified':
                        print(f"      📍 {job.get('location')}")
                    print()
                
                if new_jobs_count > 5:
                    print(f"   ... and {new_jobs_count - 5} more jobs")
            else:
                print(f"\n💡 NO NEW JOBS FOUND")
                print("   Possible reasons:")
                print("   • All recent jobs already in database")
                print("   • No jobs matching criteria in last 14 days")
                print("   • Keywords may need adjustment")
                print("   • Cache may be serving previous results")
            
            # Display file locations for easy access
            print(f"\n📂 FILE LOCATIONS:")
            print(f"   JSON: {self.json_filename}")
            print(f"   CSV:  {self.csv_filename}")
            if dashboard_created:
                print(f"   Dashboard: {self.dashboard_filename}")
                print(f"\n🌐 To view dashboard: Open the HTML file in your browser")
                print(f"   Or in Jupyter: import webbrowser; webbrowser.open('{self.dashboard_filename}')")
            
            # Performance metrics
            if new_jobs_count > 0:
                jobs_per_minute = (new_jobs_count / total_time.total_seconds()) * 60
                print(f"\n⚡ PERFORMANCE:")
                print(f"   Jobs per minute: {jobs_per_minute:.1f}")
                print(f"   Average time per job: {total_time.total_seconds()/new_jobs_count:.1f}s")
            
            print(f"\n🔄 NEXT STEPS:")
            print(f"   1. Review the CSV file for job details")
            if dashboard_created:
                print(f"   2. Open dashboard for visual analysis")
            print(f"   3. Update search keywords if needed")
            print(f"   4. Run again for fresh updates (cache will auto-refresh)")
            print(f"   5. Check logs for detailed operation information")
            
            # Display CSV preview
            if new_jobs_count > 0:
                print(f"\n📋 CSV PREVIEW (Latest {min(3, new_jobs_count)} jobs):")
                try:
                    df = pd.DataFrame(self.jobs_data)
                    preview_df = df[['job_title', 'source', 'location', 'date_posted']].tail(min(3, new_jobs_count))
                    print(preview_df.to_string(index=False))
                except Exception as e:
                    print(f"   Could not generate preview: {str(e)}")
            
            # Display cache information
            print(f"\n🗄️  CACHE INFORMATION:")
            print(f"   Cache entries: {len(self.cache)}")
            print(f"   Run config: {self.current_run_config[:12]}...")
            print(f"   Cache strategy: Configuration-based invalidation")
            
            # Display full CSV path for easy access
            print(f"\n📁 FULL FILE PATHS:")
            print(f"   JSON: {self.json_filename}")
            print(f"   CSV:  {self.csv_filename}")
            if dashboard_created:
                print(f"   HTML: {self.dashboard_filename}")
                
        except Exception as e:
            self.logger.error(f"Error in main execution: {str(e)}")
            print(f"❌ Fatal error: {str(e)}")
        finally:
            # Cleanup
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")
        
        self.logger.info("=== Kenya Job Scraper v19 Finished ===")


def main():
    """Main function with enhanced user interface"""
    print("="*80)
    print("🇰🇪 KENYA JOB SCRAPER v19 - ENHANCED DATA ANALYTICS EDITION")
    print("="*80)
    print("🎯 Targeting: Data Analytics, Statistics, and BI roles")
    print("🌐 Sources: MyJobMag, BrighterMonday, Fuzu, CareerPoint, MyJobsInKenya")
    print("📊 Output: JSON, CSV, and Interactive Dashboard")
    print("🔧 Features: Enhanced Human Verification, Smart Caching, Error Recovery")
    print("💡 New: Configuration-based cache invalidation")
    print("🤖 Enhanced: Fuzu human verification with extended wait times")
    print("-" * 80)
    
    # Configuration
    save_path = "C:\\Users\\USER\\Documents\\app\\Jobs\\"
    
    try:
        # Initialize and run scraper
        scraper = KenyaJobScraper(save_path=save_path)
        scraper.run()
        
        print("\n✅ Enhanced scraping completed successfully!")
        print("📁 Check the generated files in:", save_path)
        print("🎨 Dashboard available for interactive visualization")
        print("🔧 Cache system optimized for better performance")
        
    except KeyboardInterrupt:
        print("\n⏹️  Scraping interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        print("📝 Check the log file for detailed error information")


if __name__ == "__main__":
    main()
