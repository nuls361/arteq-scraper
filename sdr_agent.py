#!/usr/bin/env python3
"""
Arteq SDR Agent — Top of Funnel.

Handles:
  - Cold outreach to new prospects
  - Follow-up sequences
  - Reply handling & sentiment classification
  - Auto-handoff to AE when "interested" reply detected

Called by orchestrator.py as Phase 4.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger("sdr_agent")

# Import shared helpers from orchestrator
from orchestrator import (
    ANTHROPIC_KEY,
    RESEND_API_KEY,
    claude_request,
    clean_json_response,
    gather_company_intel,
    log_decision,
    log_dossier,
    supabase_request,
)


def load_soul():
    """Load SDR soul file."""
    path = os.path.join(os.path.dirname(__file__), "agent_soul_sdr.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


SDR_SOUL = load_soul()


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def get_persona(config):
    """Load outreach persona from config."""
    try:
        return json.loads(config.get("outreach_persona", "{}"))
    except json.JSONDecodeError:
        return {}


def get_successful_examples():
    """Load outreach emails that got positive replies — few-shot learning."""
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
        body = re.sub(r"<[^>]+>", "", ex.get("body_html", ""))
        body = re.sub(r"\s+", " ", body).strip()
        example_text += f"\nBeispiel {i}:\nBetreff: {ex.get('subject', '')}\nText: {body[:300]}\n"

    example_text += "\n--- ENDE BEISPIELE ---\nOrientiere dich am Stil dieser erfolgreichen Emails.\n"
    return example_text


def send_email(from_email, to_email, cc_email, subject, body_html):
    """Send email via Resend. Returns resend_id or None."""
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


def classify_sentiment(text):
    """Classify reply sentiment using Claude."""
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


# ═══════════════════════════════════════════════════════════
# COLD OUTREACH — New prospects
# ═══════════════════════════════════════════════════════════

def run_cold_outreach(config):
    """Generate and send cold outreach to new prospects."""
    results = {"drafts_created": 0, "emails_sent": 0}

    outreach_mode = config.get("outreach_mode", "draft")
    daily_limit = int(config.get("outreach_daily_limit", "3"))
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")

    persona = get_persona(config)
    examples_text = get_successful_examples()

    if examples_text:
        logger.info("  📚 Loaded successful email examples for learning")

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

    # Find prospects — SDR only handles companies owned by SDR or unassigned
    companies = supabase_request("GET", "company", params={
        "select": "id,name,status,composite_score,outreach_priority,industry,funding_stage,domain",
        "status": "in.(active,prospect)",
        "composite_score": "gte.65",
        "is_agency": "eq.false",
        "agent_owner": "in.(sdr,)",
        "pipeline_stage": "in.(prospect,sdr_outreach)",
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
        logger.info("  No outreach-ready companies for SDR")
        return results

    logger.info(f"  {len(outreach_candidates)} candidates, processing {min(remaining, len(outreach_candidates))}")

    for cand in outreach_candidates[:remaining]:
        co = cand["company"]
        dm = cand["dm"]
        intel = gather_company_intel(co["id"])

        prompt = _build_outreach_prompt(persona, dm, co, intel, examples_text)
        text = claude_request(prompt, max_tokens=800, system=SDR_SOUL)
        if not text:
            continue

        try:
            email_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            logger.error(f"  JSON parse error for outreach to {co['name']}")
            continue

        subject = email_data.get("subject", f"Arteq x {co['name']}")
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
                logger.info(f"  📨 SENT: {subject} → {dm['email']}")
            else:
                outreach_status = "draft"
        else:
            results["drafts_created"] += 1
            logger.info(f"  📝 DRAFT: {subject} → {dm['email']}")

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

        if outreach_record and len(outreach_record) > 0:
            oid = outreach_record[0]["id"]
            supabase_request("PATCH", f"outreach?id=eq.{oid}", data={"thread_id": oid})

        # Update pipeline stage
        supabase_request("PATCH", f"company?id=eq.{co['id']}", data={
            "pipeline_stage": "sdr_outreach",
            "agent_owner": "sdr",
        })

        log_decision("outreach_" + outreach_status, "company", co["id"],
                      f"SDR {'sent' if outreach_status == 'sent' else 'drafted'} outreach to {dm['name']} — {subject}",
                      {"contact_email": dm["email"], "subject": subject, "agent": "sdr"})
        log_dossier(co["id"], "outreach",
                    f"SDR {'Sent' if outreach_status == 'sent' else 'Draft'}: {subject}",
                    f"To: {dm['name']} ({dm['email']})\n\n{body_html[:500]}")

        time.sleep(1)

    return results


# ═══════════════════════════════════════════════════════════
# REPLY HANDLER — Process inbound replies + auto-respond
# ═══════════════════════════════════════════════════════════

def run_reply_handler(config):
    """Process new inbound replies, classify sentiment, auto-respond, handoff to AE if needed."""
    results = {"replies_processed": 0, "followups_sent": 0, "handoffs": 0}

    max_followups = int(config.get("outreach_max_followups", "3"))
    outreach_mode = config.get("outreach_mode", "draft")
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")
    persona = get_persona(config)

    try:
        reply_style = json.loads(config.get("outreach_reply_style", "{}"))
    except json.JSONDecodeError:
        reply_style = {}

    # Find unprocessed inbound replies
    new_replies = supabase_request("GET", "outreach", params={
        "select": "id,thread_id,company_id,contact_id,subject,body_html,raw_text,from_email,created_at",
        "direction": "eq.inbound",
        "status": "eq.replied",
        "order": "created_at.asc",
        "limit": "20",
    })

    if not new_replies:
        return results

    logger.info(f"  💬 {len(new_replies)} new replies to process")

    for reply in new_replies:
        thread_id = reply.get("thread_id")
        company_id = reply.get("company_id")
        contact_id = reply.get("contact_id")

        if not thread_id or not company_id:
            continue

        # Load full thread
        thread = supabase_request("GET", "outreach", params={
            "thread_id": f"eq.{thread_id}",
            "select": "id,direction,subject,body_html,raw_text,created_at,status",
            "order": "created_at.asc",
        })

        our_messages = [t for t in (thread or []) if t.get("direction") == "outbound"]
        if len(our_messages) >= max_followups:
            logger.info(f"  Max follow-ups ({max_followups}) reached for thread {thread_id}")
            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "closed"})
            # Move to nurture
            supabase_request("PATCH", f"company?id=eq.{company_id}", data={
                "pipeline_stage": "nurture",
            })
            continue

        # Classify sentiment
        reply_text = reply.get("raw_text") or re.sub(r"<[^>]+>", "", reply.get("body_html", ""))
        sentiment = classify_sentiment(reply_text)
        supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"reply_sentiment": sentiment})

        # Mark original as got_reply
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

        # ── HANDOFF CHECK: interested/positive → AE takes over ──
        if sentiment in ("interested", "positive"):
            logger.info(f"  🤝 HANDOFF: {company_id} → AE (sentiment: {sentiment})")
            supabase_request("PATCH", f"company?id=eq.{company_id}", data={
                "pipeline_stage": "qualified",
                "agent_owner": "ae",
                "handoff_at": datetime.now(timezone.utc).isoformat(),
                "handoff_reason": f"auto: reply sentiment '{sentiment}'",
            })
            # Mark reply as handed off, AE will handle the response
            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "handoff_ae"})
            results["handoffs"] += 1

            log_decision("sdr_handoff_ae", "company", company_id,
                         f"SDR → AE handoff: reply sentiment '{sentiment}'",
                         {"sentiment": sentiment, "thread_id": thread_id, "agent": "sdr"})
            log_dossier(company_id, "agent_action",
                        f"SDR → AE Handoff",
                        f"Positive reply erhalten (sentiment: {sentiment}). Übergabe an AE Agent.")
            continue

        # ── NOT INTERESTED / NEGATIVE → close gracefully ──
        if sentiment == "negative":
            logger.info(f"  ✋ STOP: {company_id} — negative reply, closing thread")
            supabase_request("PATCH", f"outreach?id=eq.{reply['id']}", data={"status": "closed"})
            supabase_request("PATCH", f"company?id=eq.{company_id}", data={
                "pipeline_stage": "nurture",
            })
            log_dossier(company_id, "outreach", "Thread closed — negative reply",
                        f"Reply-Sentiment: {sentiment}. Kein weiterer Outreach.")
            continue

        # ── NEUTRAL / NOT_INTERESTED → SDR responds with new angle ──
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

        # Build conversation context
        conv_history = ""
        for msg in (thread or []):
            sender = "Niels (Arteq)" if msg.get("direction") == "outbound" else dm.get("name", "Kontakt")
            body = msg.get("raw_text") or re.sub(r"<[^>]+>", "", msg.get("body_html", ""))
            body = re.sub(r"\s+", " ", body).strip()
            conv_history += f"\n[{sender}]: {body[:500]}\n"

        reply_rules = "\n".join(f"  - {r}" for r in reply_style.get("rules", []))
        reply_signature = persona.get("signature", "Beste Grüße,\nNiels")
        dm_name = dm.get("name", "?")
        dm_title = dm.get("title", "?")
        co_name = company.get("name", "?")

        sentiment_hint = ""
        if sentiment == "not_interested":
            sentiment_hint = "Höfliche Absage. Akzeptiere freundlich, halte die Tür offen. Kurz."
        else:
            sentiment_hint = "Neutral/unklar. Beantworte Fragen, liefere Mehrwert, wiederhole CTA."

        prompt = f"""Bisherige Konversation mit {dm_name} ({dm_title}) von {co_name}:
{conv_history}

