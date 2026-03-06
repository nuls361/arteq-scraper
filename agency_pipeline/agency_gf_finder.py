#!/usr/bin/env python3
"""
A-Line Agency GF Finder — Find Geschäftsführer/Inhaber of agencies.

Uses Claude API with web search to find the GF/Inhaber:
  1. Impressum (ground truth for German GmbHs)
  2. LinkedIn search
  3. Team/About page

Usage: python -m agency_pipeline.agency_gf_finder
"""

import json
import logging
import os
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agency_gf_finder")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

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


def claude_request(prompt, max_tokens=800, system=None):
    """Make a request to Claude API."""
    if not ANTHROPIC_KEY:
        return None
    try:
        body = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error(f"Claude API {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        return "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return None


def clean_json_response(text):
    """Strip markdown fences and extract JSON."""
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1]
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1]
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    t = t.strip()
    if t and t[0] != '{':
        idx = t.find('{')
        if idx >= 0:
            t = t[idx:]
    if t and t[0] == '{':
        depth = 0
        for i, c in enumerate(t):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            if depth == 0:
                t = t[:i + 1]
                break
    return t


# ═══════════════════════════════════════════════════════════
# GF FINDER
# ═══════════════════════════════════════════════════════════

def find_agency_gf(agency):
    """Find the Geschäftsführer/Inhaber of an agency.

    Uses Claude with web search to find the person.

    Args:
        agency: dict from agency table with id, name, domain.

    Returns:
        dict with GF info or None.
    """
    agency_id = agency["id"]
    name = agency.get("name", "Unknown")
    domain = agency.get("domain", "")

    logger.info(f"\nFinding GF for: {name} ({domain})")

    prompt = f"""Find the Geschäftsführer (CEO/Managing Director) or Inhaber (Owner) of this company.

Company: {name}
Domain: {domain}

Search in this order:
1. "{name} Impressum" → always lists GF for German GmbHs
2. "{name} Geschäftsführer LinkedIn"
3. "{name} Inhaber LinkedIn"
4. "{name} team" or "{name} über uns"

Return ONLY a JSON object:
{{
  "name": "full name or null",
  "title": "Geschäftsführer | Inhaber | Managing Partner | Managing Director",
  "linkedin_url": "LinkedIn URL or null",
  "email": "guessed email from domain pattern (e.g. vorname@domain.de) or null",
  "confidence": "high | medium | low",
  "source": "impressum | linkedin | website | inferred"
}}

Rules:
- Never guess a name. null + low confidence is better than a wrong name.
- German Impressum = ground truth for GF identity.
- confidence = 'high' only if confirmed via Impressum or LinkedIn profile.
- For email: if the domain pattern is known (e.g. firstname@domain.de), provide a guess. Otherwise null.
- Return ONLY valid JSON, no explanation."""

    text = claude_request(prompt, max_tokens=500, system="You are a contact research agent. Return only valid JSON.")
    if not text:
        return None

    try:
        result = json.loads(clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"  JSON parse error: {e}")
        return None

    if not result.get("name"):
        logger.info(f"  No GF found for {name}")
        return None

    # Store in agency_contact table
    contact_data = {
        "agency_id": agency_id,
        "name": result["name"],
        "title": result.get("title", "Geschäftsführer"),
        "linkedin_url": result.get("linkedin_url"),
        "email": result.get("email"),
        "confidence": result.get("confidence", "medium"),
        "source": result.get("source", "inferred"),
        "is_primary": True,
    }

    supabase_request("POST", "agency_contact", data=contact_data)

    logger.info(f"  Found: {result['name']} ({result.get('title', '?')}) [{result.get('confidence', '?')}]")
    return result


def run_gf_finder_batch(limit=20):
    """Find GFs for enriched agencies that don't have contacts yet.

    Args:
        limit: Max agencies to process per run.
    """
    logger.info("=" * 60)
    logger.info("A-Line Agency GF Finder — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Get enriched, non-competitor agencies
    agencies = supabase_request("GET", "agency", params={
        "select": "id,name,domain",
        "enrichment_status": "eq.enriched",
        "is_direct_competitor": "eq.false",
        "order": "created_at.desc",
        "limit": str(limit),
    })

    if not agencies:
        logger.info("No agencies needing GF lookup — done")
        return

    # Filter to those without contacts
    to_process = []
    for agency in agencies:
        existing_contacts = supabase_request("GET", "agency_contact", params={
            "agency_id": f"eq.{agency['id']}",
            "select": "id",
            "limit": "1",
        })
        if not existing_contacts:
            to_process.append(agency)

    if not to_process:
        logger.info("All enriched agencies already have contacts — done")
        return

    logger.info(f"Found {len(to_process)} agencies needing GF lookup")

    found = 0
    for agency in to_process:
        try:
            result = find_agency_gf(agency)
            if result:
                found += 1
        except Exception as e:
            logger.error(f"Error finding GF for {agency.get('name', '?')}: {e}")

        time.sleep(1)

    logger.info("=" * 60)
    logger.info(f"AGENCY GF FINDER SUMMARY: {found}/{len(to_process)} GFs found")
    logger.info("=" * 60)


def run():
    """Main entry point."""
    run_gf_finder_batch()


if __name__ == "__main__":
    run()
