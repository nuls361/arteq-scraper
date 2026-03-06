#!/usr/bin/env python3
"""
A-Line Single Company Enrichment — Triggered via GitHub Actions dispatch.

Reuses orchestrator functions to evaluate a single company:
  1. Fetch company record
  2. Gather intel (roles, signals, contacts)
  3. Claude scoring + recommendation
  4. Update company composite_score, status, last_orchestrator_eval
  5. Write to company_dossier + agent_log

Usage: python enrich_single.py --company-id <uuid>
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_single")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


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
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, params=params, timeout=15)
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


def clean_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def load_agent_soul():
    soul_path = os.path.join(os.path.dirname(__file__), "agent_soul.md")
    try:
        with open(soul_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


AGENT_SOUL = load_agent_soul()


def claude_request(prompt, max_tokens=1500, system=None):
    if not ANTHROPIC_KEY:
        return None
    try:
        body = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        sys_prompt = system if system is not None else AGENT_SOUL
        if sys_prompt:
            body["system"] = sys_prompt

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


def gather_company_intel(company_id):
    roles = supabase_request("GET", "role", params={
        "company_id": f"eq.{company_id}",
        "select": "title,tier,final_score,engagement_type,status,first_seen_at",
        "order": "final_score.desc", "limit": "10",
    })
    signals = supabase_request("GET", "signal", params={
        "company_id": f"eq.{company_id}",
        "select": "type,title,relevance_score,urgency,detected_at",
        "order": "detected_at.desc", "limit": "15",
    })
    contacts = supabase_request("GET", "company_contact", params={
        "company_id": f"eq.{company_id}",
        "select": "is_decision_maker,role_at_company,contact:contact_id(name,title,email,linkedin_url,phone)",
    })
    return {
        "roles": roles or [],
        "signals": signals or [],
        "contacts": [c for c in (contacts or []) if c.get("contact")],
    }


def enrich_company(company_id):
    logger.info(f"Enriching company {company_id}")

    # Fetch company
    result = supabase_request("GET", "company", params={
        "id": f"eq.{company_id}",
        "select": "id,name,status,domain,industry,funding_stage,headcount,signal_density,arteq_fit,is_agency,composite_score",
        "limit": "1",
    })
    if not result or len(result) == 0:
        logger.error(f"Company {company_id} not found")
        return False

    co = result[0]
    logger.info(f"Company: {co['name']} (status={co.get('status')}, score={co.get('composite_score')})")

    # Gather intel
    intel = gather_company_intel(company_id)
    logger.info(f"Intel: {len(intel['roles'])} roles, {len(intel['signals'])} signals, {len(intel['contacts'])} contacts")

    company_name = co["name"]
    domain = (co.get("domain") or "").replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] or None

    # ── Step 1: Claude Company Research ──
    logger.info("Step 1: Claude company research...")
    research_prompt = f"""You are a company research agent. Given a company name, search the web and return structured data for the following fields. Use sources like Crunchbase, PitchBook, LinkedIn, Tracxn, ZoomInfo, and the company's own website.

Company: {company_name}

Return ONLY a JSON object with these exact fields:

{{
  "domain": "primary website domain (e.g. buchhaltungsbutler.de)",
  "industry": "industry or sector (e.g. Financial Software / SaaS)",
  "hq": "full HQ address or city + country",
  "founded": "founding year (integer)",
  "headcount": "employee count or range (e.g. '11-50' or 23)",
  "description": "2-3 sentence business description: what they do, for whom, key differentiator",
  "funding_stage": "last known funding stage (e.g. Seed, Series A, Acquired, Bootstrapped)",
  "funding_total": "total funding raised in USD (null if unknown)",
  "investors": ["list", "of", "known", "investors"],
  "revenue": "annual revenue if known (null if unknown)",
  "acquisition": {{
    "acquired": false,
    "acquirer": null,
    "date": null
  }},
  "founders": ["Founder Name 1", "Founder Name 2"],
  "status": "active | acquired | defunct"
}}

