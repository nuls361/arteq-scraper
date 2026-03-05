#!/usr/bin/env python3
"""
A-Line SDR Agent — Top of Funnel.

Handles:
  - Cold outreach to opportunities in ready_for_outreach stage
  - Follow-up sequences
  - Reply handling & sentiment classification
  - Auto-handoff to AE when "interested" reply detected

Reads from opportunity table with different templates based on pipeline_type.

Usage: python -m pipeline.sdr_agent (called by orchestrator)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sdr_agent")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")


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
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            logger.error(f"Supabase {method} {table}: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Supabase error: {e}")
        return None


def claude_request(prompt, max_tokens=800, system=None):
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
        idx = t.find('{')
        if idx >= 0:
            t = t[idx:]
    if t and t[0] == '{':
        depth = 0
        for i, c in enumerate(t):
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            if depth == 0:
                t = t[:i + 1]
                break
    return t


def load_soul():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_soul_sdr.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


SDR_SOUL = load_soul()


def gather_company_intel(company_id):
    """Gather roles, signals, contacts for a company."""
    roles = supabase_request("GET", "role", params={
        "company_id": f"eq.{company_id}",
        "select": "title,tier,is_hot,engagement_type,role_function,status",
        "order": "created_at.desc", "limit": "10",
    })
    signals = supabase_request("GET", "signal", params={
        "company_id": f"eq.{company_id}",
        "select": "type,title,relevance_score,urgency,is_hot",
        "order": "detected_at.desc", "limit": "10",
    })
    contacts = supabase_request("GET", "company_contact", params={
        "company_id": f"eq.{company_id}",
        "select": "is_decision_maker,role_at_company,contact:contact_id(id,name,title,email,linkedin_url,decision_maker_score)",
    })
    return {
        "roles": roles or [],
        "signals": signals or [],
        "contacts": [c for c in (contacts or []) if c.get("contact")],
    }


def log_decision(action, entity_type, entity_id, reason, metadata=None):
    supabase_request("POST", "agent_log", data={
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "reason": reason,
        "metadata": json.dumps(metadata) if metadata else None,
    })


def log_dossier(company_id, entry_type, title, content):
    supabase_request("POST", "company_dossier", data={
        "company_id": company_id,
        "entry_type": entry_type,
        "title": title[:500],
        "content": (content or "")[:5000],
        "source": "sdr_agent",
    })


def send_email(from_email, to_email, cc_email, subject, body_html):
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
        return result.get("id")
    except Exception as e:
        logger.error(f"  Send error: {e}")
        return None


def get_config():
    """Load agent config from Supabase."""
    result = supabase_request("GET", "agent_config", params={"select": "key,value"})
    return {r["key"]: r["value"] for r in (result or [])}


# ═══════════════════════════════════════════════════════════
# OUTREACH — Based on pipeline_type
# ═══════════════════════════════════════════════════════════

def get_successful_examples():
    examples = supabase_request("GET", "outreach", params={
        "select": "subject,body_html",
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
        body = re.sub(r"<[^>]+>", "", ex.get("body_html", ""))
        body = re.sub(r"\s+", " ", body).strip()
        example_text += f"\nBeispiel {i}:\nBetreff: {ex.get('subject', '')}\nText: {body[:300]}\n"
    example_text += "\n--- ENDE BEISPIELE ---\nOrientiere dich am Stil dieser erfolgreichen Emails.\n"
    return example_text


def build_outreach_prompt(opp, company, dm, intel, examples_text, persona):
    """Build outreach prompt with different messaging based on pipeline_type."""
    pipeline_type = opp.get("pipeline_type", "role")
    context = f"Company: {company.get('name', '?')}\n"
    context += f"Industry: {company.get('industry', '?')} | Funding: {company.get('funding_stage', '?')}\n"
    context += f"Contact: {dm['name']} ({dm.get('title', '?')})\n"

    if intel["roles"]:
        context += "Aktive Roles: " + ", ".join(
            f"{r['title']} ({r.get('engagement_type', '?')})" for r in intel["roles"][:3]
        ) + "\n"

    if intel["signals"]:
        context += "Signals: " + ", ".join(
            f"{s.get('type')}: {s.get('title', '')[:40]}" for s in intel["signals"][:3]
        ) + "\n"

    # Pipeline-specific messaging
    if pipeline_type == "role":
        role_title = opp.get("notes", "").replace("Hot role: ", "").split(" — ")[0]
        angle = f"""ANLASS: Die Company sucht aktiv einen {role_title}.
