"""
Arteq Job Signal Scraper — JSearch API (RapidAPI Free Tier)
Free: 200 requests/month via RapidAPI
Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
"""

import requests
import time
import logging
from datetime import datetime, timedelta
from config import JSEARCH_API_KEY, LOCATIONS, TIER1_QUERIES, TIER2_QUERIES

logger = logging.getLogger(__name__)

BASE_URL = "https://jsearch.p.rapidapi.com/search"

HEADERS = {
    "X-RapidAPI-Key": JSEARCH_API_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}


def search_jobs(query: str, country: str, page: int = 1, num_pages: int = 1) -> list[dict]:
    """
    Search JSearch API for a single query + country.
    Returns list of raw job objects.
    """
    params = {
        "query": f"{query} in {country}",
        "page": str(page),
        "num_pages": str(num_pages),
        "date_posted": "week",  # Only last 7 days
    }

    try:
        resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "OK" and data.get("data"):
            return data["data"]
        return []

    except requests.exceptions.RequestException as e:
        logger.error(f"JSearch API error for '{query}' in {country}: {e}")
        return []


def normalize_job(raw: dict) -> dict:
    """
    Transform a raw JSearch job object into our unified schema.
    """
    # Extract employer info
    employer = raw.get("employer_name", "Unknown")
    employer_logo = raw.get("employer_logo", "")
    company_type = raw.get("employer_company_type", "")

    # Location
    city = raw.get("job_city", "")
    state = raw.get("job_state", "")
    country = raw.get("job_country", "")
    is_remote = raw.get("job_is_remote", False)
    location_parts = [p for p in [city, state, country] if p]
    location_str = ", ".join(location_parts)
    if is_remote:
        location_str = f"{location_str} (Remote)" if location_str else "Remote"

    # Date
    posted_ts = raw.get("job_posted_at_datetime_utc", "")
    posted_date = ""
    if posted_ts:
        try:
            posted_date = datetime.fromisoformat(posted_ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            posted_date = posted_ts[:10] if len(posted_ts) >= 10 else ""

    # Description for signal detection
    description = raw.get("job_description", "")

    # Employment type
    employment_type = raw.get("job_employment_type", "")

    # Experience
    exp = raw.get("job_required_experience", {}) or {}
    min_exp = exp.get("required_experience_in_months")

    # Company size from highlights
    highlights = raw.get("job_highlights", {}) or {}

    return {
        "company_name": employer,
        "role_title": raw.get("job_title", ""),
        "description": description[:2000],  # Truncate for memory
        "location": location_str,
        "posted_date": posted_date,
        "source": "JSearch",
        "source_url": raw.get("job_apply_link", "") or raw.get("job_google_link", ""),
        "employment_type": employment_type,
        "company_type": company_type,
        "is_remote": is_remote,
        "min_experience_months": min_exp,
        "raw_employer_logo": employer_logo,
    }


def run_jsearch_scraper(max_queries: int = 30) -> list[dict]:
    """
    Run the full JSearch scraping pipeline.
    
    Budget management:
    - Free tier: 200 requests/month
    - Daily budget: ~6-7 requests/day (200 / 30 days)
    - Prioritize Tier 1 (fractional/interim) queries
    
    Args:
        max_queries: Maximum API calls for this run (default: 6 for daily use on free tier)
    """
    all_jobs = []
    queries_used = 0

    # Prioritize Tier 1 queries (explicit fractional/interim)
    priority_queries = []
    
    # Rotate through Tier 1 queries - pick a subset each day
    day_of_month = datetime.now().day
    tier1_subset = TIER1_QUERIES[day_of_month % len(TIER1_QUERIES)::max(1, len(TIER1_QUERIES) // 4)][:3]
    tier2_subset = TIER2_QUERIES[day_of_month % len(TIER2_QUERIES)::max(1, len(TIER2_QUERIES) // 3)][:2]
    
    priority_queries = tier1_subset + tier2_subset

    # Rotate through countries
    countries = ["Germany", "Austria", "Switzerland"]
    country_idx = day_of_month % len(countries)
    today_country = countries[country_idx]

    logger.info(f"Today's queries: {priority_queries}")
    logger.info(f"Today's country focus: {today_country}")

    for query in priority_queries:
        if queries_used >= max_queries:
            logger.info(f"Daily query budget reached ({max_queries})")
            break

        logger.info(f"Searching: '{query}' in {today_country}")
        raw_jobs = search_jobs(query, today_country)
        queries_used += 1

        for raw in raw_jobs:
            normalized = normalize_job(raw)
            normalized["search_query"] = query
            all_jobs.append(normalized)

        # Respectful rate limiting
        time.sleep(1)

    logger.info(f"JSearch: {queries_used} queries used, {len(all_jobs)} jobs found")
    return all_jobs
