"""
A-Line Job Signal Scraper — Scoring Engine

Additive scoring (0-100):
  +40  Explicit fractional/interim in title
  +25  Fractional signal in body text
  +15  Recent funding signal
  +10  Company size 10-200 (sweet spot)
  +5   DACH location confirmed
  +5   C-Level title (vs Head-of)

Tiers:
  > 70  = Hot Lead   → daily review
  40-70 = Warm Lead  → weekly review
  < 40  = Parked     → monthly check
"""

import re
import logging
from config import (
    FRACTIONAL_BODY_SIGNALS, EXCLUDED_COMPANIES, EXCLUDED_TITLE_WORDS,
    SCORING, TITLE_KEYWORDS_CLEVEL, TITLE_KEYWORDS_VP, TITLE_KEYWORDS_HEAD,
    ENGAGEMENT_KEYWORDS, FUNCTION_MAP,
)

logger = logging.getLogger(__name__)


def should_exclude(job: dict) -> bool:
    """Check if job should be excluded (staffing agencies, juniors, etc.)."""
    company_lower = job.get("company_name", "").lower()
    title_lower = job.get("role_title", "").lower()

    # Exclude staffing agencies
    for excluded in EXCLUDED_COMPANIES:
        if excluded in company_lower:
            return True

    # Exclude non-exec roles
    for excluded_word in EXCLUDED_TITLE_WORDS:
        if excluded_word in title_lower:
            return True

    return False


def detect_engagement_type(job: dict) -> str:
    """Detect if the role is Fractional, Interim, or Full-time."""
    title_lower = job.get("role_title", "").lower()
    desc_lower = job.get("description", "").lower()

    for keyword in ENGAGEMENT_KEYWORDS:
        kw_lower = keyword.lower()
        if kw_lower in title_lower:
            if kw_lower in ["fractional", "interim"]:
                return "Fractional" if "fractional" in kw_lower else "Interim"
            return "Fractional"  # part-time, teilzeit etc. → fractional

    # Check body text
    for keyword in ENGAGEMENT_KEYWORDS:
        if keyword.lower() in desc_lower:
            return "Fractional"

    return "Full-time"


def detect_fractional_signals(job: dict) -> list[str]:
    """Extract all fractional/interim signals from job posting."""
    signals = []
    title_lower = job.get("role_title", "").lower()
    desc_lower = job.get("description", "").lower()

    # Title signals
    for kw in ENGAGEMENT_KEYWORDS:
        if kw.lower() in title_lower:
            signals.append(f"'{kw}' in title")

    # Body text signals
    for signal in FRACTIONAL_BODY_SIGNALS:
        if signal.lower() in desc_lower:
            signals.append(f"'{signal}' in description")

    # Remote + part-time combination
    if job.get("is_remote") and any(s.lower() in desc_lower for s in ["part-time", "teilzeit", "3 days", "2 days"]):
        signals.append("Remote + part-time")

    return list(set(signals))  # Deduplicate


def detect_role_level(job: dict) -> str:
    """Classify role as C-Level, VP, or Head/Director."""
    title_lower = job.get("role_title", "").lower()

    for kw in TITLE_KEYWORDS_CLEVEL:
        if kw.lower() in title_lower:
            return "C-Level"

    for kw in TITLE_KEYWORDS_VP:
        if kw.lower() in title_lower:
            return "VP"

    for kw in TITLE_KEYWORDS_HEAD:
        if kw.lower() in title_lower:
            return "Head/Director"

    return "Unknown"


def detect_role_function(job: dict) -> str:
    """Map role to a function (Finance, Engineering, People, etc.)."""
    title_lower = job.get("role_title", "").lower()
    desc_lower = job.get("description", "").lower()[:500]

    for function, keywords in FUNCTION_MAP.items():
        for kw in keywords:
            if kw in title_lower:
                return function

    # Fallback: check description
    for function, keywords in FUNCTION_MAP.items():
        for kw in keywords:
            if kw in desc_lower:
                return function

    return "Other"


def calculate_score(job: dict, engagement_type: str, signals: list[str], role_level: str) -> int:
    """Calculate composite lead score (0-100)."""
    score = 0

    # +40: Explicit fractional/interim in title
    title_lower = job.get("role_title", "").lower()
    if any(kw.lower() in title_lower for kw in ["fractional", "interim"]):
        score += SCORING["explicit_fractional_interim_title"]

    # +25: Fractional signal in body text
    if signals and score < 40:  # Only add if not already Hot from title
        score += SCORING["fractional_signal_body"]

    # +15: Recent funding (if we have the data)
    funding = job.get("funding_info", "")
    if funding and any(kw in str(funding).lower() for kw in ["series", "seed", "funding", "raised"]):
        score += SCORING["recent_funding"]

    # +10: Company size sweet spot (10-200 employees)
    company_size = job.get("company_size", "")
    if company_size:
        # Try to extract number
        nums = re.findall(r'\d+', str(company_size))
        if nums:
            size = int(nums[0])
            if 10 <= size <= 200:
                score += SCORING["company_size_sweet_spot"]

    # +5: DACH location confirmed
    location = job.get("location", "").lower()
    dach_signals = ["germany", "deutschland", "austria", "österreich",
                    "switzerland", "schweiz", "berlin", "munich", "münchen",
                    "hamburg", "frankfurt", "cologne", "köln", "vienna", "wien",
                    "zurich", "zürich", "düsseldorf", "stuttgart"]
    if any(s in location for s in dach_signals):
        score += SCORING["dach_confirmed"]

    # +5: C-Level title (higher value mandate)
    if role_level == "C-Level":
        score += SCORING["clevel_title"]

    # Bonus: Startup/Scale-up company type
    if job.get("company_type", "").lower() in ["startup", "scale-up"]:
        score += 5

    return min(score, 100)


def determine_tier(score: int) -> str:
    """Assign lead tier based on score."""
    if score > 70:
        return "Hot"
    elif score >= 40:
        return "Warm"
    else:
        return "Parked"


def score_job(job: dict) -> dict | None:
    """
    Full scoring pipeline for a single job.
    Returns enriched job dict or None if excluded.
    """
    if should_exclude(job):
        logger.debug(f"Excluded: {job.get('company_name')} - {job.get('role_title')}")
        return None

    engagement_type = detect_engagement_type(job)
    signals = detect_fractional_signals(job)
    role_level = detect_role_level(job)
    role_function = detect_role_function(job)
    score = calculate_score(job, engagement_type, signals, role_level)
    tier = determine_tier(score)

    # Enrich job with scoring data
    job["engagement_type"] = engagement_type
    job["fractional_signals"] = "; ".join(signals) if signals else ""
    job["role_level"] = role_level
    job["role_function"] = role_function
    job["score"] = score
    job["signal_tier"] = tier

    return job


def score_all_jobs(jobs: list[dict]) -> list[dict]:
    """Score all jobs and return only non-excluded results, sorted by score."""
    scored = []
    excluded_count = 0

    for job in jobs:
        result = score_job(job)
        if result:
            scored.append(result)
        else:
            excluded_count += 1

    scored.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Scored {len(scored)} jobs, excluded {excluded_count}")
    return scored
