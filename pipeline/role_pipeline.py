#!/usr/bin/env python3
"""
A-Line Role Pipeline — Create opportunities from hot roles.

Scans for hot roles where company is enriched + contacts enriched.
Creates opportunity with pipeline_type='role', linked to role_id + company_id.

SDR targets: HR-Lead, Hiring Manager, CEO
Messaging: "We saw you're hiring [Role] — we have experienced Interim/Fractional [Role] in our network"

Usage: python -m pipeline.role_pipeline
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("role_pipeline")

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
    """Create opportunities from hot roles at enriched companies."""
    logger.info("Role Pipeline — Scanning for new opportunities")

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Get hot roles at companies with enrichment_status='complete'
    hot_roles = supabase_request("GET", "role", params={
        "select": "id,title,company_id,engagement_type,role_function,role_level",
        "is_hot": "eq.true",
        "status": "eq.active",
        "order": "created_at.desc",
        "limit": "50",
    })

    if not hot_roles:
        logger.info("No hot roles found — done")
        return

    created = 0

    for role in hot_roles:
        company_id = role.get("company_id")
        role_id = role.get("id")
        if not company_id or not role_id:
            continue

        # Check company is enriched
        company = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,enrichment_status",
            "limit": "1",
        })
        if not company or company[0].get("enrichment_status") != "complete":
            continue

        # Check if opportunity already exists for this role
        existing = supabase_request("GET", "opportunity", params={
            "role_id": f"eq.{role_id}",
            "select": "id",
            "limit": "1",
        })
        if existing and len(existing) > 0:
            continue

        # Check that company has at least one contact with email
        contacts = supabase_request("GET", "company_contact", params={
            "company_id": f"eq.{company_id}",
            "select": "contact:contact_id(id,email,enrichment_status)",
            "limit": "5",
        })
        has_contact_with_email = any(
            c.get("contact", {}).get("email") for c in (contacts or [])
        )
        if not has_contact_with_email:
            continue

        # Create opportunity
        opp = supabase_request("POST", "opportunity", data={
            "pipeline_type": "role",
            "stage": "ready_for_outreach",
            "company_id": company_id,
            "role_id": role_id,
            "owner": "sdr",
            "notes": f"Hot role: {role['title']} ({role.get('engagement_type', '?')}) — {role.get('role_function', '?')}",
        })

        if opp:
            created += 1
            logger.info(f"  Opportunity created: {company[0]['name']} — {role['title']}")

            # Log to agent_log
            supabase_request("POST", "agent_log", data={
                "action": "opportunity_created",
                "entity_type": "opportunity",
                "entity_id": opp[0]["id"] if isinstance(opp, list) and opp else None,
                "reason": f"Role pipeline: hot role '{role['title']}' at {company[0]['name']}",
                "metadata": json.dumps({"pipeline_type": "role", "role_id": role_id}),
            })

    logger.info(f"Role Pipeline: {created} new opportunities created")


def main():
    create_opportunities()


if __name__ == "__main__":
    main()
