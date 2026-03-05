#!/usr/bin/env python3
"""
A-Line Company Pipeline — Create opportunities from hot signals.

Scans for hot signals where company is enriched + contacts enriched.
Creates opportunity with pipeline_type='company', linked to signal_id + company_id.

SDR targets: CEO, COO, HR-Lead
Messaging: "We read about [Signal] — typically you need [Interim Role]. We can help."

Usage: python -m pipeline.company_pipeline
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("company_pipeline")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def supabase_request(method, table, data=None, params=None):
    """Make a request to Supabase REST API."""
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
        elif method == "PATCH":
            resp = requests.patch(url, headers=headers, json=data, params=params, timeout=15)
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


def create_opportunities():
    """Create opportunities from hot signals at enriched companies."""
    logger.info("Company Pipeline — Scanning for new opportunities")

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Get hot signals
    hot_signals = supabase_request("GET", "signal", params={
        "select": "id,company_id,type,title,interim_relevance",
        "is_hot": "eq.true",
        "processed": "eq.false",
        "order": "detected_at.desc",
        "limit": "50",
    })

    if not hot_signals:
        logger.info("No hot signals found — done")
        return

    created = 0

    for signal in hot_signals:
        company_id = signal.get("company_id")
        signal_id = signal.get("id")
        if not company_id or not signal_id:
            continue

        # Check company is enriched
        company = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,enrichment_status",
            "limit": "1",
        })
        if not company or company[0].get("enrichment_status") != "complete":
            continue

        # Check if opportunity already exists for this signal
        existing = supabase_request("GET", "opportunity", params={
            "signal_id": f"eq.{signal_id}",
            "select": "id",
            "limit": "1",
        })
        if existing and len(existing) > 0:
            # Mark signal as processed
            supabase_request("PATCH", f"signal?id=eq.{signal_id}", data={"processed": True})
            continue

        # Also check if company already has an active opportunity (avoid duplicates)
        existing_company_opp = supabase_request("GET", "opportunity", params={
            "company_id": f"eq.{company_id}",
            "pipeline_type": "eq.company",
            "stage": "in.(new,ready_for_outreach,sdr_contacted)",
            "select": "id",
            "limit": "1",
        })
        if existing_company_opp and len(existing_company_opp) > 0:
            supabase_request("PATCH", f"signal?id=eq.{signal_id}", data={"processed": True})
            continue

        # Check that company has at least one contact with email
        contacts = supabase_request("GET", "company_contact", params={
            "company_id": f"eq.{company_id}",
            "select": "contact:contact_id(id,email)",
            "limit": "5",
        })
        has_contact_with_email = any(
            c.get("contact", {}).get("email") for c in (contacts or [])
        )
        if not has_contact_with_email:
            continue

        # Create opportunity
        signal_type = signal.get("type", "other")
        signal_title = signal.get("title", "")[:100]

        opp = supabase_request("POST", "opportunity", data={
            "pipeline_type": "company",
            "stage": "ready_for_outreach",
            "company_id": company_id,
            "signal_id": signal_id,
            "owner": "sdr",
            "notes": f"Signal: [{signal_type}] {signal_title}",
        })

        if opp:
            created += 1
            logger.info(f"  Opportunity created: {company[0]['name']} — [{signal_type}] {signal_title}")

            # Mark signal as processed
            supabase_request("PATCH", f"signal?id=eq.{signal_id}", data={"processed": True})

            # Log to agent_log
            supabase_request("POST", "agent_log", data={
                "action": "opportunity_created",
                "entity_type": "opportunity",
                "entity_id": opp[0]["id"] if isinstance(opp, list) and opp else None,
                "reason": f"Company pipeline: hot signal [{signal_type}] at {company[0]['name']}",
                "metadata": json.dumps({"pipeline_type": "company", "signal_id": signal_id}),
            })

    logger.info(f"Company Pipeline: {created} new opportunities created")


def main():
    create_opportunities()


if __name__ == "__main__":
    main()
