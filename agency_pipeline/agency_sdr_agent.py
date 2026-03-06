#!/usr/bin/env python3
"""
A-Line Agency SDR Agent — Outreach to agency GFs.

Pitches: We have systematic deal-flow (open interim roles in DACH).
We are looking for pool partners. If they have a candidate and we
place them, they get 20% finder fee.

Uses Instantly.ai for email delivery (separate campaign from company outreach).

Usage: python -m agency_pipeline.agency_sdr_agent
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agency_sdr_agent")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "")
INSTANTLY_AGENCY_CAMPAIGN_ID = os.getenv("INSTANTLY_AGENCY_CAMPAIGN_ID", "")

MAX_EMAILS_PER_SEQUENCE = 4


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


def log_decision(action, entity_type, entity_id, reason, metadata=None):
    """Log agent decision."""
    supabase_request("POST", "agent_log", data={
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "reason": reason,
        "metadata": json.dumps(metadata) if metadata else None,
    })


# ═══════════════════════════════════════════════════════════
# EMAIL GENERATION
# ═══════════════════════════════════════════════════════════

AGENCY_SDR_SYSTEM = """Du bist Niels, Gründer von A-Line — einer DACH-fokussierten Plattform, die systematisch offene Interim- und Fractional-Executive-Rollen via automatisierter Market Intelligence findet.

Schreibe eine kurze, personalisierte deutsche Cold Email an einen Agentur-GF/Inhaber.
Sprache: Deutsch, Du-Form.
Ton: Peer-to-Peer, wie ein Gründer zum anderen.
Länge: max 5-6 Sätze.

Der Pitch: Wir haben systematischen Deal-Flow (offene Interim-Rollen im DACH-Raum, täglich gefunden via unserer Pipeline). Wir suchen Pool-Partner. Wenn sie einen Kandidaten haben und wir ihn platzieren, bekommen sie 20% Finder Fee. Wir teilen den Firmennamen erst bei gegenseitigem Interesse.

CTA: 15-Minuten-Call um Fit zu explorieren.
Signatur: "Beste Grüße,\\nNiels\\nA-Line | Interim & Fractional Executive Matching"

NICHT erwähnen: AI, Automatisierung, Scraping.
NICHT wie ein Template klingen. Klingen, als hätte Niels das persönlich geschrieben."""


def generate_agency_outreach_email(context):
    """Generate a personalized cold email to an agency GF.

    Args:
        context: dict with gf_name, agency_name, agency_specialization,
                 agency_hq_city, available_role_count.

    Returns:
        dict with {subject, body} or None.
    """
    spec = context.get("agency_specialization", [])
    spec_text = ", ".join(spec) if spec else "verschiedene Funktionsbereiche"

    prompt = f"""Write a cold email to {context.get('gf_name', 'den Geschäftsführer')} at {context.get('agency_name', 'die Agentur')}.

Context:
- Recipient: {context.get('gf_name', '?')} — GF/Inhaber von {context.get('agency_name', '?')}
- Their specialization: {spec_text}
- Their location: {context.get('agency_hq_city', 'DACH')}
- We currently have {context.get('available_role_count', 'mehrere')} offene Interim-Rollen im DACH-Raum die zu ihrem Profil passen könnten

Hook: Sei spezifisch — erwähne, dass wir aktuell {context.get('available_role_count', 'mehrere')} offene Interim-Rollen haben, die zu typischen {spec_text} Profilen passen.

Return ONLY a JSON object:
{{
  "subject": "email subject (short, specific, no emojis)",
  "body": "email body (plain text, use \\n for line breaks)"
}}"""

    text = claude_request(prompt, max_tokens=500, system=AGENCY_SDR_SYSTEM)
    if not text:
        return None

    try:
        return json.loads(clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"Email generation JSON error: {e}")
        return None


def generate_agency_followup(context, history):
    """Generate follow-up email with reasoning.

    Args:
        context: same as generate_agency_outreach_email
        history: list of previous outreach records

    Returns:
        dict with {subject, body, send, reasoning} or None.
    """
    history_text = ""
    for i, msg in enumerate(history, 1):
        date = msg.get("created_at", "?")[:10]
        history_text += f"\nEmail {i} ({date}):\n"
        history_text += f"Subject: {msg.get('subject', '?')}\n"
        body = msg.get("body", "")
        history_text += f"Body: {body[:300]}\n"

    step = len(history) + 1

    prompt = f"""Decide whether to send follow-up #{step} to {context.get('gf_name', '?')} at {context.get('agency_name', '?')}.

