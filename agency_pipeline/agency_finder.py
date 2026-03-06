#!/usr/bin/env python3
"""
A-Line Agency Finder — Discover interim management agencies in DACH.

Sources:
  1. Google/Claude web search for interim management agencies
  2. DDIM member directory (Dachgesellschaft Deutsches Interim Management)

Usage: python -m agency_pipeline.agency_finder
"""

import json
import logging
import os
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agency_finder")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def supabase_request(method, table, data=None, params=None, upsert=False):
    """Make a request to Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if upsert:
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
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


def claude_request(prompt, max_tokens=2000, system=None):
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
            timeout=90,
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
    if t and t[0] not in ('{', '['):
        idx_obj = t.find('{')
        idx_arr = t.find('[')
        if idx_obj >= 0 and (idx_arr < 0 or idx_obj < idx_arr):
            t = t[idx_obj:]
        elif idx_arr >= 0:
            t = t[idx_arr:]
    if t and t[0] in ('{', '['):
        open_ch = t[0]
        close_ch = '}' if open_ch == '{' else ']'
        depth = 0
        for i, c in enumerate(t):
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
            if depth == 0:
                t = t[:i + 1]
                break
    return t


# ═══════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════

SEARCH_QUERIES = [
    "Interim Management Agentur Deutschland",
    "Interim Management Beratung DACH",
    "Interim Manager Vermittlung Deutschland",
    "Interim Management Agentur Österreich",
    "Interim Management Agentur Schweiz",
    "DDIM Mitglied Interim Management",
    "Fractional Executive Vermittlung DACH",
    "Interim Management Boutique Deutschland",
    "Interim CFO Vermittlung Deutschland",
    "Interim CTO Vermittlung DACH",
]


def find_agencies_via_google(max_results=50):
    """Search for DACH interim management agencies using Claude web search.

    Uses Claude API to run web searches and extract structured results.

    Returns:
        List of dicts: [{name, domain, hq_city, hq_country, source}]
    """
    logger.info("Searching for interim management agencies via web search...")
    all_agencies = []

    for query in SEARCH_QUERIES:
        prompt = f"""Search the web for: "{query}"

Find interim management agencies, boutiques, and placement firms.
For each result, extract the agency information.

Return a JSON array of agencies found:
[
  {{
    "name": "Agency Name GmbH",
    "domain": "agency-domain.de",
    "hq_city": "city name or null",
    "hq_country": "Germany | Austria | Switzerland",
    "snippet": "brief description from search result"
  }}
]

Rules:
- Only include actual interim management agencies, NOT job boards or news articles.
- Skip staffing giants (Hays, Robert Half, Randstad, Adecco, ManpowerGroup).
- Skip big consulting firms (McKinsey, BCG, Bain, Deloitte, PwC, KPMG, EY).
- Include boutique firms, specialized interim management providers, and DDIM members.
- domain should be clean (e.g. "firma.de", not "https://www.firma.de/page").
- Return ONLY valid JSON array."""

        text = claude_request(prompt, max_tokens=2000, system="You are a web research agent. Return only valid JSON.")
        if not text:
            continue

        try:
            agencies = json.loads(clean_json_response(text))
            if isinstance(agencies, list):
                for a in agencies:
                    a["source"] = "google"
                all_agencies.extend(agencies)
                logger.info(f"  Query '{query}': {len(agencies)} agencies found")
        except json.JSONDecodeError as e:
            logger.error(f"  JSON parse error for query '{query}': {e}")

        time.sleep(1)

        if len(all_agencies) >= max_results:
            break

    logger.info(f"Total agencies found via web search: {len(all_agencies)}")
    return all_agencies[:max_results]


def find_agencies_via_ddim():
    """Scrape DDIM member directory for interim management agencies.

    DDIM = Dachgesellschaft Deutsches Interim Management.
    This is the main German industry association — high quality leads.

    Returns:
        List of dicts: [{name, domain, hq_city, source}]
    """
    logger.info("Searching DDIM member directory...")

    prompt = """Search the web for the DDIM (Dachgesellschaft Deutsches Interim Management) member directory.
URL: https://www.ddim.de/interim-manager/ or https://www.ddim.de/mitglieder/

Find interim management firms that are DDIM members. These are the most established
interim management providers in Germany.

Return a JSON array of member firms found:
[
  {
    "name": "Agency Name",
    "domain": "agency-domain.de",
    "hq_city": "city or null",
    "hq_country": "Germany",
    "specialization": ["Finance", "Operations"]
  }
]

Rules:
- Only include firms that provide interim management services.
- Skip individual interim managers — we want the firms/agencies.
- domain should be clean (e.g. "firma.de").
- Return ONLY valid JSON array. If you can't access the directory, return []."""

    text = claude_request(prompt, max_tokens=2000, system="You are a web research agent. Return only valid JSON.")
    if not text:
        return []

    try:
        agencies = json.loads(clean_json_response(text))
        if isinstance(agencies, list):
            for a in agencies:
                a["source"] = "ddim"
            logger.info(f"DDIM members found: {len(agencies)}")
            return agencies
    except json.JSONDecodeError as e:
        logger.error(f"DDIM JSON parse error: {e}")

    return []


# ═══════════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════════

def deduplicate_and_store(agencies):
    """Upsert agencies into Supabase agency table.

    Deduplicates on domain.

    Args:
        agencies: List of dicts with name, domain, hq_city, etc.

    Returns:
        Count of new agencies added.
    """
    if not agencies:
        return 0

    added = 0
    for agency in agencies:
        domain = (agency.get("domain") or "").strip().lower()
        if not domain:
            continue

        # Clean domain
        domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if not domain:
            continue

        # Check if already exists
        existing = supabase_request("GET", "agency", params={
            "domain": f"eq.{domain}",
            "select": "id",
            "limit": "1",
        })

        if existing:
            continue

        # Insert new agency
        data = {
            "name": agency.get("name", domain),
            "domain": domain,
            "hq_city": agency.get("hq_city"),
            "hq_country": agency.get("hq_country", "Germany"),
            "source": agency.get("source", "google"),
            "enrichment_status": "pending",
            "outreach_status": "pending",
        }

        # Store specialization if available
        if agency.get("specialization"):
            data["specialization"] = agency["specialization"]

        result = supabase_request("POST", "agency", data=data)
        if result:
            added += 1
            logger.info(f"  Added agency: {data['name']} ({domain})")

    logger.info(f"Stored {added} new agencies (from {len(agencies)} found)")
    return added


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run():
    """Run the agency finder: search + store."""
    logger.info("=" * 60)
    logger.info("A-Line Agency Finder — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return 0

    all_agencies = []

    # Google/Claude web search
    google_results = find_agencies_via_google(max_results=50)
    all_agencies.extend(google_results)

    # DDIM member directory
    ddim_results = find_agencies_via_ddim()
    all_agencies.extend(ddim_results)

    # Deduplicate and store
    added = deduplicate_and_store(all_agencies)

    logger.info("=" * 60)
    logger.info(f"AGENCY FINDER SUMMARY: {added} new agencies added")
    logger.info("=" * 60)

    return added


if __name__ == "__main__":
    run()
