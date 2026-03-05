"""
A-Line Job Signal Scraper — Google Sheets Writer

Writes scored, deduplicated leads to Google Sheets.
Uses gspread library with service account credentials.

Setup:
1. Create Google Cloud project
2. Enable Google Sheets API
3. Create service account → download JSON key
4. Share target spreadsheet with service account email
5. Set GOOGLE_SHEETS_CREDS_JSON env var (JSON string of the key)
6. Set GOOGLE_SHEET_ID env var (spreadsheet ID from URL)
"""

import json
import logging
from datetime import datetime
from config import (
    GOOGLE_SHEETS_CREDS_JSON, GOOGLE_SHEET_ID,
    SHEET_TAB_HOT, SHEET_TAB_WARM, SHEET_TAB_PARKED, SHEET_TAB_LOG,
    SHEET_HEADERS,
)

logger = logging.getLogger(__name__)

# Try to import gspread — graceful fallback to CSV if not available
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not installed. Will output to CSV instead.")


def get_sheets_client():
    """Authenticate and return gspread client."""
    if not GSPREAD_AVAILABLE:
        return None

    if not GOOGLE_SHEETS_CREDS_JSON or not GOOGLE_SHEET_ID:
        logger.warning("Google Sheets credentials not configured. Will output to CSV.")
        return None

    try:
        creds_dict = json.loads(GOOGLE_SHEETS_CREDS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        logger.error(f"Google Sheets auth failed: {e}")
        return None


def get_or_create_worksheet(spreadsheet, tab_name: str):
    """Get existing worksheet or create new one with headers."""
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(SHEET_HEADERS))
        ws.update("A1", [SHEET_HEADERS])
        # Format header row (bold)
        ws.format("A1:S1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.18},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        })
        logger.info(f"Created worksheet: {tab_name}")
    return ws


def get_existing_dedup_keys(spreadsheet) -> set[str]:
    """Read all existing dedup keys from all tabs to prevent duplicates."""
    keys = set()
    for tab_name in [SHEET_TAB_HOT, SHEET_TAB_WARM, SHEET_TAB_PARKED]:
        try:
            ws = spreadsheet.worksheet(tab_name)
            # Dedup Key is column Q (index 17)
            col_values = ws.col_values(17)  # 1-indexed: column Q
            keys.update(v for v in col_values[1:] if v)  # Skip header
        except gspread.WorksheetNotFound:
            continue
    return keys


def job_to_row(job: dict) -> list[str]:
    """Convert job dict to spreadsheet row."""
    return [
        job.get("company_name", ""),
        job.get("role_title", ""),
        job.get("signal_tier", ""),
        job.get("fractional_signals", ""),
        job.get("location", ""),
        job.get("posted_date", ""),
        job.get("source", ""),
        job.get("source_url", ""),
        job.get("company_size", ""),
        job.get("funding_info", ""),
        job.get("decision_maker", ""),
        str(job.get("score", 0)),
        job.get("status", "New"),
        job.get("notes", ""),
        job.get("role_function", ""),
        job.get("role_level", ""),
        job.get("dedup_key", ""),
        job.get("first_seen", ""),
        job.get("last_updated", ""),
    ]


def write_to_sheets(jobs: list[dict], run_stats: dict) -> bool:
    """
    Write scored jobs to Google Sheets, routed by tier.
    Returns True if successful.
    """
    client = get_sheets_client()

    if not client:
        # Fallback to CSV
        return write_to_csv(jobs, run_stats)

    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        # Get existing dedup keys
        existing_keys = get_existing_dedup_keys(spreadsheet)
        logger.info(f"Found {len(existing_keys)} existing leads in sheet")

        # Route jobs to tabs
        hot_jobs = [j for j in jobs if j.get("signal_tier") == "Hot" and j.get("dedup_key") not in existing_keys]
        warm_jobs = [j for j in jobs if j.get("signal_tier") == "Warm" and j.get("dedup_key") not in existing_keys]
        parked_jobs = [j for j in jobs if j.get("signal_tier") == "Parked" and j.get("dedup_key") not in existing_keys]

        # Write to respective tabs
        if hot_jobs:
            ws = get_or_create_worksheet(spreadsheet, SHEET_TAB_HOT)
            rows = [job_to_row(j) for j in hot_jobs]
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(f"Wrote {len(hot_jobs)} Hot leads")

        if warm_jobs:
            ws = get_or_create_worksheet(spreadsheet, SHEET_TAB_WARM)
            rows = [job_to_row(j) for j in warm_jobs]
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(f"Wrote {len(warm_jobs)} Warm leads")

        if parked_jobs:
            ws = get_or_create_worksheet(spreadsheet, SHEET_TAB_PARKED)
            rows = [job_to_row(j) for j in parked_jobs]
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(f"Wrote {len(parked_jobs)} Parked leads")

        # Write run log
        write_run_log(spreadsheet, run_stats, len(hot_jobs), len(warm_jobs), len(parked_jobs))

        skipped = len(jobs) - len(hot_jobs) - len(warm_jobs) - len(parked_jobs)
        logger.info(f"Sheets update complete. {skipped} duplicates skipped.")
        return True

    except Exception as e:
        logger.error(f"Google Sheets write failed: {e}")
        return write_to_csv(jobs, run_stats)


def write_run_log(spreadsheet, stats: dict, hot: int, warm: int, parked: int):
    """Write scraper run log entry."""
    try:
        ws = get_or_create_worksheet(spreadsheet, SHEET_TAB_LOG)

        # Check if headers exist
        first_row = ws.row_values(1)
        if not first_row:
            ws.update("A1", [["Timestamp", "Queries Used", "Raw Jobs Found",
                             "After Scoring", "After Dedup", "Hot", "Warm",
                             "Parked", "Duration (s)", "Errors"]])

        log_row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            str(stats.get("queries_used", 0)),
            str(stats.get("raw_jobs", 0)),
            str(stats.get("scored_jobs", 0)),
            str(stats.get("deduped_jobs", 0)),
            str(hot),
            str(warm),
            str(parked),
            str(stats.get("duration_seconds", 0)),
            stats.get("errors", ""),
        ]
        ws.append_row(log_row, value_input_option="USER_ENTERED")
    except Exception as e:
        logger.error(f"Failed to write run log: {e}")