Sentiment: {sentiment}
{sentiment_hint}

Regeln für Replies:
{reply_rules}

Schreibe die nächste Antwort. Max 2-4 Sätze.
Unterschrift: {reply_signature}

Antworte NUR in validem JSON:
{{"subject": "Re: ...", "body_html": "<p>Antwort HTML</p>"}}"""

        text = claude_request(prompt, max_tokens=600, system=SDR_SOUL)
        if not text:
            continue

        try:
            followup_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            logger.error(f"  JSON parse error for reply to {dm_name}")
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
                logger.info(f"  💬 SDR REPLY: {subject} → {dm['email']}")

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

        # Update pipeline stage
        supabase_request("PATCH", f"company?id=eq.{company_id}", data={
            "pipeline_stage": "sdr_followup",
        })

        log_decision("outreach_reply", "company", company_id,
                     f"SDR reply to {dm_name} (sentiment: {sentiment}) — {subject}",
                     {"sentiment": sentiment, "thread_id": thread_id, "agent": "sdr"})

        time.sleep(1)

    return results


# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT (called by orchestrator)
# ═══════════════════════════════════════════════════════════

def run(config):
    """Run all SDR agent tasks. Returns combined results dict."""
    logger.info("\n📨 SDR AGENT")
    results = {"drafts_created": 0, "emails_sent": 0, "replies_processed": 0, "followups_sent": 0, "handoffs": 0}

    if config.get("outreach_mode") == "off":
        logger.info("  Outreach mode: OFF — SDR skipping")
        return results

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — SDR skipping")
        return results

    # Step 1: Handle replies first (may trigger handoffs)
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
                f"{results['handoffs']} handoffs → AE")
    return results


def _build_outreach_prompt(persona, dm, co, intel, examples_text):
    """Build the SDR outreach prompt with persona + learning."""
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

    dos = "\n".join(f"  - {d}" for d in persona.get("dos", []))
    donts = "\n".join(f"  - {d}" for d in persona.get("donts", []))
    value_props = "\n".join(f"  - {v}" for v in persona.get("value_props", []))
    first_name = dm["name"].split()[0] if dm.get("name") else "?"
    signature = persona.get("signature", "Beste Grüße,\nNiels")

    return f"""Kontext über die Company:
{context}
{examples_text}

DO:
{dos}

DON'T:
{donts}

Value Props:
{value_props}

Schreibe eine Cold Outreach-Email an {dm['name']} ({dm.get('title', '')}) bei {co['name']}.
Begrüßung: "Hi {first_name}"
Unterschrift: {signature}

Antworte NUR in validem JSON:
{{"subject": "Betreff", "body_html": "<p>Email HTML Body</p>"}}"""
