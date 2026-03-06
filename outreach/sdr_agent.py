#!/usr/bin/env python3
"""
A-Line SDR Agent (Instantly.ai) — Email outreach orchestration.

Replaces the Resend-based pipeline with Instantly.ai for:
  - Lead creation + email sequencing
  - Open/bounce tracking
  - Reply handling + sentiment classification
  - Follow-up reasoning

Usage: python -m outreach.sdr_agent
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from outreach.instantly_client import create_lead, get_lead_status, list_replies, pause_lead
from outreach.email_writer import generate_initial_email, generate_followup_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("outreach.sdr_agent")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
INSTANTLY_CAMPAIGN_ID = os.getenv("INSTANTLY_CAMPAIGN_ID", "")

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


def claude_request(prompt, max_tokens=300, system=None):
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


def log_decision(action, entity_type, entity_id, reason, metadata=None):
    """Log agent decision to agent_log table."""
    supabase_request("POST", "agent_log", data={
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "reason": reason,
        "metadata": json.dumps(metadata) if metadata else None,
    })


# ═══════════════════════════════════════════════════════════
# OUTREACH PIPELINE
# ═══════════════════════════════════════════════════════════

def run_outreach_pipeline():
    """Daily entry point: send initial emails + follow-ups via Instantly."""
    logger.info("=" * 60)
    logger.info("Outreach Pipeline — Starting")
    logger.info("=" * 60)

    if not INSTANTLY_CAMPAIGN_ID:
        logger.error("Missing INSTANTLY_CAMPAIGN_ID — skipping outreach")
        return {"emails_sent": 0, "follow_ups": 0}

    stats = {"emails_sent": 0, "follow_ups": 0, "skipped": 0}

    # ── 1. Initial outreach for new HOT roles ──
    # Find roles with score >= 70, hiring manager identified, not yet contacted, at least 1 day old
    one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    hot_roles = supabase_request("GET", "role", params={
        "select": "id,title,company_id,engagement_type,source_url,hiring_manager_name,hiring_manager_title,sourcing_brief,created_at",
        "enrichment_status": "eq.complete",
        "status": "eq.active",
        "tier": "eq.hot",
        "created_at": f"lt.{one_day_ago}",
        "order": "created_at.desc",
        "limit": "10",
    })

    for role in (hot_roles or []):
        # Check if already contacted for this role
        existing = supabase_request("GET", "outreach", params={
            "company_id": f"eq.{role['company_id']}",
            "direction": "eq.outbound",
            "select": "id",
            "limit": "1",
        })
        if existing:
            continue

        # Find contact with email (decision maker at this company)
        contacts = supabase_request("GET", "contact", params={
            "company_id": f"eq.{role['company_id']}",
            "select": "id,first_name,last_name,name,email,title",
            "email": "not.is.null",
            "is_primary": "eq.true",
            "limit": "1",
        })
        if not contacts:
            # Try any contact with email
            contacts = supabase_request("GET", "contact", params={
                "company_id": f"eq.{role['company_id']}",
                "select": "id,first_name,last_name,name,email,title",
                "email": "not.is.null",
                "limit": "1",
            })
        if not contacts:
            logger.info(f"  Skipping {role['title']}: no contact with email")
            stats["skipped"] += 1
            continue

        contact = contacts[0]
        contact_name = contact.get("name") or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()

        # Fetch company
        company_rows = supabase_request("GET", "company", params={
            "id": f"eq.{role['company_id']}",
            "select": "id,name,description,headcount,industry",
            "limit": "1",
        })
        company = company_rows[0] if company_rows else {"name": "Unknown"}

        # Generate email
        email_context = {
            "company_name": company.get("name", ""),
            "contact_name": contact_name,
            "contact_title": contact.get("title", ""),
            "role_title": role.get("title", ""),
            "company_description": company.get("description", ""),
            "engagement_type": role.get("engagement_type", ""),
            "hiring_manager_name": role.get("hiring_manager_name", ""),
        }

        email = generate_initial_email(email_context)
        if not email:
            logger.error(f"  Failed to generate email for {role['title']}")
            continue

        # Add lead to Instantly
        try:
            lead_data = create_lead(
                {
                    "email": contact["email"],
                    "first_name": contact.get("first_name", ""),
                    "last_name": contact.get("last_name", ""),
                    "company_name": company.get("name", ""),
                    "title": contact.get("title", ""),
                    "role_title": role.get("title", ""),
                },
                INSTANTLY_CAMPAIGN_ID,
            )
        except Exception as e:
            logger.error(f"  Instantly lead creation failed: {e}")
            continue

        instantly_lead_id = lead_data.get("id") if lead_data else None

        # Write outreach record
        outreach_record = supabase_request("POST", "outreach", data={
            "company_id": role["company_id"],
            "contact_id": contact["id"],
            "subject": email["subject"],
            "body_html": email["body"],
            "status": "sent",
            "direction": "outbound",
            "from_email": "lena@arteq.app",
            "sender_name": "Lena",
            "sender_email": "lena@arteq.app",
            "instantly_lead_id": instantly_lead_id,
            "sequence_step": 1,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

        if outreach_record:
            # Set thread_id to own id
            rec = outreach_record[0] if isinstance(outreach_record, list) else outreach_record
            supabase_request("PATCH", f"outreach?id=eq.{rec['id']}", data={
                "thread_id": rec["id"],
            })

        log_decision("outreach_sent", "role", role["id"],
                      f"Initial email sent to {contact_name} for {role['title']} via Instantly",
                      {"contact_email": contact["email"], "instantly_lead_id": instantly_lead_id})

        logger.info(f"  Sent initial email: {role['title']} → {contact_name} ({contact['email']})")
        stats["emails_sent"] += 1
        time.sleep(1)

    # ── 2. Follow-ups for existing sequences ──
    open_sequences = supabase_request("GET", "outreach", params={
        "select": "id,company_id,contact_id,subject,body_html,status,created_at,thread_id,sequence_step,instantly_lead_id",
        "status": "eq.sent",
        "direction": "eq.outbound",
        "got_reply": "eq.false",
        "order": "created_at.asc",
        "limit": "20",
    })

    # Group by thread_id → find threads needing follow-up
    threads = {}
    for msg in (open_sequences or []):
        tid = msg.get("thread_id") or msg["id"]
        if tid not in threads:
            threads[tid] = []
        threads[tid].append(msg)

    for thread_id, messages in threads.items():
        latest = messages[-1]
        step = latest.get("sequence_step", 1)

        # Enforce max emails guardrail
        if step >= MAX_EMAILS_PER_SEQUENCE:
            logger.info(f"  Thread {thread_id}: max emails reached ({step}), closing")
            for msg in messages:
                supabase_request("PATCH", f"outreach?id=eq.{msg['id']}", data={"status": "closed"})
            continue

        # Check if enough time has passed for follow-up
        last_sent = datetime.fromisoformat(latest["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_since = (now - last_sent).days

        follow_up_delay = {1: 2, 2: 5, 3: 10}  # step → days to wait
        required_days = follow_up_delay.get(step, 5)
        if days_since < required_days:
            continue

        # Check Instantly for opens/bounces
        if latest.get("instantly_lead_id"):
            try:
                lead_status = get_lead_status(latest.get("sender_email", ""))
                if lead_status:
                    # Update tracking
                    opened = lead_status.get("opened", False)
                    times_opened = lead_status.get("times_opened", 0)
                    bounced = lead_status.get("bounced", False)
                    supabase_request("PATCH", f"outreach?id=eq.{latest['id']}", data={
                        "email_opened": opened,
                        "times_opened": times_opened,
                        "bounced": bounced,
                    })
                    if bounced:
                        logger.info(f"  Thread {thread_id}: bounced, closing")
                        supabase_request("PATCH", f"outreach?id=eq.{latest['id']}", data={"status": "bounced"})
                        continue
            except Exception as e:
                logger.warning(f"  Could not check Instantly status: {e}")

        # Fetch company and contact for follow-up context
        company_rows = supabase_request("GET", "company", params={
            "id": f"eq.{latest['company_id']}",
            "select": "id,name,description",
            "limit": "1",
        })
        company = company_rows[0] if company_rows else {"name": "Unknown"}

        contact_rows = supabase_request("GET", "contact", params={
            "id": f"eq.{latest['contact_id']}",
            "select": "id,name,first_name,last_name,email,title",
            "limit": "1",
        })
        contact = contact_rows[0] if contact_rows else {}
        contact_name = contact.get("name") or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()

        # Ask Claude whether to follow up
        context = {
            "company_name": company.get("name", ""),
            "contact_name": contact_name,
            "contact_title": contact.get("title", ""),
        }

        followup = generate_followup_email(context, messages)
        if not followup:
            continue

        if not followup.get("send", False):
            logger.info(f"  Thread {thread_id}: agent says don't follow up — {followup.get('reasoning', '')}")
            supabase_request("PATCH", f"outreach?id=eq.{latest['id']}", data={
                "follow_up_reasoning": followup.get("reasoning", ""),
            })
            # Close the sequence if agent says stop
            for msg in messages:
                supabase_request("PATCH", f"outreach?id=eq.{msg['id']}", data={"status": "closed"})
            continue

        # Write follow-up outreach record
        supabase_request("POST", "outreach", data={
            "company_id": latest["company_id"],
            "contact_id": latest["contact_id"],
            "subject": followup.get("subject", f"Re: {latest.get('subject', '')}"),
            "body_html": followup.get("body", ""),
            "status": "sent",
            "direction": "outbound",
            "thread_id": thread_id,
            "in_reply_to": latest["id"],
            "from_email": "lena@arteq.app",
            "sender_name": "Lena",
            "sender_email": "lena@arteq.app",
            "sequence_step": step + 1,
            "follow_up_reasoning": followup.get("reasoning", ""),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

        log_decision("outreach_followup", "outreach", thread_id,
                      f"Follow-up #{step + 1} sent to {contact_name}: {followup.get('reasoning', '')}",
                      {"step": step + 1})

        logger.info(f"  Follow-up #{step + 1} sent: {contact_name} ({followup.get('reasoning', '')[:60]})")
        stats["follow_ups"] += 1
        time.sleep(1)

    logger.info(f"Outreach pipeline done: {stats['emails_sent']} initial, {stats['follow_ups']} follow-ups, {stats['skipped']} skipped")
    return stats


# ═══════════════════════════════════════════════════════════
# REPLY HANDLING
# ═══════════════════════════════════════════════════════════

def classify_sentiment(text):
    """Classify reply sentiment using Claude."""
    prompt = f"""Classify the sentiment of this email reply in one word.