def write_to_csv(jobs: list[dict], run_stats: dict) -> bool:
    """
    Fallback: Write results to CSV file.
    Used when Google Sheets is not configured.
    """
    import csv
    from pathlib import Path

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = output_dir / f"leads_{timestamp}.csv"

    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(SHEET_HEADERS)
            for job in jobs:
                writer.writerow(job_to_row(job))

        logger.info(f"CSV fallback: wrote {len(jobs)} leads to {filename}")

        # Also write summary
        summary_file = output_dir / f"summary_{timestamp}.txt"
        hot = sum(1 for j in jobs if j.get("signal_tier") == "Hot")
        warm = sum(1 for j in jobs if j.get("signal_tier") == "Warm")
        parked = sum(1 for j in jobs if j.get("signal_tier") == "Parked")

        with open(summary_file, "w") as f:
            f.write(f"A-Line Job Signal Scraper — Run Summary\n")
            f.write(f"{'='*50}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Total leads: {len(jobs)}\n")
            f.write(f"Hot: {hot} | Warm: {warm} | Parked: {parked}\n")
            f.write(f"Queries used: {run_stats.get('queries_used', 'N/A')}\n")
            f.write(f"Duration: {run_stats.get('duration_seconds', 'N/A')}s\n")
            f.write(f"\nTop 10 leads:\n")
            f.write(f"{'-'*50}\n")
            for job in sorted(jobs, key=lambda x: x.get("score", 0), reverse=True)[:10]:
                f.write(f"  [{job.get('score', 0):3d}] {job.get('signal_tier', ''):6s} | "
                       f"{job.get('company_name', ''):25s} | {job.get('role_title', '')}\n")

        return True

    except Exception as e:
        logger.error(f"CSV write failed: {e}")
        return False