Previous emails:{history_text}

Follow-up strategy:
- Follow-up 1 (after 48h): New angle — mention a specific role type
- Follow-up 2 (after 5 days): Short — "Kurze Frage: habt ihr gerade Interim-Profile im Pool?"
- Follow-up 3 (after 10 days): Last chance — "Letzter Versuch" format
- After 3 follow-ups: STOP.

Language: German, Du-Form. Max 2-3 sentences. Signed as Niels.

Return ONLY a JSON object:
{{
  "send": true/false,
  "reasoning": "why send or not",
  "subject": "Re: [original subject]",
  "body": "follow-up body"
}}"""

    text = claude_request(prompt, max_tokens=400, system=AGENCY_SDR_SYSTEM)
    if not text:
        return None

    try:
        return json.loads(clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"Follow-up JSON error: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# ANONYMIZED ROLE BRIEF
# ═══════════════════════════════════════════════════════════

def generate_anonymized_role_brief(role):
    """Generate an anonymized role brief for sharing with agencies.

    NEVER includes company name, domain, or identifying information.

    Args:
        role: dict from role table with title, location, engagement_type, etc.

    Returns:
        str — anonymized brief text.
    """
    title = role.get("title", "Interim Executive")
    location = role.get("location", "DACH")
    engagement = role.get("engagement_type", "interim")
    brief_data = role.get("sourcing_brief")

    # Parse sourcing brief if available
    if isinstance(brief_data, str):
        try:
            brief_data = json.loads(brief_data)
        except json.JSONDecodeError:
            brief_data = None

    parts = []

    # Role function (generalize the title)
    parts.append(title.split(" at ")[0].split(" bei ")[0].strip())

    # Location (city only, no company)
    city = location.split(",")[0].strip() if location else "DACH"
    parts.append(city)

    # Engagement type
    if engagement:
        parts.append(engagement.capitalize())

    # Key requirements from sourcing brief
    if brief_data:
        must_have = brief_data.get("must_have", [])[:3]
        if must_have:
            parts.append("Key: " + "; ".join(must_have))

        seniority = brief_data.get("seniority")
        if seniority:
            parts.append(f"Level: {seniority}")

    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════
# INSTANTLY INTEGRATION
# ═══════════════════════════════════════════════════════════

def _instantly_create_lead(contact, campaign_id):
    """Add a lead to Instantly campaign."""
    if not INSTANTLY_API_KEY:
        return None

    try:
        import httpx
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.instantly.ai/api/v2/leads",
                headers={
                    "Authorization": f"Bearer {INSTANTLY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "campaign_id": campaign_id,
                    "email": contact["email"],
                    "first_name": contact.get("first_name", ""),
                    "last_name": contact.get("last_name", ""),
                    "company_name": contact.get("company_name", ""),
                },
            )
            if resp.status_code >= 400:
                logger.error(f"Instantly create lead: {resp.status_code} — {resp.text[:200]}")
                return None
            return resp.json()
    except Exception as e:
        logger.error(f"Instantly error: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# OUTREACH PIPELINE
# ═══════════════════════════════════════════════════════════

def run_agency_outreach_pipeline():
    """Main daily entry point for agency outreach.

    1. Find agencies ready for outreach (enriched, not competitor, pending)
    2. Generate + send initial emails
    3. Process follow-ups for existing sequences
    """
    logger.info("=" * 60)
    logger.info("Agency Outreach Pipeline — Starting")
    logger.info("=" * 60)

    if not INSTANTLY_AGENCY_CAMPAIGN_ID:
        logger.info("No INSTANTLY_AGENCY_CAMPAIGN_ID — skipping agency outreach")
        return {"emails_sent": 0, "follow_ups": 0}

    stats = {"emails_sent": 0, "follow_ups": 0, "skipped": 0}

    # Count available HOT roles for pitch
    hot_roles = supabase_request("GET", "role", params={
        "select": "id,title,engagement_type,location,sourcing_brief",
        "tier": "eq.hot",
        "status": "eq.active",
        "limit": "100",
    })
    hot_role_count = len(hot_roles or [])

    # ── 1. Initial outreach ──
    agencies = supabase_request("GET", "agency", params={
        "select": "id,name,domain,hq_city,specialization,is_direct_competitor",
        "enrichment_status": "eq.enriched",
        "is_direct_competitor": "eq.false",
        "outreach_status": "eq.pending",
        "order": "quality_score.desc.nullslast",
        "limit": "10",
    })

    for agency in (agencies or []):
        # Double-check competitor flag
        if agency.get("is_direct_competitor"):
            logger.info(f"  Skipping competitor: {agency['name']}")
            continue

        # Find contact with confidence != low
        contacts = supabase_request("GET", "agency_contact", params={
            "agency_id": f"eq.{agency['id']}",
            "confidence": "not.eq.low",
            "select": "id,name,title,email,linkedin_url",
            "limit": "1",
        })
        if not contacts:
            stats["skipped"] += 1
            continue

        contact = contacts[0]
        if not contact.get("email"):
            logger.info(f"  Skipping {agency['name']}: no email for {contact.get('name', '?')}")
            stats["skipped"] += 1
            continue

        # Generate email
        first_name = contact["name"].split()[0] if contact.get("name") else "?"
        email_context = {
            "gf_name": first_name,
            "agency_name": agency["name"],
            "agency_specialization": agency.get("specialization", []),
            "agency_hq_city": agency.get("hq_city", "DACH"),
            "available_role_count": hot_role_count,
        }

        email = generate_agency_outreach_email(email_context)
        if not email:
            logger.error(f"  Failed to generate email for {agency['name']}")
            continue

        # Add to Instantly
        name_parts = contact["name"].split() if contact.get("name") else [""]
        instantly_result = _instantly_create_lead(
            {
                "email": contact["email"],
                "first_name": name_parts[0],
                "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
                "company_name": agency["name"],
            },
            INSTANTLY_AGENCY_CAMPAIGN_ID,
        )
        instantly_lead_id = instantly_result.get("id") if instantly_result else None

        # Write outreach record
        outreach_rec = supabase_request("POST", "agency_outreach", data={
            "agency_id": agency["id"],
            "agency_contact_id": contact["id"],
            "direction": "outbound",
            "sequence_step": 1,
            "subject": email["subject"],
            "body": email["body"],
            "status": "sent",
            "instantly_lead_id": instantly_lead_id,
            "sender_name": "Niels",
            "sender_email": "niels@arteq.app",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

        if outreach_rec:
            rec = outreach_rec[0] if isinstance(outreach_rec, list) else outreach_rec
            supabase_request("PATCH", f"agency_outreach?id=eq.{rec['id']}", data={
                "thread_id": rec["id"],
            })

        # Update agency status
        supabase_request("PATCH", f"agency?id=eq.{agency['id']}", data={
            "outreach_status": "contacted",
        })

        log_decision("agency_outreach_sent", "agency", agency["id"],
                      f"Initial email sent to {contact['name']} at {agency['name']}",
                      {"contact_email": contact["email"]})

        logger.info(f"  Sent: {agency['name']} → {contact['name']} ({contact['email']})")
        stats["emails_sent"] += 1
        time.sleep(1)

    # ── 2. Follow-ups ──
    open_threads = supabase_request("GET", "agency_outreach", params={
        "select": "id,agency_id,agency_contact_id,subject,body,status,created_at,thread_id,sequence_step",
        "status": "eq.sent",
        "direction": "eq.outbound",
        "got_reply": "eq.false",
        "order": "created_at.asc",
        "limit": "20",
    })

    threads = {}
    for msg in (open_threads or []):
        tid = msg.get("thread_id") or msg["id"]
        if tid not in threads:
            threads[tid] = []
        threads[tid].append(msg)

    for thread_id, messages in threads.items():
        latest = messages[-1]
        step = latest.get("sequence_step", 1)

        # Hard guardrail: max emails
        if step >= MAX_EMAILS_PER_SEQUENCE:
            logger.info(f"  Agency thread {thread_id}: max emails reached, closing")
            for msg in messages:
                supabase_request("PATCH", f"agency_outreach?id=eq.{msg['id']}", data={"status": "closed"})
            continue

        # Check timing
        last_sent = datetime.fromisoformat(latest["created_at"].replace("Z", "+00:00"))
        days_since = (datetime.now(timezone.utc) - last_sent).days
        required_days = {1: 2, 2: 5, 3: 10}.get(step, 5)
        if days_since < required_days:
            continue

        # Get agency + contact for context
        agency_rows = supabase_request("GET", "agency", params={
            "id": f"eq.{latest['agency_id']}",
            "select": "id,name,specialization,hq_city",
            "limit": "1",
        })
        agency = agency_rows[0] if agency_rows else {"name": "Unknown"}

        contact_rows = supabase_request("GET", "agency_contact", params={
            "id": f"eq.{latest['agency_contact_id']}",
            "select": "id,name,email",
            "limit": "1",
        })
        contact = contact_rows[0] if contact_rows else {}

        first_name = contact.get("name", "?").split()[0] if contact.get("name") else "?"
        context = {
            "gf_name": first_name,
            "agency_name": agency.get("name", ""),
            "agency_specialization": agency.get("specialization", []),
            "agency_hq_city": agency.get("hq_city", ""),
            "available_role_count": hot_role_count,
        }

        followup = generate_agency_followup(context, messages)
        if not followup or not followup.get("send", False):
            reason = followup.get("reasoning", "agent decided not to follow up") if followup else "no response from Claude"
            logger.info(f"  Agency thread {thread_id}: no follow-up — {reason}")
            for msg in messages:
                supabase_request("PATCH", f"agency_outreach?id=eq.{msg['id']}", data={"status": "closed"})
            continue

        # Send follow-up
        supabase_request("POST", "agency_outreach", data={
            "agency_id": latest["agency_id"],
            "agency_contact_id": latest["agency_contact_id"],
            "direction": "outbound",
            "thread_id": thread_id,
            "in_reply_to": latest["id"],
            "sequence_step": step + 1,
            "subject": followup.get("subject", f"Re: {latest.get('subject', '')}"),
            "body": followup.get("body", ""),
            "status": "sent",
            "sender_name": "Niels",
            "sender_email": "niels@arteq.app",
            "follow_up_reasoning": followup.get("reasoning", ""),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(f"  Agency follow-up #{step + 1}: {agency.get('name', '?')}")
        stats["follow_ups"] += 1
        time.sleep(1)

    logger.info(f"Agency outreach done: {stats['emails_sent']} initial, {stats['follow_ups']} follow-ups")
    return stats


# ═══════════════════════════════════════════════════════════
# REPLY HANDLING
# ═══════════════════════════════════════════════════════════

def check_agency_replies():
    """Check for agency replies and classify sentiment."""
    logger.info("Checking agency replies...")

    # Find inbound replies that haven't been processed
    inbound = supabase_request("GET", "agency_outreach", params={
        "select": "id,agency_id,agency_contact_id,raw_reply_text,reply_sentiment",
        "direction": "eq.inbound",
        "reply_sentiment": "is.null",
        "limit": "20",
    })

    if not inbound:
        logger.info("  No unprocessed agency replies")
        return {"processed": 0}

    processed = 0
    for reply in inbound:
        text = reply.get("raw_reply_text", "")
        if not text:
            continue

        # Classify sentiment
        sentiment_prompt = f"""Classify this reply sentiment in one word.