MESSAGING: "Wir haben gesehen, dass ihr einen {role_title} sucht — wir haben erfahrene Interim/Fractional {role_title} in unserem Netzwerk, die sofort starten können."
FOKUS: Schnelligkeit, Erfahrung, Flexibilität unserer Executives."""
    else:
        signal_info = opp.get("notes", "").replace("Signal: ", "")
        angle = f"""ANLASS: Signal — {signal_info}
MESSAGING: "Wir haben von [Signal] gelesen — in dieser Phase brauchen Unternehmen häufig erfahrene Interim-Führungskräfte. Wir können helfen."
FOKUS: Situationsverständnis, typische Herausforderungen, wie A-Line Interim/Fractional Executives sofort einsetzen kann."""

    dos = "\n".join(f"  - {d}" for d in persona.get("dos", []))
    donts = "\n".join(f"  - {d}" for d in persona.get("donts", []))
    value_props = "\n".join(f"  - {v}" for v in persona.get("value_props", []))
    first_name = dm["name"].split()[0] if dm.get("name") else "?"
    signature = persona.get("signature", "Beste Grüße,\nNiels")

    return f"""Kontext über die Company:
{context}

{angle}

{examples_text}

DO:
{dos}

DON'T:
{donts}

Value Props:
{value_props}

Schreibe eine Cold Outreach-Email an {dm['name']} ({dm.get('title', '')}) bei {company.get('name', '?')}.
Begrüßung: "Hi {first_name}"
Unterschrift: {signature}

Antworte NUR in validem JSON:
{{"subject": "Betreff", "body_html": "<p>Email HTML Body</p>"}}"""


def run_cold_outreach(config):
    """Generate and send cold outreach for ready opportunities."""
    results = {"drafts_created": 0, "emails_sent": 0}

    outreach_mode = config.get("outreach_mode", "draft")
    daily_limit = int(config.get("outreach_daily_limit", "3"))
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")

    try:
        persona = json.loads(config.get("outreach_persona", "{}"))
    except json.JSONDecodeError:
        persona = {}

    examples_text = get_successful_examples()

    # Check daily limit
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

    # Get ready opportunities owned by SDR
    opportunities = supabase_request("GET", "opportunity", params={
        "select": "id,pipeline_type,company_id,role_id,signal_id,notes",
        "stage": "eq.ready_for_outreach",
        "owner": "eq.sdr",
        "order": "created_at.asc",
        "limit": "20",
    })

    if not opportunities:
        logger.info("  No ready opportunities for SDR")
        return results

    candidates = []
    for opp in opportunities:
        company_id = opp.get("company_id")
        if not company_id:
            continue

        # Check no existing outreach for this company
        existing = supabase_request("GET", "outreach", params={
            "company_id": f"eq.{company_id}",
            "select": "id",
            "limit": "1",
        })
        if existing and len(existing) > 0:
            continue

        # Find decision maker with email
        intel = gather_company_intel(company_id)
        dm = None
        # Sort contacts by decision_maker_score
        sorted_contacts = sorted(
            intel["contacts"],
            key=lambda c: c.get("contact", {}).get("decision_maker_score") or 0,
            reverse=True,
        )
        for link in sorted_contacts:
            if link.get("contact", {}).get("email"):
                dm = link["contact"]
                break

        if not dm:
            continue

        # Get company details
        company = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,industry,funding_stage,domain",
            "limit": "1",
        })

        candidates.append({
            "opp": opp,
            "company": company[0] if company else {},
            "dm": dm,
            "intel": intel,
        })

    if not candidates:
        logger.info("  No outreach-ready opportunities with contacts")
        return results

    logger.info(f"  {len(candidates)} candidates, processing {min(remaining, len(candidates))}")

    for cand in candidates[:remaining]:
        opp = cand["opp"]
        company = cand["company"]
        dm = cand["dm"]
        intel = cand["intel"]

        prompt = build_outreach_prompt(opp, company, dm, intel, examples_text, persona)
        text = claude_request(prompt, max_tokens=800, system=SDR_SOUL)
        if not text:
            continue

        try:
            email_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            logger.error(f"  JSON parse error for outreach to {company.get('name', '?')}")
            continue

        subject = email_data.get("subject", f"A-Line x {company.get('name', '?')}")
        body_html = email_data.get("body_html", "")
        if not body_html:
            continue

        outreach_status = "draft"
        sent_at = None
        resend_id = None

        if outreach_mode == "auto" and RESEND_API_KEY:
            resend_id = send_email(from_email, dm["email"], cc_email, subject, body_html)
            if resend_id:
                outreach_status = "sent"
                sent_at = datetime.now(timezone.utc).isoformat()
                results["emails_sent"] += 1
                logger.info(f"  SENT: {subject} -> {dm['email']}")
            else:
                outreach_status = "draft"
        else:
            results["drafts_created"] += 1
            logger.info(f"  DRAFT: {subject} -> {dm['email']}")

        outreach_record = supabase_request("POST", "outreach", data={
            "company_id": company.get("id"),
            "contact_id": dm["id"],
            "subject": subject,
            "body_html": body_html,
            "status": outreach_status,
            "sent_at": sent_at,
            "resend_email_id": resend_id,
            "direction": "outbound",
            "from_email": from_email,
        })

        if outreach_record and len(outreach_record) > 0:
            oid = outreach_record[0]["id"]
            supabase_request("PATCH", f"outreach?id=eq.{oid}", data={"thread_id": oid})

        # Update opportunity stage
        supabase_request("PATCH", f"opportunity?id=eq.{opp['id']}", data={
            "stage": "sdr_contacted",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        log_decision("outreach_" + outreach_status, "opportunity", opp["id"],
                      f"SDR {'sent' if outreach_status == 'sent' else 'drafted'} outreach to {dm['name']} — {subject}",
                      {"contact_email": dm["email"], "subject": subject, "agent": "sdr", "pipeline_type": opp.get("pipeline_type")})
        log_dossier(company.get("id"), "outreach",
                    f"SDR {'Sent' if outreach_status == 'sent' else 'Draft'}: {subject}",
                    f"To: {dm['name']} ({dm['email']})\n\n{body_html[:500]}")

        time.sleep(1)

    return results


# ═══════════════════════════════════════════════════════════
# REPLY HANDLER
# ═══════════════════════════════════════════════════════════

def classify_sentiment(text):
    if not text or not ANTHROPIC_KEY:
        return "neutral"
    prompt = """Klassifiziere diese Email-Antwort in eine Kategorie:
