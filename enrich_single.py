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

    # Build evaluation prompt
    batch_text = f"--- Company: {co['name']} (ID: {co['id']}) ---\n"
    batch_text += f"Status: {co.get('status', 'unknown')} | Industry: {co.get('industry', '?')} | Funding: {co.get('funding_stage', '?')} | Headcount: {co.get('headcount', '?')} | Signal Density: {co.get('signal_density', 0)} | Current Fit: {co.get('arteq_fit', '?')}\n"

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

    prompt = f"""Du bist der AI-Agent für A-Line, eine DACH-Fractional/Interim-Executive-Vermittlung.

Bewerte diese Company ganzheitlich:
1. composite_score (0-100): Wie vielversprechend ist diese Company als Kunde?
2. recommended_status: lead | prospect | active
3. outreach_priority: 1 (höchste) bis 10 (niedrigste)
4. reasoning: 2-3 Sätze mit detaillierter Begründung

Kriterien:
- Hat die Company aktive HOT/WARM Roles für Fractional/Interim Positionen? → starkes Signal
- Funding-Runde + Wachstum → brauchen wahrscheinlich bald Leadership
- Leadership Changes → offene Position = Chance
- Haben wir einen DM mit Email? → outreach-ready
- Agentur = DISQUALIFIZIERT (score 0)

{batch_text}

Antworte NUR in validem JSON:
{{"company_id": "...", "composite_score": 82, "recommended_status": "active", "outreach_priority": 1, "reasoning": "..."}}"""

    text = claude_request(prompt, max_tokens=800)
    if not text:
        logger.error("Claude returned no response")
        return False

    try:
        ev = json.loads(clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return False

    score = ev.get("composite_score", 0)
    new_status = ev.get("recommended_status", co.get("status", "lead"))
    old_status = co.get("status", "lead")
    priority = ev.get("outreach_priority")
    reasoning = ev.get("reasoning", "")

    logger.info(f"Claude evaluation: score={score}, status={new_status}, priority={priority}")
    logger.info(f"Reasoning: {reasoning}")

    # Update company
    update_data = {
        "composite_score": score,
        "outreach_priority": priority,
        "last_orchestrator_eval": datetime.now(timezone.utc).isoformat(),
    }

    # Status promotion logic
    if new_status != old_status:
        if (old_status == "lead" and new_status in ("prospect", "active")) or \
           (old_status == "prospect" and new_status == "active"):
            update_data["status"] = new_status
            logger.info(f"Promoting: {old_status} -> {new_status}")
        elif old_status == "prospect" and new_status == "lead":
            update_data["status"] = new_status
            logger.info(f"Downgrading: {old_status} -> {new_status}")

    supabase_request("PATCH", f"company?id=eq.{company_id}", data=update_data)

    # Write dossier entry
    status_note = ""
    if update_data.get("status"):
        status_note = f"\nStatus: {old_status} -> {update_data['status']}"
    dossier_content = f"Agent Score: {score}/100 | Priority: {priority}/10{status_note}\n\n{reasoning}"

    supabase_request("POST", "company_dossier", data={
        "company_id": company_id,
        "entry_type": "agent_action",
        "title": f"Manual Enrichment — Score: {score}/100",
        "content": dossier_content[:2000],
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
