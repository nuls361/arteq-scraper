"""
A-Line Job Signal Scraper — Deduplication

Dedup key: normalize(company_name) + normalize(role_function) + country
This catches the same role posted on multiple platforms.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Company name suffixes to strip for normalization
COMPANY_SUFFIXES = [
    "gmbh", "ag", "ug", "se", "ltd", "inc", "corp", "co.",
    "haftungsbeschränkt", "limited", "corporation", "company",
    "& co", "& co.", "kg", "ohg", "gbr", "e.v.", "sarl", "sas",
]


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for dedup matching.
    'Taxfix GmbH' and 'taxfix' → 'taxfix'
    """
    name = name.lower().strip()

    # Remove common suffixes
    for suffix in COMPANY_SUFFIXES:
        name = re.sub(rf'\b{re.escape(suffix)}\b', '', name)

    # Remove special characters, extra whitespace
    name = re.sub(r'[^a-z0-9]', '', name)

    return name


def extract_country(location: str) -> str:
    """Extract country code from location string."""
    location_lower = location.lower()

    if any(s in location_lower for s in ["germany", "deutschland", "berlin",
            "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln",
            "düsseldorf", "stuttgart", "leipzig", "dresden", "hannover"]):
        return "de"
    elif any(s in location_lower for s in ["austria", "österreich", "vienna", "wien", "graz", "salzburg"]):
        return "at"
    elif any(s in location_lower for s in ["switzerland", "schweiz", "zurich", "zürich", "bern", "basel", "geneva", "genf"]):
        return "ch"
    else:
        return "unknown"


def generate_dedup_key(job: dict) -> str:
    """
    Generate deduplication key.
    Format: normalized_company + role_function + country
    """
    company = normalize_company_name(job.get("company_name", ""))
    function = job.get("role_function", "other").lower().replace(" ", "")
    country = extract_country(job.get("location", ""))

    return f"{company}_{function}_{country}"


def deduplicate_jobs(new_jobs: list[dict], existing_keys: set[str] = None) -> tuple[list[dict], list[dict]]:
    """
    Deduplicate jobs.
    
    Returns:
        (new_unique_jobs, updated_jobs)
        - new_unique_jobs: Jobs not seen before
        - updated_jobs: Jobs already seen but with new source info
    """
    if existing_keys is None:
        existing_keys = set()

    seen_this_run = {}
    new_unique = []
    updates = []

    for job in new_jobs:
        dedup_key = generate_dedup_key(job)
        job["dedup_key"] = dedup_key

        if dedup_key in existing_keys:
            # Already in sheet — could update source or date
            updates.append(job)
            logger.debug(f"Duplicate (existing): {job.get('company_name')} - {job.get('role_function')}")

        elif dedup_key in seen_this_run:
            # Duplicate within this batch — keep highest score
            existing = seen_this_run[dedup_key]
            if job.get("score", 0) > existing.get("score", 0):
                seen_this_run[dedup_key] = job
                logger.debug(f"Duplicate (batch, higher score): {job.get('company_name')}")
            else:
                # Append source info to existing
                existing_source = existing.get("source", "")
                new_source = job.get("source", "")
                if new_source and new_source not in existing_source:
                    existing["source"] = f"{existing_source}, {new_source}"
        else:
            seen_this_run[dedup_key] = job

    new_unique = list(seen_this_run.values())
    
    # Add timestamps
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for job in new_unique:
        job["first_seen"] = now
        job["last_updated"] = now
        job["status"] = "New"

    logger.info(f"Dedup: {len(new_unique)} unique new leads, {len(updates)} duplicates of existing")
    return new_unique, updates
