#!/usr/bin/env python3
"""
Arteq Job Signal Scraper — Main Orchestration

Daily pipeline:
1. Scrape jobs from JSearch (API) + Wellfound (web)
2. Score each job (engagement type, signals, role level, composite score)
3. Deduplicate across sources and against existing leads
4. Write to Google Sheets (or CSV fallback)

Usage:
    python main.py                  # Full run (JSearch + Wellfound)
    python main.py --source jsearch # JSearch only
    python main.py --source wellfound # Wellfound only
    python main.py --dry-run        # Score and print, don't write to sheets
"""

import argparse
import logging
import time
from datetime import datetime

from scrapers.jsearch import run_jsearch_scraper
from scrapers.wellfound import run_wellfound_scraper
from scorer import score_all_jobs
from dedup import deduplicate_jobs
from sheets_writer import write_to_sheets, get_sheets_client, get_existing_dedup_keys

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("arteq-scraper")


def run_pipeline(source: str = "all", dry_run: bool = False, max_queries: int = 6):
    """Execute the full scraping pipeline."""
    start_time = time.time()
    errors = []
    
    logger.info("=" * 60)
    logger.info("Arteq Job Signal Scraper — Starting")
    logger.info(f"Source: {source} | Dry run: {dry_run} | Max queries: {max_queries}")
    logger.info("=" * 60)

    # ── Step 1: Scrape ──────────────────────────────────────
    raw_jobs = []

    if source in ("all", "jsearch"):
        try:
            logger.info("▸ Running JSearch scraper...")
            jsearch_jobs = run_jsearch_scraper(max_queries=max_queries)
            raw_jobs.extend(jsearch_jobs)
            logger.info(f"  JSearch returned {len(jsearch_jobs)} jobs")
        except Exception as e:
            logger.error(f"  JSearch scraper failed: {e}")
            errors.append(f"JSearch: {e}")

    if source in ("all", "wellfound"):
        try:
            logger.info("▸ Running Wellfound scraper...")
            wf_jobs = run_wellfound_scraper()
            raw_jobs.extend(wf_jobs)
            logger.info(f"  Wellfound returned {len(wf_jobs)} jobs")
        except Exception as e:
            logger.error(f"  Wellfound scraper failed: {e}")
            errors.append(f"Wellfound: {e}")

    if not raw_jobs:
        logger.warning("No jobs found from any source. Exiting.")
        return

    logger.info(f"  Total raw jobs: {len(raw_jobs)}")

    # ── Step 2: Score ───────────────────────────────────────
    logger.info("▸ Scoring jobs...")
    scored_jobs = score_all_jobs(raw_jobs)
    
    hot = sum(1 for j in scored_jobs if j.get("signal_tier") == "Hot")
    warm = sum(1 for j in scored_jobs if j.get("signal_tier") == "Warm")
    parked = sum(1 for j in scored_jobs if j.get("signal_tier") == "Parked")
    logger.info(f"  Scored: {len(scored_jobs)} | Hot: {hot} | Warm: {warm} | Parked: {parked}")

    # ── Step 3: Deduplicate ─────────────────────────────────
    logger.info("▸ Deduplicating...")
    
    # Try to get existing keys from Google Sheets
    existing_keys = set()
    if not dry_run:
        try:
            client = get_sheets_client()
            if client:
                from config import GOOGLE_SHEET_ID
                spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
                existing_keys = get_existing_dedup_keys(spreadsheet)
                logger.info(f"  Loaded {len(existing_keys)} existing dedup keys from sheets")
        except Exception as e:
            logger.debug(f"  Could not load existing keys: {e}")

    unique_jobs, updated_jobs = deduplicate_jobs(scored_jobs, existing_keys)
    logger.info(f"  Unique new leads: {len(unique_jobs)} | Duplicates: {len(updated_jobs)}")

    # ── Step 4: Output ──────────────────────────────────────
    duration = round(time.time() - start_time, 1)

    run_stats = {
        "queries_used": max_queries if source in ("all", "jsearch") else 0,
        "raw_jobs": len(raw_jobs),
        "scored_jobs": len(scored_jobs),
        "deduped_jobs": len(unique_jobs),
        "duration_seconds": duration,
        "errors": "; ".join(errors) if errors else "",
    }

    if dry_run:
        logger.info("▸ DRY RUN — printing results instead of writing to sheets")
        print_results(unique_jobs)
    else:
        logger.info("▸ Writing to Google Sheets (or CSV fallback)...")
        success = write_to_sheets(unique_jobs, run_stats)
        if success:
            logger.info("  Write successful!")
        else:
            logger.error("  Write failed!")

    # ── Summary ─────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Run complete!")
    logger.info(f"  Duration: {duration}s")
    logger.info(f"  New leads: {len(unique_jobs)}")
    hot_new = sum(1 for j in unique_jobs if j.get("signal_tier") == "Hot")
    warm_new = sum(1 for j in unique_jobs if j.get("signal_tier") == "Warm")
    logger.info(f"  Hot: {hot_new} | Warm: {warm_new} | Parked: {len(unique_jobs) - hot_new - warm_new}")
    if errors:
        logger.warning(f"  Errors: {'; '.join(errors)}")
    logger.info("=" * 60)


def print_results(jobs: list[dict]):
    """Pretty-print results for dry run."""
    if not jobs:
        print("\n  No new leads found.\n")
        return

    print(f"\n{'='*90}")
    print(f"  {'Score':>5}  {'Tier':6}  {'Company':25}  {'Role':30}  {'Location'}")
    print(f"{'='*90}")
    
    for job in sorted(jobs, key=lambda x: x.get("score", 0), reverse=True)[:30]:
        score = job.get("score", 0)
        tier = job.get("signal_tier", "")
        company = job.get("company_name", "")[:25]
        role = job.get("role_title", "")[:30]
        location = job.get("location", "")[:20]
        signals = job.get("fractional_signals", "")

        # Color coding for terminal
        if tier == "Hot":
            tier_display = f"\033[91m{tier:6}\033[0m"  # Red
        elif tier == "Warm":
            tier_display = f"\033[93m{tier:6}\033[0m"  # Yellow
        else:
            tier_display = f"{tier:6}"

        print(f"  {score:5d}  {tier_display}  {company:25}  {role:30}  {location}")
        if signals:
            print(f"         {'':6}  → Signals: {signals[:70]}")

    print(f"{'='*90}\n")


def main():
    parser = argparse.ArgumentParser(description="Arteq Job Signal Scraper")
    parser.add_argument("--source", choices=["all", "jsearch", "wellfound"],
                       default="all", help="Which sources to scrape")
    parser.add_argument("--dry-run", action="store_true",
                       help="Print results without writing to sheets")
    parser.add_argument("--max-queries", type=int, default=6,
                       help="Max JSearch API queries per run (default: 6 for free tier)")
    args = parser.parse_args()

    run_pipeline(
        source=args.source,
        dry_run=args.dry_run,
        max_queries=args.max_queries,
    )


if __name__ == "__main__":
    main()
