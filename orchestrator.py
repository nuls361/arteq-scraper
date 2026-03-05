#!/usr/bin/env python3
"""
A-Line Orchestrator — Agentic decision-making layer.

Runs after all scrapers (quick_run, signal_scraper, company_discovery) and:
  1. Data Hygiene — expire stale roles, dedup contacts, calc signal density
  2. Company Scoring — Claude evaluates companies holistically, promotes/downgrades
  3. Budget-Aware Enrichment — Apollo enrich within daily/monthly credit budget
  4. Auto-Outreach — Claude writes personalized emails to outreach-ready companies
  5. Daily Brief — comprehensive summary email to Niels
  6. Decision Log — all decisions in agent_log + company_dossier

Usage: python orchestrator.py
Schedule: 07:15 UTC daily (after all scrapers)
"""

import json
import logging
import os
import re
import time
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
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "niels@arteq.app")

# Defaults (overridden by agent_config table)
DEFAULT_CONFIG = {
    "apollo_daily_credit_budget": "25",
    "apollo_monthly_credit_budget": "500",
    "role_expire_days": "60",
    "auto_promote_signal_threshold": "2",
    "auto_downgrade_days_inactive": "30",
    "outreach_mode": "draft",
    "outreach_daily_limit": "3",
    "outreach_from_email": "niels@arteq.app",
    "outreach_cc": "niels@arteq.app",
}


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def supabase_request(method, table, data=None, params=None, upsert=False):
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
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, params=params, timeout=15)
        else:
            return None
        if resp.status_code in (200, 201, 204):
            return resp.json() if resp.text else []
        else:
            logger.error(f"  Supabase {method} {table}: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"  Supabase error: {e}")
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
    """Log an agent decision."""
    supabase_request("POST", "agent_log", data={
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "reason": reason,
        "metadata": metadata,
    })


def log_dossier(company_id, entry_type, title, content, source="orchestrator"):
    """Write an entry to company_dossier."""
    supabase_request("POST", "company_dossier", data={
        "company_id": company_id,
        "entry_type": entry_type,
        "title": title,
        "content": content[:2000],
        "source": source,
        "author": "A-Line Agent",
    })


def clean_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def load_agent_soul():
    """Load the agent soul file as system prompt."""
    soul_path = os.path.join(os.path.dirname(__file__), "agent_soul.md")
    try:
        with open(soul_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


AGENT_SOUL = load_agent_soul()


def claude_request(prompt, max_tokens=1500, system=None):
    """Make a Claude API request with optional system prompt (defaults to agent soul)."""
    if not ANTHROPIC_KEY:
        return None
    try:
        body = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Use provided system prompt, fall back to agent soul
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
            logger.error(f"  Claude API {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    except Exception as e:
        logger.error(f"  Claude error: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# PHASE 1: DATA HYGIENE
# ═══════════════════════════════════════════════════════════

def phase_hygiene(config):
    """Expire stale roles, dedup contacts, calculate signal density."""
    logger.info("\n🧹 PHASE 1: DATA HYGIENE")
    results = {"roles_expired": 0, "contacts_deduped": 0, "signal_density_updated": 0}

    # ── 1a: Expire stale roles ──
    expire_days = int(config.get("role_expire_days", "60"))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=expire_days)).isoformat()

    stale = supabase_request("GET", "role", params={
        "select": "id,title,company_id,first_seen_at",
        "status": "neq.expired",
        "first_seen_at": f"lt.{cutoff}",
        "limit": "500",
    })

    for role in (stale or []):
        supabase_request("PATCH", f"role?id=eq.{role['id']}", data={"status": "expired"})
        log_decision("expire_role", "role", role["id"],
                     f"Role '{role['title']}' open since {role.get('first_seen_at', '?')[:10]} (>{expire_days} days)")
        results["roles_expired"] += 1

    if results["roles_expired"]:
        logger.info(f"  Expired {results['roles_expired']} stale roles")

    # ── 1b: Dedup contacts by linkedin_url ──
    contacts = supabase_request("GET", "contact", params={
        "select": "id,name,linkedin_url,email,phone",
        "linkedin_url": "not.is.null",
        "linkedin_url": "neq.",
        "order": "created_at.asc",
        "limit": "2000",
    })

    if contacts:
        seen = {}
        for c in contacts:
            url = (c.get("linkedin_url") or "").strip().rstrip("/").lower()
            if not url:
                continue
            if url in seen:
                # Keep the richer record, delete the duplicate
                original = seen[url]
                # Update original with any missing data from duplicate
                update = {}
                if c.get("email") and not original.get("email"):
                    update["email"] = c["email"]
                if c.get("phone") and not original.get("phone"):
                    update["phone"] = c["phone"]
                if update:
                    supabase_request("PATCH", f"contact?id=eq.{original['id']}", data=update)

                # Reassign company_contact links
                links = supabase_request("GET", "company_contact", params={
                    "contact_id": f"eq.{c['id']}", "select": "id,company_id",
                })
                for link in (links or []):
                    # Check if original already linked to this company
                    existing = supabase_request("GET", "company_contact", params={
                        "contact_id": f"eq.{original['id']}",
                        "company_id": f"eq.{link['company_id']}",
                        "select": "id", "limit": "1",
                    })
                    if not existing or len(existing) == 0:
                        supabase_request("PATCH", f"company_contact?id=eq.{link['id']}", data={
                            "contact_id": original["id"],
                        })
                    else:
                        supabase_request("DELETE", f"company_contact?id=eq.{link['id']}")

                supabase_request("DELETE", f"contact?id=eq.{c['id']}")
                log_decision("dedup_contact", "contact", c["id"],
                             f"Merged duplicate '{c['name']}' into '{original['name']}' (same LinkedIn)")
                results["contacts_deduped"] += 1
            else:
                seen[url] = c

    if results["contacts_deduped"]:
        logger.info(f"  Deduped {results['contacts_deduped']} contacts")

    # ── 1c: Signal density ──
    ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    companies = supabase_request("GET", "company", params={
        "select": "id", "limit": "1000",
    })
    for co in (companies or []):
        signals = supabase_request("GET", "signal", params={
            "company_id": f"eq.{co['id']}",
            "detected_at": f"gte.{ninety_days_ago}",
            "select": "id",
        })
        density = len(signals) if signals else 0
        supabase_request("PATCH", f"company?id=eq.{co['id']}", data={"signal_density": density})
        results["signal_density_updated"] += 1

    logger.info(f"  Signal density updated for {results['signal_density_updated']} companies")
    return results


# ═══════════════════════════════════════════════════════════
# PHASE 2: COMPANY SCORING
# ═══════════════════════════════════════════════════════════

def gather_company_intel(company_id):
    """Gather all intelligence about a company."""
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


def phase_scoring(config):
    """Claude evaluates companies and auto-promotes/downgrades."""
    logger.info("\n📊 PHASE 2: COMPANY SCORING")
    results = {"evaluated": 0, "promoted": 0, "downgraded": 0}

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — skipping")
        return results

    # Get companies that need evaluation:
    # 1. New companies (last 24h)
    # 2. Companies with new signals
    # 3. Companies not evaluated in 7+ days
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    candidates = []

    # New companies
    new_cos = supabase_request("GET", "company", params={
        "select": "id,name,status,domain,industry,funding_stage,headcount,signal_density,arteq_fit,is_agency,composite_score",
        "created_at": f"gte.{yesterday}",
        "limit": "50",
    })
    candidates.extend(new_cos or [])

    # Companies with recent signals
    recent_signals = supabase_request("GET", "signal", params={
        "select": "company_id",
        "detected_at": f"gte.{yesterday}",
        "limit": "100",
    })
    signal_company_ids = list({s["company_id"] for s in (recent_signals or [])})
    for cid in signal_company_ids[:30]:
        co = supabase_request("GET", "company", params={
            "id": f"eq.{cid}",
            "select": "id,name,status,domain,industry,funding_stage,headcount,signal_density,arteq_fit,is_agency,composite_score",
            "limit": "1",
        })
        if co:
            candidates.extend(co)

    # Stale evaluations
    stale = supabase_request("GET", "company", params={
        "select": "id,name,status,domain,industry,funding_stage,headcount,signal_density,arteq_fit,is_agency,composite_score",
        "or": f"(last_orchestrator_eval.is.null,last_orchestrator_eval.lt.{week_ago})",
        "status": "in.(lead,prospect,active)",
        "limit": "20",
    })
    candidates.extend(stale or [])

    # Dedup
    seen_ids = set()
    unique_candidates = []
    for c in candidates:
        if c["id"] not in seen_ids and not c.get("is_agency"):
            seen_ids.add(c["id"])
            unique_candidates.append(c)

    if not unique_candidates:
        logger.info("  No companies to evaluate")
        return results

    logger.info(f"  Evaluating {len(unique_candidates)} companies...")

    promote_threshold = int(config.get("auto_promote_signal_threshold", "2"))
    downgrade_days = int(config.get("auto_downgrade_days_inactive", "30"))

    # Process in batches of 4
    for i in range(0, len(unique_candidates), 4):
        batch = unique_candidates[i:i+4]
        batch_text = ""

        for co in batch:
            intel = gather_company_intel(co["id"])
            batch_text += f"\n--- Company: {co['name']} (ID: {co['id']}) ---\n"
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
                    f"{c['contact']['name']} ({c['contact'].get('title', '?')}) {'✉' if c['contact'].get('email') else ''}" for c in intel["contacts"][:3]
                ) + "\n"

        prompt = f"""Du bist der AI-Agent für A-Line, eine DACH-Fractional/Interim-Executive-Vermittlung.

Bewerte diese Companies ganzheitlich. Für jede Company:
1. composite_score (0-100): Wie vielversprechend ist diese Company als Kunde?
2. recommended_status: lead | prospect | active
3. outreach_priority: 1 (höchste) bis 10 (niedrigste)
4. reasoning: 1 Satz warum

Kriterien:
- Hat die Company aktive HOT/WARM Roles für Fractional/Interim Positionen? → starkes Signal
- Funding-Runde + Wachstum → brauchen wahrscheinlich bald Leadership
- Leadership Changes → offene Position = Chance
- Haben wir einen DM mit Email? → outreach-ready
- Agentur = DISQUALIFIZIERT (score 0)

{batch_text}

Antworte NUR in validem JSON als Array:
[{{"company_id": "...", "composite_score": 82, "recommended_status": "active", "outreach_priority": 1, "reasoning": "..."}}]"""

        text = claude_request(prompt, max_tokens=1500)
        if not text:
            continue

        try:
            evaluations = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            logger.error(f"  JSON parse error in scoring batch")
            continue

        for ev in evaluations:
            cid = ev.get("company_id")
            if not cid:
                continue

            # Find the company in our batch
            company = next((c for c in batch if str(c["id"]) == str(cid)), None)
            if not company:
                continue

            score = ev.get("composite_score", 0)
            new_status = ev.get("recommended_status", company.get("status", "lead"))
            old_status = company.get("status", "lead")
            priority = ev.get("outreach_priority")
            reasoning = ev.get("reasoning", "")

            # Update company
            update_data = {
                "composite_score": score,
                "outreach_priority": priority,
                "last_orchestrator_eval": datetime.now(timezone.utc).isoformat(),
            }

            # Auto-promotion logic
            promoted = False
            downgraded = False

            if new_status != old_status:
                # Promotion: lead → prospect or prospect → active
                if (old_status == "lead" and new_status in ("prospect", "active")) or \
                   (old_status == "prospect" and new_status == "active"):
                    update_data["status"] = new_status
                    promoted = True
                    log_decision("promote_company", "company", cid,
                                 f"{old_status} → {new_status}: {reasoning}",
                                 {"old_status": old_status, "new_status": new_status, "composite_score": score})
                    log_dossier(cid, "agent_action",
                                f"Promoted: {old_status} → {new_status}",
                                f"Agent Score: {score}/100. {reasoning}")
                    results["promoted"] += 1

                # Downgrade: prospect → lead
                elif old_status == "prospect" and new_status == "lead":
                    update_data["status"] = new_status
                    downgraded = True
                    log_decision("downgrade_company", "company", cid,
                                 f"{old_status} → {new_status}: {reasoning}",
                                 {"old_status": old_status, "new_status": new_status, "composite_score": score})
                    log_dossier(cid, "agent_action",
                                f"Downgraded: {old_status} → {new_status}",
                                f"Agent Score: {score}/100. {reasoning}")
                    results["downgraded"] += 1

            supabase_request("PATCH", f"company?id=eq.{cid}", data=update_data)
            results["evaluated"] += 1

            status_change = ""
            if promoted:
                status_change = f" ⬆ {old_status}→{new_status}"
            elif downgraded:
                status_change = f" ⬇ {old_status}→{new_status}"

            logger.info(f"  {company['name']}: score={score}, priority={priority}{status_change}")

        time.sleep(1)

    logger.info(f"  Evaluated {results['evaluated']}, promoted {results['promoted']}, downgraded {results['downgraded']}")
    return results


# ═══════════════════════════════════════════════════════════
# PHASE 3: BUDGET-AWARE ENRICHMENT
# ═══════════════════════════════════════════════════════════

def phase_enrichment(config):
    """Enrich high-priority contacts within Apollo credit budget."""
    logger.info("\n💰 PHASE 3: BUDGET-AWARE ENRICHMENT")
    results = {"enriched": 0, "credits_used": 0, "budget_remaining": 0}

    if not APOLLO_API_KEY:
        logger.info("  No APOLLO_API_KEY — skipping")
        return results

    # Check budget
    daily_budget = int(config.get("apollo_daily_credit_budget", "25"))
    monthly_budget = int(config.get("apollo_monthly_credit_budget", "500"))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")

    daily_used = supabase_request("GET", "apollo_credit_ledger", params={
        "select": "credits", "created_at": f"gte.{today}T00:00:00Z",
    })
    monthly_used = supabase_request("GET", "apollo_credit_ledger", params={
        "select": "credits", "created_at": f"gte.{month_start}T00:00:00Z",
    })

    daily_spent = sum(r["credits"] for r in (daily_used or []))
    monthly_spent = sum(r["credits"] for r in (monthly_used or []))
    available = min(daily_budget - daily_spent, monthly_budget - monthly_spent)

    results["budget_remaining"] = available
    logger.info(f"  Budget: {available} credits available (daily: {daily_spent}/{daily_budget}, monthly: {monthly_spent}/{monthly_budget})")

    if available <= 0:
        logger.info("  Budget exhausted — skipping enrichment")
        return results

    # Find un-enriched DM contacts at high-priority companies
    # Join company_contact with contact and company
    links = supabase_request("GET", "company_contact", params={
        "select": "company_id,contact_id,contact:contact_id(id,name,email,enriched_at,linkedin_url),is_decision_maker",
        "is_decision_maker": "eq.true",
        "limit": "200",
    })

    candidates = []
    for link in (links or []):
        contact = link.get("contact")
        if not contact or contact.get("email") or contact.get("enriched_at"):
            continue  # Already has email or was already enriched

        # Get company priority
        co = supabase_request("GET", "company", params={
            "id": f"eq.{link['company_id']}",
            "select": "id,name,status,composite_score,outreach_priority,is_agency,domain",
            "limit": "1",
        })
        if not co or co[0].get("is_agency"):
            continue

        company = co[0]
        if company.get("status") not in ("active", "prospect"):
            continue

        candidates.append({
            "contact": contact,
            "company": company,
            "priority": company.get("outreach_priority") or 999,
        })

    # Sort by priority (lower = higher priority)
    candidates.sort(key=lambda x: x["priority"])

    for cand in candidates[:available]:
        contact = cand["contact"]
        company = cand["company"]
        domain = (company.get("domain") or "").strip()

        # Apollo People Match (1 credit)
        try:
            payload = {}
            name = contact.get("name", "")
            parts = name.split(" ", 1)
            payload["first_name"] = parts[0]
            if len(parts) > 1:
                payload["last_name"] = parts[1]
            if domain:
                payload["organization_domain"] = domain
            payload["reveal_personal_emails"] = False
            payload["reveal_phone_number"] = True

            resp = requests.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": APOLLO_API_KEY,
                },
                json=payload,
                timeout=15,
            )

            if resp.status_code != 200:
                continue

            person = resp.json().get("person")
            if not person:
                continue

            update = {"enriched_at": datetime.now(timezone.utc).isoformat()}
            email = person.get("email")
            phone = None
            phone_numbers = person.get("phone_numbers") or []
            if phone_numbers:
                phone = phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("number")

            if email:
                update["email"] = email
                update["email_status"] = person.get("email_status", "unknown")
            if phone:
                update["phone"] = phone

            supabase_request("PATCH", f"contact?id=eq.{contact['id']}", data=update)

            # Log credit
            supabase_request("POST", "apollo_credit_ledger", data={
                "action": "people_enrich",
                "credits": 1,
                "contact_id": contact["id"],
                "company_id": company["id"],
            })

            log_decision("enrich_contact", "contact", contact["id"],
                         f"Enriched {contact['name']} at {company['name']} — email={'yes' if email else 'no'}, phone={'yes' if phone else 'no'}",
                         {"email_found": bool(email), "phone_found": bool(phone)})
            log_dossier(company["id"], "agent_action",
                        f"Contact enriched: {contact['name']}",
                        f"Apollo enrichment: {'email found' if email else 'no email'}, {'phone found' if phone else 'no phone'}")

            results["enriched"] += 1
            results["credits_used"] += 1

            logger.info(f"  ✅ Enriched {contact['name']} at {company['name']}: email={'yes' if email else 'no'}")
            time.sleep(1)

        except Exception as e:
            logger.error(f"  Enrichment error for {contact.get('name')}: {e}")

    results["budget_remaining"] = available - results["credits_used"]
    logger.info(f"  Enriched {results['enriched']} contacts, {results['credits_used']} credits used")
    return results