- "interested" — will mehr wissen, offen für Gespräch
- "positive" — freundlich, offen, aber noch kein konkretes Interesse
- "neutral" — unklar, Rückfragen
- "not_interested" — höfliche Absage, kein Bedarf
- "negative" — klare Absage, will nicht kontaktiert werden

Email-Antwort:
""" + text[:500] + """

Antworte NUR mit einem Wort."""

    result = claude_request(prompt, max_tokens=20, system=SDR_SOUL)
    if result:
        result = result.strip().lower().strip('"').strip("'")
        if result in ("interested", "positive", "neutral", "not_interested", "negative"):
            return result
    return "neutral"


def run_reply_handler(config):
    """Process new inbound replies, classify sentiment, auto-respond, handoff to AE."""
    results = {"replies_processed": 0, "followups_sent": 0, "handoffs": 0}

    max_followups = int(config.get("outreach_max_followups", "3"))
    outreach_mode = config.get("outreach_mode", "draft")
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")

    new_replies = supabase_request("GET", "outreach", params={
        "select": "id,thread_id,company_id,contact_id,subject,body_html,raw_text,from_email,created_at",
        "direction": "eq.inbound",
        "status": "eq.replied",
        "order": "created_at.asc",
        "limit": "20",
    })

    if not new_replies:
        return results

    logger.info(f"  {len(new_replies)} new replies to process")

    for reply in new_replies:
        thread_id = reply.get("thread_id")
        company_id = reply.get("company_id")
        contact_id = reply.get("contact_id")

        if not thread_id or not company_id:
            continue

        thread = supabase_request("GET", "outreach", params={
            "thread_id": f"eq.{thread_id}",
            "select": "id,direction,subject,body_html,raw_text,created_at,status",
            "order": "created_at.asc",
        })

        our_messages = [t for t in (thread or []) if t.get("direction") == "outbound"]
        if len(our_messages) >= max_followups:
            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "closed"})
            # Find opportunity and move to nurture
            opps = supabase_request("GET", "opportunity", params={
                "company_id": f"eq.{company_id}",
                "owner": "eq.sdr",
                "select": "id",
                "limit": "1",
            })
            if opps:
                supabase_request("PATCH", f"opportunity?id=eq.{opps[0]['id']}", data={
                    "stage": "closed_lost",
                    "notes": "Max follow-ups reached",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
            continue

        reply_text = reply.get("raw_text") or re.sub(r"<[^>]+>", "", reply.get("body_html", ""))
        sentiment = classify_sentiment(reply_text)
        supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"reply_sentiment": sentiment})

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

        results["replies_processed"] += 1

        # HANDOFF to AE on interested/positive
        if sentiment in ("interested", "positive"):
            logger.info(f"  HANDOFF: {company_id} -> AE (sentiment: {sentiment})")

            opps = supabase_request("GET", "opportunity", params={
                "company_id": f"eq.{company_id}",
                "owner": "eq.sdr",
                "select": "id",
                "limit": "1",
            })
            if opps:
                supabase_request("PATCH", f"opportunity?id=eq.{opps[0]['id']}", data={
                    "stage": "qualified",
                    "owner": "ae",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })

            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "handoff_ae"})
            results["handoffs"] += 1

            log_decision("sdr_handoff_ae", "company", company_id,
                         f"SDR -> AE handoff: reply sentiment '{sentiment}'",
                         {"sentiment": sentiment, "thread_id": thread_id, "agent": "sdr"})
            continue

        # NEGATIVE → close
        if sentiment == "negative":
            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "closed"})
            opps = supabase_request("GET", "opportunity", params={
                "company_id": f"eq.{company_id}",
                "owner": "eq.sdr",
                "select": "id",
                "limit": "1",
            })
            if opps:
                supabase_request("PATCH", f"opportunity?id=eq.{opps[0]['id']}", data={
                    "stage": "closed_lost",
                    "notes": "Negative reply",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
            continue

        # NEUTRAL / NOT_INTERESTED → follow up
        co = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}", "select": "id,name,industry,funding_stage", "limit": "1",
        })
        contact = supabase_request("GET", "contact", params={
            "id": f"eq.{contact_id}", "select": "id,name,title,email", "limit": "1",
        })

        if not co or not contact:
            continue

        company = co[0]
        dm = contact[0]

        conv_history = ""
        for msg in (thread or []):
            sender = "Niels (A-Line)" if msg.get("direction") == "outbound" else dm.get("name", "Kontakt")
            body = msg.get("raw_text") or re.sub(r"<[^>]+>", "", msg.get("body_html", ""))
            body = re.sub(r"\s+", " ", body).strip()
            conv_history += f"\n[{sender}]: {body[:500]}\n"

        sentiment_hint = "Höfliche Absage. Akzeptiere freundlich, halte die Tür offen. Kurz." if sentiment == "not_interested" else "Neutral/unklar. Beantworte Fragen, liefere Mehrwert, wiederhole CTA."

        prompt = f"""Bisherige Konversation mit {dm.get('name', '?')} ({dm.get('title', '?')}) von {company.get('name', '?')}:
{conv_history}

