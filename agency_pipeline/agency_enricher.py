#!/usr/bin/env python3
"""
A-Line Agency Enricher — Deep enrichment for pending agencies.

Uses Claude API with web search to enrich agency profiles:
  - Headcount, founding year, specialization
  - Geographic focus, description
  - Competitor detection

Usage: python -m agency_pipeline.agency_enricher
"""

import json
import logging
import os
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agency_enricher")

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


def claude_request(prompt, max_tokens=1500, system=None):
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
# ENRICHMENT
# ═══════════════════════════════════════════════════════════

def enrich_agency(agency):
    """Enrich a single agency using Claude web search.

    Args:
        agency: dict from agency table with id, name, domain.

    Returns:
        True if enrichment succeeded.
    """
    agency_id = agency["id"]
    name = agency.get("name", "Unknown")
    domain = agency.get("domain", "")

    logger.info(f"\nEnriching agency: {name} ({domain})")

    prompt = f"""You are a company research agent. Research this interim management agency and return structured JSON.

Agency: {name}
Domain: {domain}

Search for their website, LinkedIn page, and any press mentions.

Return ONLY valid JSON:
{{
  "headcount": "1-5 | 5-10 | 10-25 | 25+",
  "founded_year": null,
  "specialization": ["Finance", "Operations"],
  "geographic_focus": "national | regional | local",
  "description": "2-3 sentence summary of what they do and for whom",
  "is_direct_competitor": false,
  "is_direct_competitor_reason": "reason why or why not",
  "quality_score": 7,
  "quality_reason": "reason for score"
}}

Scoring guide for quality_score (1-10):
- 8-10: Established firm, multiple interim managers in pool, clear specialization, DDIM member
- 5-7: Smaller boutique, focused niche, decent web presence
- 1-4: Very small, unclear offering, or not actually an interim management firm

is_direct_competitor = true ONLY if they actively place roles themselves AND have their own deal-flow / scraper / tech stack. Small boutiques without tech infrastructure = false (they are pool partners, not competitors).

Rules:
- If information is unknown, use null — never guess.
- specialization should use standard categories: Finance, Operations, HR/People, Engineering/Tech, Sales, Marketing, Product, General Management, C-Suite, Board
- Return ONLY valid JSON, no explanation."""

    text = claude_request(prompt, max_tokens=800, system="You are a company research agent. Return only valid JSON.")
    if not text:
        supabase_request("PATCH", f"agency?id=eq.{agency_id}", data={
            "enrichment_status": "failed",
        })
        return False

    try:
        result = json.loads(clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"  JSON parse error: {e}")
        supabase_request("PATCH", f"agency?id=eq.{agency_id}", data={
            "enrichment_status": "failed",
        })
        return False

    # Update agency record
    update = {
        "enrichment_status": "enriched",
    }
    if result.get("headcount"):
        update["headcount"] = result["headcount"]
    if result.get("founded_year"):
        update["founded_year"] = result["founded_year"]
    if result.get("specialization"):
        update["specialization"] = result["specialization"]
    if result.get("geographic_focus"):
        update["geographic_focus"] = result["geographic_focus"]
    if result.get("description"):
        update["description"] = result["description"]
    if result.get("is_direct_competitor") is not None:
        update["is_direct_competitor"] = bool(result["is_direct_competitor"])
    if result.get("is_direct_competitor_reason"):
        update["is_direct_competitor_reason"] = result["is_direct_competitor_reason"]
    if result.get("quality_score"):
        update["quality_score"] = result["quality_score"]
    if result.get("quality_reason"):
        update["quality_reason"] = result["quality_reason"]

    supabase_request("PATCH", f"agency?id=eq.{agency_id}", data=update)

    is_comp = result.get("is_direct_competitor", False)
    logger.info(f"  Enriched: headcount={result.get('headcount')}, quality={result.get('quality_score')}, competitor={is_comp}")

    return True


def run_enrichment_batch(limit=20):
    """Enrich pending agencies in batch.

    Args:
        limit: Max agencies to enrich per run.
    """
    logger.info("=" * 60)
    logger.info("A-Line Agency Enricher — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    agencies = supabase_request("GET", "agency", params={
        "select": "id,name,domain",
        "enrichment_status": "eq.pending",
        "order": "created_at.desc",
        "limit": str(limit),
    })

    if not agencies:
        logger.info("No pending agencies to enrich — done")
        return

    logger.info(f"Found {len(agencies)} agencies to enrich")

    enriched = 0
    for agency in agencies:
        try:
            if enrich_agency(agency):
                enriched += 1
        except Exception as e:
            logger.error(f"Error enriching {agency.get('name', '?')}: {e}")

        time.sleep(1)

    logger.info("=" * 60)
    logger.info(f"AGENCY ENRICHER SUMMARY: {enriched}/{len(agencies)} enriched")
    logger.info("=" * 60)


def run():
    """Main entry point."""
    run_enrichment_batch()


if __name__ == "__main__":
    run()
