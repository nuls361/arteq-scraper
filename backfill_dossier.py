#!/usr/bin/env python3
"""
Backfill company_dossier from existing signals.

One-time script: reads all signals from Supabase and creates
corresponding dossier entries. Safe to re-run (skips signals
that already have a dossier entry via signal_id).

Usage: python backfill_dossier.py
Requires: SUPABASE_URL, SUPABASE_KEY
"""

import logging
import os

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_dossier")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def supabase_request(method, table, data=None, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=15)
        else:
            return None
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            logger.error(f"Supabase {method} {table}: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Supabase error: {e}")
        return None


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Get all signals
    signals = supabase_request("GET", "signal", params={
        "select": "id,company_id,title,description,source,source_url,type,relevance_score,urgency,detected_at",
        "order": "detected_at.asc",
        "limit": "5000",
    })
    if not signals:
        logger.info("No signals found")
        return

    logger.info(f"Found {len(signals)} signals to backfill")

    # Get existing dossier signal_ids to avoid duplicates
    existing = supabase_request("GET", "company_dossier", params={
        "select": "signal_id",
        "entry_type": "eq.signal",
        "signal_id": "not.is.null",
        "limit": "10000",
    })
    existing_signal_ids = set()
    if existing:
        existing_signal_ids = {e["signal_id"] for e in existing if e.get("signal_id")}

    logger.info(f"Already in dossier: {len(existing_signal_ids)} signals")

    written = 0
    skipped = 0
    for s in signals:
        if s["id"] in existing_signal_ids:
            skipped += 1
            continue

        content = s.get("description") or s.get("title") or ""
        signal_type = s.get("type", "other")
        score = s.get("relevance_score", 0)
        urgency = s.get("urgency", "medium")
        content += f"\n\n[Signal: {signal_type} | Relevance: {score}/100 | Urgency: {urgency}]"

        record = {
            "company_id": s["company_id"],
            "entry_type": "signal",
            "title": s.get("title", "")[:500] if s.get("title") else None,
            "content": content[:5000],
            "source": s.get("source"),
            "source_url": s.get("source_url"),
            "signal_id": s["id"],
            "created_at": s.get("detected_at"),
        }

        result = supabase_request("POST", "company_dossier", data=record)
        if result:
            written += 1
        else:
            logger.warning(f"Failed to backfill signal {s['id']}")

    logger.info(f"Backfill complete: {written} written, {skipped} already existed")


if __name__ == "__main__":
    main()