# ═══════════════════════════════════════════════════════════
# PHASE 4: AUTO-OUTREACH (with persona + learning)
# ═══════════════════════════════════════════════════════════

def get_persona(config):
    """Load outreach persona from config."""
    try:
        return json.loads(config.get("outreach_persona", "{}"))
    except json.JSONDecodeError:
        return {}


def get_successful_examples():
    """Load outreach emails that got positive replies — used as few-shot examples."""
    examples = supabase_request("GET", "outreach", params={
        "select": "subject,body_html,company_id,contact_id",
        "got_reply": "eq.true",
        "reply_sentiment": "in.(positive,interested)",
        "direction": "eq.outbound",
        "order": "created_at.desc",
        "limit": "5",
    })
    if not examples:
        return ""

    example_text = "\n\n--- BEISPIEL-EMAILS DIE FUNKTIONIERT HABEN ---\n"
    for i, ex in enumerate(examples, 1):
        # Strip HTML tags for a cleaner example
        body = re.sub(r"<[^>]+>", "", ex.get("body_html", ""))
        body = re.sub(r"\s+", " ", body).strip()
        example_text += f"\nBeispiel {i}:\nBetreff: {ex.get('subject', '')}\nText: {body[:300]}\n"

    example_text += "\n--- ENDE BEISPIELE ---\nOrientiere dich am Stil dieser erfolgreichen Emails.\n"
    return example_text