Sentiment: {sentiment}
{sentiment_hint}

Schreibe die nächste Antwort. Max 2-4 Sätze.
Unterschrift: Beste Grüße,
Niels

Antworte NUR in validem JSON:
{{"subject": "Re: ...", "body_html": "<p>Antwort HTML</p>"}}"""

        text = claude_request(prompt, max_tokens=600, system=SDR_SOUL)
        if not text:
            continue

        try:
            followup_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            continue

        subject = followup_data.get("subject", f"Re: {reply.get('subject', '')}")
        body_html = followup_data.get("body_html", "")
        if not body_html:
            continue

        followup_status = "draft"
        sent_at = None
        resend_id = None

        if outreach_mode == "auto" and RESEND_API_KEY and dm.get("email"):
            resend_id = send_email(from_email, dm["email"], cc_email, subject, body_html)
            if resend_id:
                followup_status = "sent"
                sent_at = datetime.now(timezone.utc).isoformat()
                results["followups_sent"] += 1

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

        supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "answered"})

        # Update opportunity stage
        opps = supabase_request("GET", "opportunity", params={
            "company_id": f"eq.{company_id}",
            "owner": "eq.sdr",
            "select": "id",
            "limit": "1",
        })
        if opps:
            supabase_request("PATCH", f"opportunity?id=eq.{opps[0]['id']}", data={
                "stage": "replied",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        time.sleep(1)

    return results


# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

def run(config=None):
    """Run all SDR agent tasks."""
    logger.info("\nSDR AGENT")
    results = {"drafts_created": 0, "emails_sent": 0, "replies_processed": 0, "followups_sent": 0, "handoffs": 0}

    if config is None:
        config = get_config()

    if config.get("outreach_mode") == "off":
        logger.info("  Outreach mode: OFF — SDR skipping")
        return results

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — SDR skipping")
        return results

    # Step 1: Handle replies first
    reply_results = run_reply_handler(config)
    results["replies_processed"] = reply_results["replies_processed"]
    results["followups_sent"] = reply_results["followups_sent"]
    results["handoffs"] = reply_results["handoffs"]

    # Step 2: New cold outreach
    outreach_results = run_cold_outreach(config)
    results["drafts_created"] = outreach_results["drafts_created"]
    results["emails_sent"] = outreach_results["emails_sent"]

    logger.info(f"  SDR Summary: {results['emails_sent']} sent, {results['drafts_created']} drafts, "
                f"{results['replies_processed']} replies, {results['followups_sent']} follow-ups, "
                f"{results['handoffs']} handoffs -> AE")
    return results


def main():
    run()


if __name__ == "__main__":
    main()