Reply text:
{text[:1000]}

Options: interested, positive, neutral, not_interested, negative

Return ONLY one of these five words, nothing else."""

    result = claude_request(prompt, max_tokens=20)
    if result:
        result = result.strip().lower().replace('"', '').replace("'", "")
        valid = {"interested", "positive", "neutral", "not_interested", "negative"}
        if result in valid:
            return result
    return "neutral"


def check_replies():
    """Poll Instantly for new replies and process them."""
    logger.info("Checking for new replies...")

    if not INSTANTLY_CAMPAIGN_ID:
        logger.info("  No campaign ID — skipping reply check")
        return {"replies_processed": 0, "handoffs": 0}

    stats = {"replies_processed": 0, "handoffs": 0}

    # Get replies from Instantly
    since = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    try:
        replies = list_replies(INSTANTLY_CAMPAIGN_ID, since=since)
    except Exception as e:
        logger.error(f"  Failed to fetch replies: {e}")
        return stats

    if not replies:
        logger.info("  No new replies")
        return stats

    for reply in (replies if isinstance(replies, list) else []):
        email = reply.get("from_email") or reply.get("email", "")
        reply_text = reply.get("body", "") or reply.get("text", "")

        if not email or not reply_text:
            continue

        # Find matching outreach record
        existing = supabase_request("GET", "outreach", params={
            "select": "id,company_id,contact_id,thread_id,status",
            "direction": "eq.outbound",
            "order": "created_at.desc",
            "limit": "1",
        })

        # Also try to match by contact email
        contact = supabase_request("GET", "contact", params={
            "email": f"eq.{email}",
            "select": "id,company_id,name",
            "limit": "1",
        })

        if not contact:
            logger.info(f"  Reply from unknown email: {email}")
            continue

        contact = contact[0]

        # Check if we already recorded this reply
        existing_reply = supabase_request("GET", "outreach", params={
            "contact_id": f"eq.{contact['id']}",
            "direction": "eq.inbound",
            "raw_text": f"eq.{reply_text[:100]}",
            "select": "id",
            "limit": "1",
        })
        if existing_reply:
            continue

        # Find the thread
        thread_msg = supabase_request("GET", "outreach", params={
            "contact_id": f"eq.{contact['id']}",
            "direction": "eq.outbound",
            "order": "created_at.desc",
            "select": "id,thread_id,company_id",
            "limit": "1",
        })

        if not thread_msg:
            continue

        thread_msg = thread_msg[0]
        thread_id = thread_msg.get("thread_id") or thread_msg["id"]

        # Classify sentiment
        sentiment = classify_sentiment(reply_text)

        # Record inbound reply
        supabase_request("POST", "outreach", data={
            "company_id": thread_msg["company_id"],
            "contact_id": contact["id"],
            "subject": f"Re: reply from {contact.get('name', email)}",
            "body_html": "",
            "raw_text": reply_text,
            "status": "replied",
            "direction": "inbound",
            "thread_id": thread_id,
            "in_reply_to": thread_msg["id"],
            "reply_sentiment": sentiment,
            "got_reply": True,
        })

        # Update original outreach
        supabase_request("PATCH", f"outreach?thread_id=eq.{thread_id}&direction=eq.outbound", data={
            "got_reply": True,
            "reply_sentiment": sentiment,
        })

        # Pause lead in Instantly
        try:
            pause_lead(email, INSTANTLY_CAMPAIGN_ID)
        except Exception as e:
            logger.warning(f"  Could not pause lead: {e}")

        logger.info(f"  Reply from {contact.get('name', email)}: sentiment={sentiment}")
        stats["replies_processed"] += 1

        # Handle based on sentiment
        if sentiment in ("interested", "positive"):
            # Escalate to AE — set flag
            supabase_request("PATCH", f"outreach?thread_id=eq.{thread_id}", data={
                "status": "handoff_ae",
            })
            log_decision("sdr_handoff_ae", "contact", contact["id"],
                          f"Positive reply from {contact.get('name', email)} — handing off to AE",
                          {"sentiment": sentiment})
            logger.info(f"  Handoff to AE: {contact.get('name', email)}")
            stats["handoffs"] += 1

        elif sentiment in ("not_interested", "negative"):
            # Close sequence
            supabase_request("PATCH", f"outreach?thread_id=eq.{thread_id}", data={
                "status": "closed",
            })
            log_decision("outreach_closed", "contact", contact["id"],
                          f"Negative reply from {contact.get('name', email)} — closing sequence",
                          {"sentiment": sentiment})
            logger.info(f"  Sequence closed: {contact.get('name', email)} ({sentiment})")

        time.sleep(0.5)

    return stats


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run():
    """Main entry point: run outreach pipeline + check replies."""
    logger.info("=" * 60)
    logger.info("A-Line SDR Agent (Instantly) — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return {"emails_sent": 0, "follow_ups": 0, "replies_processed": 0, "handoffs": 0}

    # Run outreach
    outreach_stats = run_outreach_pipeline()

    # Check replies
    reply_stats = check_replies()

    combined = {**outreach_stats, **reply_stats}

    logger.info("=" * 60)
    logger.info(f"SDR AGENT SUMMARY: {combined}")
    logger.info("=" * 60)

    return combined


if __name__ == "__main__":
    run()