Reply: {text[:500]}

Options: interested, positive, neutral, not_interested, negative
Return ONLY one word."""

        result = claude_request(sentiment_prompt, max_tokens=20)
        sentiment = "neutral"
        if result:
            result = result.strip().lower().replace('"', '')
            valid = {"interested", "positive", "neutral", "not_interested", "negative"}
            if result in valid:
                sentiment = result

        supabase_request("PATCH", f"agency_outreach?id=eq.{reply['id']}", data={
            "reply_sentiment": sentiment,
        })

        # If positive → mark agency as partner
        if sentiment in ("interested", "positive"):
            supabase_request("PATCH", f"agency?id=eq.{reply['agency_id']}", data={
                "outreach_status": "partner",
                "partner_since": datetime.now(timezone.utc).isoformat(),
            })
            log_decision("agency_partner", "agency", reply["agency_id"],
                          f"Agency showed interest — marking as partner",
                          {"sentiment": sentiment})
            logger.info(f"  New partner! Agency {reply['agency_id']}")

        elif sentiment in ("not_interested", "negative"):
            supabase_request("PATCH", f"agency?id=eq.{reply['agency_id']}", data={
                "outreach_status": "declined",
            })

        processed += 1

    return {"processed": processed}


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run():
    """Run the full agency SDR pipeline."""
    logger.info("=" * 60)
    logger.info("A-Line Agency SDR Agent — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    outreach_stats = run_agency_outreach_pipeline()
    reply_stats = check_agency_replies()

    logger.info("=" * 60)
    logger.info(f"AGENCY SDR SUMMARY: {outreach_stats}, replies: {reply_stats}")
    logger.info("=" * 60)

    return {**outreach_stats, **reply_stats}


if __name__ == "__main__":
    run()