def build_outreach_prompt(persona, dm, co, intel, examples_text):
    """Build the outreach prompt with persona + learning."""
    # Build company context
    context = f"Company: {co['name']}\n"
    context += f"Industry: {co.get('industry', '?')} | Funding: {co.get('funding_stage', '?')}\n"
    context += f"Contact: {dm['name']} ({dm.get('title', '?')})\n"

    if intel["roles"]:
        context += "Aktive Roles: " + ", ".join(
            f"{r['title']} ({r.get('engagement_type', '?')})" for r in intel["roles"][:3]
        ) + "\n"

    if intel["signals"]:
        context += "Signals: " + ", ".join(
            f"{s.get('type')}: {s.get('title', '')[:40]}" for s in intel["signals"][:3]
        ) + "\n"

    # Persona rules
    dos = "\n".join(f"  - {d}" for d in persona.get("dos", []))
    donts = "\n".join(f"  - {d}" for d in persona.get("donts", []))
    value_props = "\n".join(f"  - {v}" for v in persona.get("value_props", []))

    first_name = dm["name"].split()[0] if dm.get("name") else "?"
    signature = persona.get("signature", "Beste Grüße,\nNiels")

    prompt = f"""Du bist {persona.get('name', 'Niels')} von {persona.get('company', 'A-Line')}.
{persona.get('role', 'Fractional & Interim Executive Vermittlung im DACH-Raum')}.

Tonalität: {persona.get('tone', 'Locker-professionell')}
Sprache: {persona.get('language', 'Deutsch, Du-Form')}

DO:
{dos}

DON'T:
{donts}

Value Props die du einsetzen kannst:
{value_props}

Kontext über die Company:
{context}
{examples_text}
Schreibe eine Outreach-Email an {dm['name']} ({dm.get('title', '')}) bei {co['name']}.
Begrüßung: "Hi {first_name}"
Unterschrift: {signature}

Antworte NUR in validem JSON:
{{"subject": "Betreff", "body_html": "<p>Email HTML Body</p>"}}"""

    return prompt


