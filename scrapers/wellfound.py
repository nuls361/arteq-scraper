"""
A-Line Job Signal Scraper — Wellfound (ex-AngelList) Scraper
Free: No API key required, direct web scraping
Focus: Startup/Scale-up executive roles in DACH
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Wellfound search URLs for DACH startup roles
WELLFOUND_SEARCHES = [
    {
        "url": "https://wellfound.com/role/l/cfo/germany",
        "role_hint": "CFO",
    },
    {
        "url": "https://wellfound.com/role/l/cto/germany",
        "role_hint": "CTO",
    },
    {
        "url": "https://wellfound.com/role/l/coo/germany",
        "role_hint": "COO",
    },
    {
        "url": "https://wellfound.com/role/l/head-of-finance/germany",
        "role_hint": "Head of Finance",
    },
    {
        "url": "https://wellfound.com/role/l/head-of-engineering/germany",
        "role_hint": "Head of Engineering",
    },
    {
        "url": "https://wellfound.com/role/l/head-of-people/germany",
        "role_hint": "Head of People",
    },
    {
        "url": "https://wellfound.com/role/l/vp-of-finance/germany",
        "role_hint": "VP Finance",
    },
    {
        "url": "https://wellfound.com/role/l/head-of-product/germany",
        "role_hint": "Head of Product",
    },
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
})


def scrape_wellfound_page(url: str, role_hint: str) -> list[dict]:
    """
    Scrape a single Wellfound search results page.
    Wellfound uses Next.js with server-rendered content — 
    we look for __NEXT_DATA__ JSON or parse HTML directly.
    """
    jobs = []

    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Method 1: Try to find __NEXT_DATA__ script tag (structured data)
        next_data_script = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data_script:
            try:
                data = json.loads(next_data_script.string)
                jobs.extend(parse_next_data(data, role_hint))
                if jobs:
                    return jobs
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Could not parse __NEXT_DATA__: {e}")

        # Method 2: Parse HTML structure directly
        # Wellfound job cards typically have role titles and company names
        job_cards = soup.select("[data-test='JobCard'], .styles_component__card, div[class*='JobCard']")
        
        if not job_cards:
            # Fallback: look for any structured job-like content
            job_cards = soup.find_all("div", class_=re.compile(r"job|listing|card", re.I))

        for card in job_cards:
            job = parse_job_card(card, role_hint, url)
            if job and job.get("role_title"):
                jobs.append(job)

        # Method 3: Look for JSON-LD structured data
        json_ld = soup.find_all("script", {"type": "application/ld+json"})
        for script in json_ld:
            try:
                ld_data = json.loads(script.string)
                if isinstance(ld_data, dict) and ld_data.get("@type") == "JobPosting":
                    jobs.append(parse_json_ld(ld_data, role_hint))
                elif isinstance(ld_data, list):
                    for item in ld_data:
                        if isinstance(item, dict) and item.get("@type") == "JobPosting":
                            jobs.append(parse_json_ld(item, role_hint))
            except (json.JSONDecodeError, KeyError):
                continue

    except requests.exceptions.RequestException as e:
        logger.error(f"Wellfound scrape error for {url}: {e}")

    return jobs


def parse_next_data(data: dict, role_hint: str) -> list[dict]:
    """Parse jobs from Wellfound's __NEXT_DATA__ JSON."""
    jobs = []
    try:
        # Navigate the Next.js data structure (may change, hence try/except)
        props = data.get("props", {}).get("pageProps", {})
        
        # Try different possible data paths
        job_listings = (
            props.get("jobListings", []) or
            props.get("jobs", []) or
            props.get("results", []) or
            []
        )
        
        for listing in job_listings:
            startup = listing.get("startup", listing.get("company", {})) or {}
            job = {
                "company_name": startup.get("name", ""),
                "role_title": listing.get("title", listing.get("role", role_hint)),
                "description": listing.get("description", "")[:2000],
                "location": listing.get("location", listing.get("locationNames", "")),
                "posted_date": "",
                "source": "Wellfound",
                "source_url": f"https://wellfound.com/jobs/{listing.get('slug', '')}",
                "employment_type": listing.get("type", ""),
                "company_type": "Startup",
                "is_remote": listing.get("remote", False),
                "company_size": startup.get("company_size", ""),
                "funding_info": startup.get("high_concept", ""),
            }
            if job["company_name"]:
                jobs.append(job)
    except (KeyError, TypeError) as e:
        logger.debug(f"Next.js data parsing error: {e}")

    return jobs


