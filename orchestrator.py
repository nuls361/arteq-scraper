#!/usr/bin/env python3
"""
A-Line Orchestrator — Simplified agentic decision-making layer.

Runs after scrapers (role_scraper, signal_scraper) and orchestrates:
  1. Healthcheck
  2. Company enrichment (pending companies)
  3. Contact enrichment (pending contacts)
  4. Role pipeline (create opportunities from hot roles)
  5. Research agent (find candidates for hot roles)
  6. Company pipeline (create opportunities from hot signals)
  7. SDR agent (outreach + reply handling)
  8. AE agent (qualified leads + meetings + proposals)
  9. Daily brief to Niels

Scrapers run as separate GitHub Actions BEFORE orchestrator.

Usage: python orchestrator.py
Schedule: 06:30 UTC (after scrapers at 06:00 and 06:15)
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("orchestrator")

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "niels@arteq.app")

DEFAULT_CONFIG = {
    "apollo_daily_credit_budget": "25",
    "apollo_monthly_credit_budget": "500",
    "role_expire_days": "60",
    "outreach_mode": "draft",
    "outreach_daily_limit": "3",
    "outreach_from_email": "niels@arteq.app",
    "outreach_cc": "niels@arteq.app",
}


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

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
        elif method == "PATCH":
            resp = requests.patch(url, headers=headers, json=data, params=params, timeout=15)
        else:
            return None
        if resp.status_code in (200, 201, 204):
            return resp.json() if resp.text else []
        else:
            logger.error(f"Supabase {method} {table}: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Supabase error: {e}")
        return None


def get_config():
    """Load agent_config from Supabase, with defaults."""
    config = dict(DEFAULT_CONFIG)
    rows = supabase_request("GET", "agent_config", params={"select": "key,value"})
    if rows:
        for r in rows:
            config[r["key"]] = r["value"]
    return config


def log_decision(action, entity_type, entity_id, reason, metadata=None):
    supabase_request("POST", "agent_log", data={
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "reason": reason,
        "metadata": json.dumps(metadata) if metadata else None,
    })


# ═══════════════════════════════════════════════════════════
# DATA HYGIENE — Expire stale roles
# ═══════════════════════════════════════════════════════════

def run_data_hygiene(config):
    """Expire stale roles and clean up."""
    logger.info("\nDATA HYGIENE")

    expire_days = int(config.get("role_expire_days", "60"))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=expire_days)).isoformat()

    # Expire old active roles
    stale_roles = supabase_request("GET", "role", params={
        "select": "id",
        "status": "eq.active",
        "first_seen_at": f"lt.{cutoff}",
        "limit": "200",
    })

    expired = 0
    for role in (stale_roles or []):
        supabase_request("PATCH", f"role?id=eq.{role['id']}", data={"status": "expired"})
        expired += 1

    if expired:
        logger.info(f"  Expired {expired} stale roles (>{expire_days} days)")
    else:
        logger.info(f"  No stale roles to expire")


# ═══════════════════════════════════════════════════════════
# DAILY BRIEF
# ═══════════════════════════════════════════════════════════

def send_daily_brief(results):
    """Send daily summary email to Niels."""
    if not RESEND_API_KEY:
        logger.info("No RESEND_API_KEY — skipping daily brief")
        return

    now = datetime.now(timezone.utc)

    # Gather stats
    hot_roles = supabase_request("GET", "role", params={
        "select": "id",
        "is_hot": "eq.true",
        "status": "eq.active",
    })

    pending_companies = supabase_request("GET", "company", params={
        "select": "id",
        "enrichment_status": "eq.pending",
    })

    active_opps = supabase_request("GET", "opportunity", params={
        "select": "id,pipeline_type,stage",
        "stage": "not.in.(closed_won,closed_lost)",
    })

    candidate_matches = supabase_request("GET", "role_candidate_match", params={
        "select": "id",
        "status": "eq.proposed",
    })

    role_opps = [o for o in (active_opps or []) if o.get("pipeline_type") == "role"]
    company_opps = [o for o in (active_opps or []) if o.get("pipeline_type") == "company"]

    html = f"""<div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;padding:20px">
    <h2 style="color:#1A1A2E;margin:0 0 8px">A-Line Daily Brief</h2>
    <p style="color:#6B6F76;font-size:13px;margin:0 0 20px">{now.strftime('%d.%m.%Y %H:%M')} UTC</p>

    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#F7F7F8">
        <th style="text-align:left;padding:8px">Metric</th>
        <th style="text-align:right;padding:8px">Count</th>
    </tr>
    <tr><td style="padding:8px">Hot Roles (active)</td><td style="text-align:right;padding:8px;font-weight:600">{len(hot_roles or [])}</td></tr>
    <tr><td style="padding:8px">Companies pending enrichment</td><td style="text-align:right;padding:8px;font-weight:600">{len(pending_companies or [])}</td></tr>
    <tr><td style="padding:8px">Candidate matches (proposed)</td><td style="text-align:right;padding:8px;font-weight:600">{len(candidate_matches or [])}</td></tr>
    <tr><td style="padding:8px">Role Pipeline opportunities</td><td style="text-align:right;padding:8px;font-weight:600">{len(role_opps)}</td></tr>
    <tr><td style="padding:8px">Company Pipeline opportunities</td><td style="text-align:right;padding:8px;font-weight:600">{len(company_opps)}</td></tr>
    </table>

    <h3 style="color:#1A1A2E;margin:16px 0 8px">Today's Run</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="background:#F7F7F8">
        <th style="text-align:left;padding:8px">Step</th>
        <th style="text-align:left;padding:8px">Result</th>
    </tr>"""

    for step, result in results.items():
        html += f'<tr><td style="padding:8px">{step}</td><td style="padding:8px">{result}</td></tr>'

    html += """</table>
    <p style="color:#6B6F76;font-size:11px;margin-top:20px">Powered by A-Line Agent</p>
    </div>"""

    try:
        import resend
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": "A-Line Agent <onboarding@resend.dev>",
            "to": [ALERT_EMAIL],
            "subject": f"A-Line Daily Brief — {now.strftime('%d.%m.%Y')}",
            "html": html,
        })
        logger.info(f"  Daily brief sent to {ALERT_EMAIL}")
    except Exception as e:
        logger.error(f"  Daily brief send error: {e}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("A-Line Orchestrator — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    results = {}

    # Load config
    config = get_config()

    # Step 0: Healthcheck
    try:
        from healthcheck import run_healthcheck
        checks, all_ok = run_healthcheck()
        results["Healthcheck"] = "OK" if all_ok else "Issues found"
    except Exception as e:
        logger.error(f"Healthcheck error: {e}")
        results["Healthcheck"] = f"Error: {e}"

    # Step 1: Data hygiene
    try:
        run_data_hygiene(config)
        results["Data Hygiene"] = "Done"
    except Exception as e:
        logger.error(f"Data hygiene error: {e}")
        results["Data Hygiene"] = f"Error: {e}"

    # Step 2: Company enrichment
    try:
        from enrichment.company_enricher import run as run_company_enricher
        run_company_enricher()
        results["Company Enrichment"] = "Done"
    except Exception as e:
        logger.error(f"Company enrichment error: {e}")
        results["Company Enrichment"] = f"Error: {e}"

    # Step 2.5: Role enrichment (decision maker + sourcing brief)
    try:
        from enrichment.role_enricher import run as run_role_enricher
        run_role_enricher()
        results["Role Enrichment"] = "Done"
    except Exception as e:
        logger.error(f"Role enrichment error: {e}")
        results["Role Enrichment"] = f"Error: {e}"

    # Step 3: Contact enrichment
    try:
        from enrichment.contact_enricher import run as run_contact_enricher
        run_contact_enricher()
        results["Contact Enrichment"] = "Done"
    except Exception as e:
        logger.error(f"Contact enrichment error: {e}")
        results["Contact Enrichment"] = f"Error: {e}"

    # Step 4: Role pipeline
    try:
        from pipeline.role_pipeline import create_opportunities as role_create
        role_create()
        results["Role Pipeline"] = "Done"
    except Exception as e:
        logger.error(f"Role pipeline error: {e}")
        results["Role Pipeline"] = f"Error: {e}"

    # Step 5: Research agent (find candidates for hot roles)
    try:
        from pipeline.research_agent import run as run_research
        research_results = run_research()
        results["Research Agent"] = f"{research_results.get('roles_researched', 0)} roles, {research_results.get('matches_found', 0)} matches"
    except Exception as e:
        logger.error(f"Research agent error: {e}")
        results["Research Agent"] = f"Error: {e}"

    # Step 6: Company pipeline
    try:
        from pipeline.company_pipeline import create_opportunities as company_create
        company_create()
        results["Company Pipeline"] = "Done"
    except Exception as e:
        logger.error(f"Company pipeline error: {e}")
        results["Company Pipeline"] = f"Error: {e}"

    # Step 7: SDR agent
    try:
        from pipeline.sdr_agent import run as run_sdr
        sdr_results = run_sdr(config)
        results["SDR Agent"] = f"{sdr_results.get('emails_sent', 0)} sent, {sdr_results.get('drafts_created', 0)} drafts, {sdr_results.get('handoffs', 0)} handoffs"
    except Exception as e:
        logger.error(f"SDR agent error: {e}")
        results["SDR Agent"] = f"Error: {e}"

    # Step 8: AE agent
    try:
        from pipeline.ae_agent import run as run_ae
        ae_results = run_ae(config)
        results["AE Agent"] = f"{ae_results.get('responses_sent', 0)} responses, {ae_results.get('briefings_created', 0)} briefings, {ae_results.get('proposals_created', 0)} proposals"
    except Exception as e:
        logger.error(f"AE agent error: {e}")
        results["AE Agent"] = f"Error: {e}"

    # ── Agency Pipeline (supply-side) ──────────────────────

    # Step 9: Agency finder (weekly — Monday only)
    if datetime.now(timezone.utc).weekday() == 0:
        try:
            from agency_pipeline.agency_finder import run as run_agency_finder
            added = run_agency_finder()
            results["Agency Finder"] = f"{added} new agencies"
        except Exception as e:
            logger.error(f"Agency finder error: {e}")
            results["Agency Finder"] = f"Error: {e}"
    else:
        results["Agency Finder"] = "Skipped (Monday only)"

    # Step 10: Agency enrichment (daily)
    try:
        from agency_pipeline.agency_enricher import run as run_agency_enricher
        run_agency_enricher()
        results["Agency Enrichment"] = "Done"
    except Exception as e:
        logger.error(f"Agency enrichment error: {e}")
        results["Agency Enrichment"] = f"Error: {e}"

    # Step 11: Agency GF finder (daily)
    try:
        from agency_pipeline.agency_gf_finder import run as run_gf_finder
        run_gf_finder()
        results["Agency GF Finder"] = "Done"
    except Exception as e:
        logger.error(f"Agency GF finder error: {e}")
        results["Agency GF Finder"] = f"Error: {e}"

    # Step 12: Agency outreach (daily)
    try:
        from agency_pipeline.agency_sdr_agent import run as run_agency_sdr
        run_agency_sdr()
        results["Agency Outreach"] = "Done"
    except Exception as e:
        logger.error(f"Agency outreach error: {e}")
        results["Agency Outreach"] = f"Error: {e}"

    # Step 13: Daily brief
    try:
        send_daily_brief(results)
    except Exception as e:
        logger.error(f"Daily brief error: {e}")

    # Log orchestrator run
    log_decision("orchestrator_run", "system", None,
                 f"Orchestrator completed: {json.dumps(results)}",
                 results)

    logger.info("=" * 60)
    logger.info("ORCHESTRATOR SUMMARY")
    for step, result in results.items():
        logger.info(f"  {step}: {result}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