def send_outreach_email(from_email, to_email, cc_email, subject, body_html):
    """Send email via Resend, return (resend_id, message_id) or (None, None)."""
    try:
        import resend
        resend.api_key = RESEND_API_KEY

        send_params = {
            "from": f"Niels <{from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": body_html,
        }
        if cc_email and cc_email != to_email:
            send_params["cc"] = [cc_email]

        result = resend.Emails.send(send_params)
        return result.get("id"), None
    except Exception as e:
        logger.error(f"  Send error: {e}")
        return None, None


def phase_outreach(config):
    """Generate and send personalized outreach emails with persona + learning."""
    logger.info("\n📨 PHASE 4: AUTO-OUTREACH")
    results = {"drafts_created": 0, "emails_sent": 0, "replies_processed": 0, "followups_sent": 0}

    outreach_mode = config.get("outreach_mode", "draft")
    daily_limit = int(config.get("outreach_daily_limit", "3"))
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")

    if outreach_mode == "off":
        logger.info("  Outreach mode: OFF — skipping")
        return results

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — skipping")
        return results

    # Load persona and successful examples for learning
    persona = get_persona(config)
    examples_text = get_successful_examples()

    if examples_text:
        logger.info("  📚 Loaded successful email examples for learning")

    # ── 4a: Process new replies & auto-respond ──
    results["replies_processed"], results["followups_sent"] = phase_reply_handler(
        config, persona, from_email, cc_email
    )

    # ── 4b: New outreach to fresh companies ──
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_outreach = supabase_request("GET", "outreach", params={
        "select": "id",
        "direction": "eq.outbound",
        "created_at": f"gte.{today}T00:00:00Z",
        "limit": "100",
    })
    already_sent = len(today_outreach or [])

    if already_sent >= daily_limit:
        logger.info(f"  Daily limit reached ({already_sent}/{daily_limit})")
        return results

    remaining = daily_limit - already_sent

    # Find outreach-ready companies
    companies = supabase_request("GET", "company", params={
        "select": "id,name,status,composite_score,outreach_priority,industry,funding_stage,domain",
        "status": "in.(active,prospect)",
        "composite_score": "gte.65",
        "is_agency": "eq.false",
        "order": "outreach_priority.asc.nullslast",
        "limit": "20",
    })

    outreach_candidates = []
    for co in (companies or []):
        existing = supabase_request("GET", "outreach", params={
            "company_id": f"eq.{co['id']}", "select": "id", "limit": "1",
        })
        if existing and len(existing) > 0:
            continue

        links = supabase_request("GET", "company_contact", params={
            "company_id": f"eq.{co['id']}",
            "is_decision_maker": "eq.true",
            "select": "contact:contact_id(id,name,title,email,linkedin_url)",
            "limit": "1",
        })
        dm = None
        for link in (links or []):
            if link.get("contact") and link["contact"].get("email"):
                dm = link["contact"]
                break

        if not dm:
            continue

        outreach_candidates.append({"company": co, "dm": dm})

    if not outreach_candidates:
        logger.info("  No outreach-ready companies")
        return results

    logger.info(f"  {len(outreach_candidates)} candidates, processing {min(remaining, len(outreach_candidates))}")

    for cand in outreach_candidates[:remaining]:
        co = cand["company"]
        dm = cand["dm"]
        intel = gather_company_intel(co["id"])

        prompt = build_outreach_prompt(persona, dm, co, intel, examples_text)
        text = claude_request(prompt, max_tokens=800)
        if not text:
            continue

        try:
            email_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            logger.error(f"  JSON parse error for outreach to {co['name']}")
            continue

        subject = email_data.get("subject", f"A-Line x {co['name']}")
        body_html = email_data.get("body_html", "")

        if not body_html:
            continue

        outreach_status = "draft"
        sent_at = None
        resend_id = None

        if outreach_mode == "auto" and RESEND_API_KEY:
            resend_id, _ = send_outreach_email(from_email, dm["email"], cc_email, subject, body_html)
            if resend_id:
                outreach_status = "sent"
                sent_at = datetime.now(timezone.utc).isoformat()
                results["emails_sent"] += 1
                logger.info(f"  📨 SENT: {subject} → {dm['email']}")
            else:
                outreach_status = "draft"
        else:
            results["drafts_created"] += 1
            logger.info(f"  📝 DRAFT: {subject} → {dm['email']}")

        # Create outreach record with thread tracking
        outreach_record = supabase_request("POST", "outreach", data={
            "company_id": co["id"],
            "contact_id": dm["id"],
            "subject": subject,
            "body_html": body_html,
            "status": outreach_status,
            "sent_at": sent_at,
            "resend_email_id": resend_id,
            "direction": "outbound",
            "from_email": from_email,
        })

        # Set thread_id = own id for initial outreach
        if outreach_record and len(outreach_record) > 0:
            oid = outreach_record[0]["id"]
            supabase_request("PATCH", f"outreach?id=eq.{oid}", data={"thread_id": oid})

        log_decision("outreach_" + outreach_status, "company", co["id"],
                      f"{'Sent' if outreach_status == 'sent' else 'Draft'} outreach to {dm['name']} ({dm.get('title', '')}) — {subject}",
                      {"contact_email": dm["email"], "subject": subject})
        log_dossier(co["id"], "outreach",
                    f"{'Sent' if outreach_status == 'sent' else 'Draft'}: {subject}",
                    f"To: {dm['name']} ({dm['email']})\n\n{body_html[:500]}")

        time.sleep(1)

    logger.info(f"  Drafts: {results['drafts_created']}, Sent: {results['emails_sent']}, "
                f"Replies: {results['replies_processed']}, Follow-ups: {results['followups_sent']}")
    return results