def parse_job_card(card, role_hint: str, page_url: str) -> dict:
    """Parse a job from an HTML card element."""
    try:
        # Try to extract title
        title_el = (
            card.find(["h2", "h3", "h4"]) or
            card.find("a", class_=re.compile(r"title|name|role", re.I)) or
            card.find("span", class_=re.compile(r"title|name|role", re.I))
        )
        title = title_el.get_text(strip=True) if title_el else ""

        # Try to extract company
        company_el = (
            card.find("a", class_=re.compile(r"company|startup", re.I)) or
            card.find("span", class_=re.compile(r"company|startup", re.I)) or
            card.find("h3") if card.find("h2") else None
        )
        company = company_el.get_text(strip=True) if company_el else ""

        # Try to extract location
        location_el = card.find(string=re.compile(r"Berlin|Munich|Hamburg|Vienna|Zurich|Remote|Germany|Austria|Switzerland", re.I))
        location = str(location_el).strip() if location_el else ""

        # Try to extract link
        link_el = card.find("a", href=True)
        link = ""
        if link_el:
            href = link_el["href"]
            link = href if href.startswith("http") else f"https://wellfound.com{href}"

        return {
            "company_name": company,
            "role_title": title or role_hint,
            "description": card.get_text(" ", strip=True)[:2000],
            "location": location,
            "posted_date": datetime.now().strftime("%Y-%m-%d"),
            "source": "Wellfound",
            "source_url": link or page_url,
            "employment_type": "",
            "company_type": "Startup",
            "is_remote": bool(re.search(r"remote", card.get_text(), re.I)),
        }
    except Exception as e:
        logger.debug(f"Card parsing error: {e}")
        return {}


def parse_json_ld(data: dict, role_hint: str) -> dict:
    """Parse a job from JSON-LD structured data."""
    org = data.get("hiringOrganization", {}) or {}
    location = data.get("jobLocation", {})
    if isinstance(location, list) and location:
        location = location[0]
    address = location.get("address", {}) if isinstance(location, dict) else {}

    return {
        "company_name": org.get("name", ""),
        "role_title": data.get("title", role_hint),
        "description": data.get("description", "")[:2000],
        "location": f"{address.get('addressLocality', '')}, {address.get('addressCountry', '')}".strip(", "),
        "posted_date": data.get("datePosted", "")[:10],
        "source": "Wellfound",
        "source_url": data.get("url", ""),
        "employment_type": data.get("employmentType", ""),
        "company_type": "Startup",
        "is_remote": "TELECOMMUTE" in str(data.get("jobLocationType", "")),
    }


def run_wellfound_scraper() -> list[dict]:
    """
    Run the full Wellfound scraping pipeline.
    Free: No API limits, just respectful crawling.
    """
    all_jobs = []

    for search in WELLFOUND_SEARCHES:
        logger.info(f"Scraping Wellfound: {search['role_hint']} ({search['url']})")
        jobs = scrape_wellfound_page(search["url"], search["role_hint"])
        all_jobs.extend(jobs)
        
        # Respectful delay between requests
        time.sleep(2)

    logger.info(f"Wellfound: {len(all_jobs)} jobs found across {len(WELLFOUND_SEARCHES)} searches")
    return all_jobs