Rules:
- If a field is unknown, use null — never guess or hallucinate.
- For headcount, prefer the most recent data point and note the source year if uncertain.
- Return only valid JSON, no explanation, no markdown."""

    research_data = {}
    research_text = claude_request(research_prompt, max_tokens=1000, system="You are a company research agent. Return only valid JSON.")
    if research_text:
        try:
            research_data = json.loads(clean_json_response(research_text))
            logger.info(f"  Research: domain={research_data.get('domain')}, industry={research_data.get('industry')}, headcount={research_data.get('headcount')}")
        except json.JSONDecodeError as e:
            logger.error(f"Research JSON parse error: {e}")

    # Map research fields to company update
    update_data = {
        "last_orchestrator_eval": datetime.now(timezone.utc).isoformat(),
    }
    if research_data.get("domain"):
        update_data["domain"] = research_data["domain"]
        domain = research_data["domain"]
    if research_data.get("industry"):
        update_data["industry"] = research_data["industry"]
    if research_data.get("hq"):
        update_data["hq_city"] = research_data["hq"]
    if research_data.get("founded"):
        update_data["founded_year"] = research_data["founded"]
    if research_data.get("headcount"):
        update_data["headcount"] = str(research_data["headcount"])
    if research_data.get("description"):
        update_data["description"] = research_data["description"]
    if research_data.get("funding_stage"):
        update_data["funding_stage"] = research_data["funding_stage"]
    if research_data.get("funding_total"):
        update_data["funding_amount"] = f"${research_data['funding_total']:,.0f}" if isinstance(research_data["funding_total"], (int, float)) else str(research_data["funding_total"])
    if research_data.get("investors"):
        update_data["investors"] = ", ".join(research_data["investors"]) if isinstance(research_data["investors"], list) else str(research_data["investors"])
    if research_data.get("revenue"):
        update_data["revenue"] = str(research_data["revenue"])
    if research_data.get("founders"):
        update_data["founders"] = ", ".join(research_data["founders"]) if isinstance(research_data["founders"], list) else str(research_data["founders"])

    # ── Step 2: Claude Assessment + Dossier ──
    logger.info("Step 2: Claude assessment...")
    batch_text = f"--- Company: {company_name} (ID: {co['id']}) ---\n"
    batch_text += f"Domain: {domain or '?'} | Industry: {update_data.get('industry', co.get('industry', '?'))} | Funding: {update_data.get('funding_stage', co.get('funding_stage', '?'))} | Headcount: {update_data.get('headcount', co.get('headcount', '?'))}\n"
    if research_data.get("description"):
        batch_text += f"Description: {research_data['description']}\n"

    if intel["roles"]:
        batch_text += f"Roles ({len(intel['roles'])}): " + ", ".join(
            f"{r['title']} [{r.get('tier', '?')}/{r.get('engagement_type', '?')}]" for r in intel["roles"][:5]
        ) + "\n"

    if intel["signals"]:
        batch_text += f"Signals ({len(intel['signals'])}): " + ", ".join(
            f"{s.get('type', '?')}: {s.get('title', '')[:50]} [{s.get('urgency', '?')}]" for s in intel["signals"][:5]
        ) + "\n"

    if intel["contacts"]:
        batch_text += f"Contacts ({len(intel['contacts'])}): " + ", ".join(
            f"{c['contact']['name']} ({c['contact'].get('title', '?')}) {'mail' if c['contact'].get('email') else ''}" for c in intel["contacts"][:3]
        ) + "\n"

    prompt = f"""You are the AI agent for A-Line, a DACH-focused Fractional/Interim Executive placement firm.

Assess this company holistically:
1. composite_score (0-100): How promising is this company as a client?
2. recommended_status: lead | prospect | active
3. outreach_priority: 1 (highest) to 10 (lowest)
4. dossier_html: Rich HTML dossier with company overview, role analysis, why A-Line fits, and next steps

Criteria:
- Active HOT/WARM Roles for Fractional/Interim positions → strong signal
- Funding round + growth → likely need leadership soon
- Leadership changes → open position = opportunity
- Decision maker with email available → outreach-ready
- Agency/consultancy → DISQUALIFIED (score 0)

{batch_text}

Respond ONLY in valid JSON:
{{"composite_score": 82, "recommended_status": "active", "outreach_priority": 1, "arteq_fit": "high|medium|low", "reasoning": "2-3 sentences", "dossier_html": "<h3>Company Dossier: [Name]</h3><p>...</p><h4>Why A-Line?</h4><ul><li>...</li></ul><h4>Next Steps</h4><ul><li>...</li></ul>"}}

IMPORTANT: Write ALL content in English."""

    text = claude_request(prompt, max_tokens=1500)
    if not text:
        logger.error("Claude returned no response")
        # Still save research data even if assessment fails
        supabase_request("PATCH", f"company?id=eq.{company_id}", data=update_data)
        return False

    try:
        ev = json.loads(clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        supabase_request("PATCH", f"company?id=eq.{company_id}", data=update_data)
        return False

    score = ev.get("composite_score", 0)
    new_status = ev.get("recommended_status", co.get("status", "lead"))
    old_status = co.get("status", "lead")
    priority = ev.get("outreach_priority")
    reasoning = ev.get("reasoning", "")

    logger.info(f"Claude evaluation: score={score}, status={new_status}, priority={priority}")
    logger.info(f"Reasoning: {reasoning}")

    # Add assessment fields to update
    update_data["composite_score"] = score
    update_data["outreach_priority"] = priority
    if ev.get("arteq_fit"):
        update_data["arteq_fit"] = ev["arteq_fit"]

    # Status promotion logic
    if new_status != old_status:
        if (old_status == "lead" and new_status in ("prospect", "active")) or \
           (old_status == "prospect" and new_status == "active"):
            update_data["status"] = new_status
            logger.info(f"Promoting: {old_status} -> {new_status}")
        elif old_status == "prospect" and new_status == "lead":
            update_data["status"] = new_status
            logger.info(f"Downgrading: {old_status} -> {new_status}")

    update_data["enrichment_status"] = "complete"
    supabase_request("PATCH", f"company?id=eq.{company_id}", data=update_data)

    # Write dossier entry (delete old first)
    supabase_request("DELETE", "company_dossier",
        params={"company_id": f"eq.{company_id}", "source": "eq.enrich_single"})

    dossier_html = ev.get("dossier_html", f"<p>Score: {score}/100 | Priority: {priority}/10</p><p>{reasoning}</p>")

    supabase_request("POST", "company_dossier", data={
        "company_id": company_id,
        "entry_type": "agent_action",
        "title": f"Manual Enrichment — Score: {score}/100",
        "content": dossier_html,
        "source": "enrich_single",
        "author": "A-Line Agent",
    })

    # Log to agent_log
    supabase_request("POST", "agent_log", data={
        "action": "enrich_single",
        "entity_type": "company",
        "entity_id": str(company_id),
        "reason": f"Manual enrichment: score={score}, status={new_status}, priority={priority}. {reasoning}",
    })

    logger.info(f"Enrichment complete for {co['name']}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Enrich a single company")
    parser.add_argument("--company-id", required=True, help="Supabase company UUID")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        sys.exit(1)

    if not ANTHROPIC_KEY:
        logger.error("Missing ANTHROPIC_API_KEY")
        sys.exit(1)

    success = enrich_company(args.company_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