# ═══════════════════════════════════════════════════════════
# PHASE 4b: REPLY HANDLER (auto-respond to inbound replies)
# ═══════════════════════════════════════════════════════════

def phase_reply_handler(config, persona, from_email, cc_email):
    """Process new inbound replies and auto-respond."""
    replies_processed = 0
    followups_sent = 0

    max_followups = int(config.get("outreach_max_followups", "3"))
    outreach_mode = config.get("outreach_mode", "draft")

    # Load reply style config
    try:
        reply_style = json.loads(config.get("outreach_reply_style", "{}"))
    except json.JSONDecodeError:
        reply_style = {}

    # Find unprocessed inbound replies (status = 'replied' means we haven't responded yet)
    new_replies = supabase_request("GET", "outreach", params={
        "select": "id,thread_id,company_id,contact_id,subject,body_html,raw_text,from_email,created_at",
        "direction": "eq.inbound",
        "status": "eq.replied",
        "order": "created_at.asc",
        "limit": "20",
    })

    if not new_replies:
        return 0, 0

    logger.info(f"  💬 {len(new_replies)} new replies to process")

    for reply in new_replies:
        thread_id = reply.get("thread_id")
        company_id = reply.get("company_id")
        contact_id = reply.get("contact_id")

        if not thread_id or not company_id:
            continue

        # Load full conversation thread
        thread = supabase_request("GET", "outreach", params={
            "thread_id": f"eq.{thread_id}",
            "select": "id,direction,subject,body_html,raw_text,created_at,status",
            "order": "created_at.asc",
        })

        # Count our outbound messages in this thread
        our_messages = [t for t in (thread or []) if t.get("direction") == "outbound"]
        if len(our_messages) >= max_followups:
            logger.info(f"  Max follow-ups ({max_followups}) reached for thread {thread_id}")
            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "closed"})
            continue

        # Classify reply sentiment
        reply_text = reply.get("raw_text") or re.sub(r"<[^>]+>", "", reply.get("body_html", ""))
        sentiment = classify_reply_sentiment(reply_text)
        supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"reply_sentiment": sentiment})

        # Mark the original outbound as got_reply
        original = supabase_request("GET", "outreach", params={
            "thread_id": f"eq.{thread_id}",
            "direction": "eq.outbound",
            "order": "created_at.asc",
            "limit": "1",
            "select": "id",
        })
        if original:
            supabase_request("PATCH", f"outreach?id=eq.{original[0]['id']}", data={
                "got_reply": True,
                "reply_sentiment": sentiment,
            })

        replies_processed += 1

        # Get company + contact info for context
        co = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,industry,funding_stage",
            "limit": "1",
        })
        contact = supabase_request("GET", "contact", params={
            "id": f"eq.{contact_id}",
            "select": "id,name,title,email",
            "limit": "1",
        })

        if not co or not contact:
            continue

        company = co[0]
        dm = contact[0]

        # Build conversation history for Claude
        conv_history = ""
        for msg in (thread or []):
            sender = "Niels (A-Line)" if msg.get("direction") == "outbound" else dm.get("name", "Kontakt")
            body = msg.get("raw_text") or re.sub(r"<[^>]+>", "", msg.get("body_html", ""))
            body = re.sub(r"\s+", " ", body).strip()
            conv_history += f"\n[{sender}]: {body[:500]}\n"

        reply_rules = "\n".join(f"  - {r}" for r in reply_style.get("rules", []))
        reply_signature = persona.get("signature", "Beste Grüße,\nNiels")
        reply_tone = reply_style.get("tone", persona.get("tone", "Persönlich und auf Augenhöhe"))
        reply_lang = persona.get("language", "Deutsch, Du-Form")
        reply_name = persona.get("name", "Niels")
        reply_company = persona.get("company", "A-Line")
        dm_name = dm.get("name", "?")
        dm_title = dm.get("title", "?")
        co_name = company.get("name", "?")
        sentiment_hint = ""
        if sentiment in ("positive", "interested"):
            sentiment_hint = "Die Person scheint interessiert — schlage einen konkreten Termin vor."
        elif sentiment in ("negative", "not_interested"):
            sentiment_hint = "Die Person scheint nicht interessiert — akzeptiere freundlich, halte die Tür offen für die Zukunft."

        prompt = f"""Du bist {reply_name} von {reply_company}.
Tonalität: {reply_tone}
Sprache: {reply_lang}

Regeln für Replies:
{reply_rules}

Bisherige Konversation mit {dm_name} ({dm_title}) von {co_name}:
{conv_history}

Sentiment der letzten Antwort: {sentiment}

{sentiment_hint}

Schreibe die nächste Antwort. Kurz (2-4 Sätze).
Unterschrift: {reply_signature}

Antworte NUR in validem JSON:
{{"subject": "Re: ...", "body_html": "<p>Antwort HTML</p>"}}"""

        text = claude_request(prompt, max_tokens=600)
        if not text:
            continue

        try:
            followup_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            logger.error(f"  JSON parse error for reply to {dm.get('name', '?')}")
            continue

        subject = followup_data.get("subject", f"Re: {reply.get('subject', '')}")
        body_html = followup_data.get("body_html", "")

        if not body_html:
            continue

        followup_status = "draft"
        sent_at = None
        resend_id = None

        if outreach_mode == "auto" and RESEND_API_KEY and dm.get("email"):
            resend_id, _ = send_outreach_email(from_email, dm["email"], cc_email, subject, body_html)
            if resend_id:
                followup_status = "sent"
                sent_at = datetime.now(timezone.utc).isoformat()
                followups_sent += 1
                logger.info(f"  💬 REPLY SENT: {subject} → {dm['email']}")
            else:
                followup_status = "draft"

        # Save follow-up
        supabase_request("POST", "outreach", data={
            "company_id": company_id,
            "contact_id": contact_id,
            "subject": subject,
            "body_html": body_html,
            "status": followup_status,
            "sent_at": sent_at,
            "resend_email_id": resend_id,
            "direction": "outbound",
            "thread_id": thread_id,
            "in_reply_to": reply["id"],
            "from_email": from_email,
        })

        # Update original reply status to indicate we've responded
        supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "answered"})

        log_decision("outreach_reply", "company", company_id,
                     f"Auto-reply to {dm.get('name', '?')} (sentiment: {sentiment}) — {subject}",
                     {"sentiment": sentiment, "thread_id": thread_id})
        log_dossier(company_id, "outreach",
                    f"Reply sent: {subject}",
                    f"Auto-reply to {dm.get('name', '?')} (sentiment: {sentiment})\n\n{body_html[:500]}")

        time.sleep(1)

    return replies_processed, followups_sent


def classify_reply_sentiment(text):
    """Use Claude to classify reply sentiment."""
    if not text or not ANTHROPIC_KEY:
        return "neutral"

    prompt = f"""Klassifiziere diese Email-Antwort in eine Kategorie:
- "interested" — Person zeigt Interesse, will mehr wissen, ist offen für ein Gespräch
- "positive" — Freundlich, offen, aber noch kein konkretes Interesse
- "neutral" — Unklar, Rückfragen, weder positiv noch negativ
- "not_interested" — Höfliche Absage, kein Bedarf momentan
- "negative" — Klare Absage, genervt, will nicht kontaktiert werden

Email-Antwort:
{text[:500]}

Antworte NUR mit einem Wort: interested, positive, neutral, not_interested, oder negative"""

    result = claude_request(prompt, max_tokens=20)
    if result:
        result = result.strip().lower().strip('"').strip("'")
        if result in ("interested", "positive", "neutral", "not_interested", "negative"):
            return result
    return "neutral"


# ═══════════════════════════════════════════════════════════
# PHASE 5: DAILY BRIEF
# ═══════════════════════════════════════════════════════════

def phase_daily_brief(config, run_results):
    """Generate and send comprehensive daily brief."""
    logger.info("\n📋 PHASE 5: DAILY BRIEF")

    if not RESEND_API_KEY:
        logger.info("  No RESEND_API_KEY — skipping")
        return

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — skipping")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Gather brief data
    new_roles = supabase_request("GET", "role", params={
        "select": "title,tier,final_score,company_id",
        "first_seen_at": f"gte.{today}",
        "order": "final_score.desc", "limit": "20",
    })
    new_signals = supabase_request("GET", "signal", params={
        "select": "title,type,urgency,company_name_raw",
        "detected_at": f"gte.{today}T00:00:00Z",
        "order": "relevance_score.desc", "limit": "15",
    })
    new_companies = supabase_request("GET", "company", params={
        "select": "name,industry,funding_stage,arteq_fit",
        "created_at": f"gte.{today}T00:00:00Z",
    })
    top_outreach = supabase_request("GET", "company", params={
        "select": "name,composite_score,outreach_priority,status,signal_density",
        "status": "in.(active,prospect)",
        "order": "outreach_priority.asc.nullslast",
        "limit": "10",
    })
    today_decisions = supabase_request("GET", "agent_log", params={
        "select": "action,entity_type,reason",
        "created_at": f"gte.{today}T00:00:00Z",
        "order": "created_at.asc",
    })
    outreach_drafts = supabase_request("GET", "outreach", params={
        "select": "subject,status,company_id",
        "created_at": f"gte.{today}T00:00:00Z",
    })

    brief_data = json.dumps({
        "date": datetime.now().strftime("%d.%m.%Y"),
        "run_results": run_results,
        "new_roles_count": len(new_roles or []),
        "hot_roles": [r for r in (new_roles or []) if r.get("tier") == "HOT"],
        "new_signals": (new_signals or [])[:10],
        "new_companies_discovered": (new_companies or [])[:10],
        "top_outreach_candidates": (top_outreach or [])[:5],
        "agent_decisions": (today_decisions or [])[:20],
        "outreach_drafts": (outreach_drafts or []),
    }, indent=2, ensure_ascii=False, default=str)

    prompt = f"""Schreibe eine tägliche Zusammenfassungs-Email für Niels von A-Line (Fractional/Interim Executive Vermittlung im DACH-Raum).

Deutsch, informell (du-Form), professionell, action-orientiert. Schreibe als HTML mit inline CSS (clean, modernes Design).

Daten vom heutigen Run:
{brief_data}

Die Email soll enthalten:
1. **Kurzes Intro** (2-3 Sätze, was heute passiert ist)
2. **Key Numbers** als kompakte Übersicht (neue Roles, Signals, Companies, Agent-Entscheidungen)
3. **Agent-Aktionen** — was der Agent gemacht hat (Promotions, Expirys, Enrichments)
4. **Top 5 Outreach-Kandidaten** mit Company, Score, Status, empfohlener Aktion
5. **Outreach-Drafts** — falls vorhanden, Subjects + Status
6. **Neue Signals** — wichtigste Funding/Leadership News
7. **Apollo Budget** — Credits verbraucht/übrig

Starte direkt mit <div>. Kein Markdown, keine Backticks."""

    html = claude_request(prompt, max_tokens=2500)
    if not html:
        logger.error("  Failed to generate daily brief")
        return

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        hygiene = run_results.get("hygiene", {})
        scoring = run_results.get("scoring", {})
        enrichment = run_results.get("enrichment", {})
        outreach = run_results.get("outreach", {})

        subject_parts = []
        if scoring.get("promoted"):
            subject_parts.append(f"{scoring['promoted']} promoted")
        if outreach.get("drafts_created") or outreach.get("emails_sent"):
            subject_parts.append(f"{outreach.get('drafts_created', 0) + outreach.get('emails_sent', 0)} outreach")
        if len(new_roles or []) > 0:
            hot = sum(1 for r in new_roles if r.get("tier") == "HOT")
            subject_parts.append(f"{hot} hot leads" if hot else f"{len(new_roles)} new roles")

        subject = f"A-Line Agent Brief {datetime.now().strftime('%d.%m')} — " + (", ".join(subject_parts) or "no changes")

        resend.Emails.send({
            "from": "A-Line Agent <onboarding@resend.dev>",
            "to": [ALERT_EMAIL],
            "subject": subject,
            "html": html,
        })
        logger.info(f"  ✅ Daily brief sent to {ALERT_EMAIL}")

    except Exception as e:
        logger.error(f"  Brief send error: {e}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 80)
    print("  A-LINE ORCHESTRATOR — Agentic Decision Layer")
    print(f"  AI: {'ON ✓' if ANTHROPIC_KEY else 'OFF'}")
    print(f"  Apollo: {'ON ✓' if APOLLO_API_KEY else 'OFF'}")
    print(f"  Resend: {'ON ✓' if RESEND_API_KEY else 'OFF'}")
    print(f"  Supabase: {'ON ✓' if SUPABASE_URL else 'OFF'}")
    print("=" * 80)

    if not SUPABASE_URL:
        print("  ⚠️ No SUPABASE_URL — cannot run orchestrator")
        return

    # Phase 0: Pre-flight healthcheck
    logger.info("\n🏥 PHASE 0: HEALTHCHECK")
    try:
        from healthcheck import run_healthcheck
        _checks, healthy = run_healthcheck()
        if not healthy:
            logger.warning("  Healthcheck found issues — continuing with caution")
    except Exception as e:
        logger.warning(f"  Healthcheck error: {e} — continuing anyway")

    config = get_config()
    logger.info(f"  Outreach mode: {config.get('outreach_mode', 'draft')}")

    run_results = {}

    # Phase 1: Data Hygiene
    run_results["hygiene"] = phase_hygiene(config)

    # Phase 2: Company Scoring
    run_results["scoring"] = phase_scoring(config)

    # Phase 3: Budget-Aware Enrichment
    run_results["enrichment"] = phase_enrichment(config)

    # Phase 4a: SDR Agent (cold outreach + reply handling)
    try:
        import sdr_agent
        run_results["sdr"] = sdr_agent.run(config)
    except Exception as exc:
        logger.error(f"  SDR Agent error: {exc}")
        run_results["sdr"] = {}

    # Phase 4b: AE Agent (qualified leads + meeting prep + proposals)
    try:
        import ae_agent
        run_results["ae"] = ae_agent.run(config)
    except Exception as exc:
        logger.error(f"  AE Agent error: {exc}")
        run_results["ae"] = {}

    # Phase 5: Daily Brief
    phase_daily_brief(config, run_results)

    # Summary
    print(f"\n{'='*80}")
    print(f"  ORCHESTRATOR COMPLETE")
    h = run_results.get("hygiene", {})
    s = run_results.get("scoring", {})
    e = run_results.get("enrichment", {})
    sdr = run_results.get("sdr", {})
    ae = run_results.get("ae", {})
    print(f"  Hygiene: {h.get('roles_expired', 0)} expired, {h.get('contacts_deduped', 0)} deduped")
    print(f"  Scoring: {s.get('evaluated', 0)} evaluated, {s.get('promoted', 0)} promoted, {s.get('downgraded', 0)} downgraded")
    print(f"  Enrichment: {e.get('enriched', 0)} contacts ({e.get('credits_used', 0)} credits)")
    print(f"  SDR: {sdr.get('emails_sent', 0)} sent, {sdr.get('drafts_created', 0)} drafts, "
          f"{sdr.get('replies_processed', 0)} replies, {sdr.get('handoffs', 0)} handoffs")
    print(f"  AE:  {ae.get('responses_sent', 0)} responses, {ae.get('briefings_created', 0)} briefings, "
          f"{ae.get('proposals_created', 0)} proposals")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
