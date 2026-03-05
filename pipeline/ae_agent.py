#!/usr/bin/env python3
"""
A-Line AE Agent — Bottom of Funnel.

Handles:
  - First response to qualified leads (after SDR handoff)
  - Meeting preparation & briefing documents
  - Proposal drafts
  - Pipeline_type context in all outputs

Reads from opportunity table.

Usage: python -m pipeline.ae_agent (called by orchestrator)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ae_agent")

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


def claude_request(prompt, max_tokens=1500, system=None):
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
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_soul_ae.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


AE_SOUL = load_soul()


def gather_company_intel(company_id):
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
        "source": "ae_agent",
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
    result = supabase_request("GET", "agent_config", params={"select": "key,value"})
    return {r["key"]: r["value"] for r in (result or [])}


# ═══════════════════════════════════════════════════════════
# QUALIFIED LEAD RESPONSE
# ═══════════════════════════════════════════════════════════

def handle_new_qualifieds(config):
    """Respond to leads handed off from SDR via opportunity table."""
    results = {"responses_sent": 0}

    outreach_mode = config.get("outreach_mode", "draft")
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")

    # Get qualified opportunities owned by AE
    opportunities = supabase_request("GET", "opportunity", params={
        "select": "id,pipeline_type,company_id,role_id,signal_id,notes",
        "stage": "eq.qualified",
        "owner": "eq.ae",
        "order": "updated_at.asc",
        "limit": "10",
    })

    if not opportunities:
        return results

    logger.info(f"  {len(opportunities)} qualified leads to respond to")

    for opp in opportunities:
        company_id = opp.get("company_id")
        if not company_id:
            continue

        # Find the handoff reply
        handoff_replies = supabase_request("GET", "outreach", params={
            "company_id": f"eq.{company_id}",
            "direction": "eq.inbound",
            "status": "eq.handoff_ae",
            "select": "id,thread_id,contact_id,subject,body_html,raw_text,reply_sentiment,created_at",
            "order": "created_at.desc",
            "limit": "1",
        })

        if not handoff_replies:
            continue

        reply = handoff_replies[0]
        thread_id = reply.get("thread_id")
        contact_id = reply.get("contact_id")

        co = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,industry,funding_stage,domain",
            "limit": "1",
        })
        contact = supabase_request("GET", "contact", params={
            "id": f"eq.{contact_id}",
            "select": "id,name,title,email,linkedin_url",
            "limit": "1",
        })

        if not co or not contact:
            continue

        company = co[0]
        dm = contact[0]
        intel = gather_company_intel(company_id)

        # Load thread
        thread = supabase_request("GET", "outreach", params={
            "thread_id": f"eq.{thread_id}",
            "select": "id,direction,subject,body_html,raw_text,created_at",
            "order": "created_at.asc",
        }) or []

        conv_history = ""
        for msg in thread:
            sender = "Niels (A-Line)" if msg.get("direction") == "outbound" else dm.get("name", "Kontakt")
            body = msg.get("raw_text") or re.sub(r"<[^>]+>", "", msg.get("body_html", ""))
            body = re.sub(r"\s+", " ", body).strip()
            conv_history += f"\n[{sender}]: {body[:500]}\n"

        # Build context with pipeline_type awareness
        context = f"Company: {company['name']}\n"
        context += f"Industry: {company.get('industry', '?')} | Funding: {company.get('funding_stage', '?')}\n"
        context += f"Contact: {dm['name']} ({dm.get('title', '?')})\n"
        context += f"Pipeline: {opp.get('pipeline_type', '?')} — {opp.get('notes', '')}\n"

        if dm.get("linkedin_url"):
            context += f"LinkedIn: {dm['linkedin_url']}\n"

        if intel["roles"]:
            context += "Offene Rollen:\n"
            for r in intel["roles"][:5]:
                context += f"  - {r['title']} ({r.get('engagement_type', '?')}) {'HOT' if r.get('is_hot') else ''}\n"

        if intel["signals"]:
            context += "Signale:\n"
            for s in intel["signals"][:5]:
                context += f"  - [{s.get('type')}] {s.get('title', '')[:60]}\n"

        first_name = dm.get("name", "?").split()[0] if dm.get("name") else "?"

        prompt = f"""Du übernimmst diese Konversation vom SDR Agent. Die Person hat positives Interesse gezeigt.

Kontext:
{context}

Bisherige Konversation:
{conv_history}

Reply-Sentiment: {reply.get('reply_sentiment', 'interested')}

Deine Aufgabe:
- Nimm den Faden natürlich auf
- Geh tiefer auf ihr spezifisches Thema ein
- Schlage einen konkreten Termin vor (z.B. "nächste Woche Dienstag oder Donnerstag, 15 Minuten")
- Zeig dass du ihr Business verstehst
- Max 4-5 Sätze

Begrüßung: "Hi {first_name}"
Unterschrift: Beste Grüße,
Niels

Antworte NUR in validem JSON:
{{"subject": "Re: ...", "body_html": "<p>Antwort HTML</p>"}}"""

        text = claude_request(prompt, max_tokens=800, system=AE_SOUL)
        if not text:
            continue

        try:
            email_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            continue

        subject = email_data.get("subject", f"Re: {reply.get('subject', '')}")
        body_html = email_data.get("body_html", "")
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
                results["responses_sent"] += 1
                logger.info(f"  AE RESPONSE: {subject} -> {dm['email']}")

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

        # Update opportunity to meeting stage
        supabase_request("PATCH", f"opportunity?id=eq.{opp['id']}", data={
            "stage": "meeting",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        log_decision("ae_response", "opportunity", opp["id"],
                     f"AE responded to qualified lead {dm['name']} at {company['name']}",
                     {"thread_id": thread_id, "agent": "ae", "pipeline_type": opp.get("pipeline_type")})
        log_dossier(company_id, "outreach",
                    f"AE Response: {subject}",
                    f"Qualified lead response to {dm['name']}\n\n{body_html[:500]}")

        time.sleep(1)

    return results


# ═══════════════════════════════════════════════════════════
# MEETING PREP
# ═══════════════════════════════════════════════════════════

def generate_meeting_preps(config):
    """Generate meeting prep briefings for opportunities in meeting stage."""
    results = {"briefings_created": 0}

    opportunities = supabase_request("GET", "opportunity", params={
        "select": "id,pipeline_type,company_id,role_id,signal_id,notes,meeting_scheduled_at",
        "stage": "eq.meeting",
        "owner": "eq.ae",
        "meeting_scheduled_at": "not.is.null",
        "order": "meeting_scheduled_at.asc",
        "limit": "5",
    })

    if not opportunities:
        return results

    for opp in opportunities:
        company_id = opp.get("company_id")
        if not company_id:
            continue

        existing_prep = supabase_request("GET", "meeting_prep", params={
            "company_id": f"eq.{company_id}",
            "select": "id",
            "limit": "1",
        })
        if existing_prep and len(existing_prep) > 0:
            continue

        company = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,industry,funding_stage,domain",
            "limit": "1",
        })
        if not company:
            continue

        intel = gather_company_intel(company_id)

        context = f"Company: {company[0]['name']}\n"
        context += f"Pipeline: {opp.get('pipeline_type', '?')} — {opp.get('notes', '')}\n"
        context += f"Meeting: {opp.get('meeting_scheduled_at', '?')}\n\n"

        if intel["roles"]:
            context += "Offene Rollen:\n"
            for r in intel["roles"][:10]:
                context += f"  - {r['title']} ({r.get('engagement_type', '?')}) {'HOT' if r.get('is_hot') else ''}\n"

        if intel["signals"]:
            context += "\nSignale:\n"
            for s in intel["signals"][:10]:
                context += f"  - [{s.get('type')}] {s.get('title', '')[:60]}\n"

        if intel["contacts"]:
            context += "\nKontakte:\n"
            for c in intel["contacts"]:
                ci = c.get("contact", {})
                dm_marker = " DM" if c.get("is_decision_maker") else ""
                context += f"  - {ci.get('name', '?')} ({ci.get('title', '?')}){dm_marker}\n"

        outreach = supabase_request("GET", "outreach", params={
            "company_id": f"eq.{company_id}",
            "select": "direction,subject,body_html,raw_text,reply_sentiment,created_at",
            "order": "created_at.asc",
            "limit": "20",
        })
        if outreach:
            context += "\nKommunikation:\n"
            for msg in outreach:
                sender = "A-Line" if msg.get("direction") == "outbound" else "Kontakt"
                body = msg.get("raw_text") or re.sub(r"<[^>]+>", "", msg.get("body_html", ""))
                body = re.sub(r"\s+", " ", body).strip()
                context += f"  [{sender}]: {body[:200]}\n"

        prompt = f"""Erstelle ein Meeting-Briefing für Niels.

{context}

Das Briefing soll enthalten:
1. **Company Summary** — Was macht die Firma, wie groß, welche Phase?
2. **Stakeholder** — Wer sitzt vermutlich am Tisch?
3. **Hypothese** — Was ist vermutlich ihr Problem?
4. **A-Line-Fit** — Welcher Executive-Typ passt? Fractional oder Interim?
5. **Talking Points** — 3-4 gute Fragen
6. **Red Flags** — Was könnte dagegen sprechen?

Antworte in JSON:
{{
  "briefing_html": "<h2>Meeting Briefing: Company</h2><p>...</p>",
  "stakeholders": ["Name — Rolle — Key Info"],
  "hypotheses": ["Hypothese 1", "Hypothese 2"],
  "talking_points": ["Frage 1", "Frage 2", "Frage 3"],
  "red_flags": ["Red Flag 1"]
}}"""

        text = claude_request(prompt, max_tokens=2000, system=AE_SOUL)
        if not text:
            continue

        try:
            prep_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            continue

        supabase_request("POST", "meeting_prep", data={
            "company_id": company_id,
            "meeting_date": opp.get("meeting_scheduled_at"),
            "briefing_html": prep_data.get("briefing_html", ""),
            "stakeholders": prep_data.get("stakeholders", []),
            "hypotheses": prep_data.get("hypotheses", []),
            "talking_points": prep_data.get("talking_points", []),
            "red_flags": prep_data.get("red_flags", []),
            "status": "draft",
        })

        results["briefings_created"] += 1
        logger.info(f"  BRIEFING: {company[0]['name']}")

        log_decision("ae_meeting_prep", "opportunity", opp["id"],
                     f"AE created meeting briefing for {company[0]['name']}",
                     {"agent": "ae", "pipeline_type": opp.get("pipeline_type")})

    return results


# ═══════════════════════════════════════════════════════════
# PROPOSALS
# ═══════════════════════════════════════════════════════════

def generate_proposals(config):
    """Generate proposal drafts for opportunities in proposal stage."""
    results = {"proposals_created": 0}

    opportunities = supabase_request("GET", "opportunity", params={
        "select": "id,pipeline_type,company_id,role_id,signal_id,notes",
        "stage": "eq.proposal",
        "owner": "eq.ae",
        "proposal_status": "in.(,drafting)",
        "limit": "5",
    })

    if not opportunities:
        return results

    for opp in opportunities:
        company_id = opp.get("company_id")
        if not company_id:
            continue

        existing = supabase_request("GET", "proposal_draft", params={
            "company_id": f"eq.{company_id}",
            "status": "in.(draft,sent)",
            "select": "id",
            "limit": "1",
        })
        if existing and len(existing) > 0:
            continue

        company = supabase_request("GET", "company", params={
            "id": f"eq.{company_id}",
            "select": "id,name,industry,funding_stage,domain",
            "limit": "1",
        })
        if not company:
            continue

        intel = gather_company_intel(company_id)

        dm = None
        for c in intel["contacts"]:
            if c.get("is_decision_maker") and c.get("contact", {}).get("email"):
                dm = c["contact"]
                break
        if not dm and intel["contacts"]:
            dm = intel["contacts"][0].get("contact", {})

        context = f"Company: {company[0]['name']}\n"
        context += f"Pipeline: {opp.get('pipeline_type', '?')} — {opp.get('notes', '')}\n"
        context += f"Industry: {company[0].get('industry', '?')} | Funding: {company[0].get('funding_stage', '?')}\n"

        if intel["roles"]:
            context += "Aktive Rollen:\n"
            for r in intel["roles"][:5]:
                context += f"  - {r['title']} ({r.get('engagement_type', '?')})\n"

        prompt = f"""Erstelle einen Proposal-Draft für {company[0]['name']}.

{context}

Das Proposal soll enthalten:
1. **Situationsanalyse** — Was ist die Herausforderung?
2. **Empfohlenes Profil** — Welcher Executive-Typ passt?
3. **Engagement-Modell** — Fractional oder Interim? Tage/Woche? Laufzeit?
4. **Nächste Schritte** — Was passiert nach Zusage?

WICHTIG: Kein Pricing — das macht Niels persönlich.

Antworte in JSON:
{{
  "title": "Proposal-Titel",
  "content_html": "<h2>Proposal: Company</h2><p>...</p>",
  "executive_profile": {{
    "title": "z.B. Interim CFO",
    "experience_years": "15+",
    "industry_focus": "SaaS / FinTech",
    "key_skills": ["Skill 1", "Skill 2"]
  }},
  "engagement_model": {{
    "type": "fractional oder interim",
    "days_per_week": "2-3",
    "estimated_duration": "6 Monate",
    "start_availability": "sofort / 2 Wochen"
  }}
}}"""

        text = claude_request(prompt, max_tokens=2000, system=AE_SOUL)
        if not text:
            continue

        try:
            proposal_data = json.loads(clean_json_response(text))
        except json.JSONDecodeError:
            continue

        supabase_request("POST", "proposal_draft", data={
            "company_id": company_id,
            "contact_id": dm.get("id") if dm else None,
            "title": proposal_data.get("title", f"Proposal: {company[0]['name']}"),
            "content_html": proposal_data.get("content_html", ""),
            "executive_profile": proposal_data.get("executive_profile"),
            "engagement_model": proposal_data.get("engagement_model"),
            "status": "draft",
        })

        supabase_request("PATCH", f"opportunity?id=eq.{opp['id']}", data={
            "proposal_status": "drafting",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        results["proposals_created"] += 1
        logger.info(f"  PROPOSAL: {company[0]['name']}")

        log_decision("ae_proposal", "opportunity", opp["id"],
                     f"AE created proposal for {company[0]['name']}",
                     {"agent": "ae", "pipeline_type": opp.get("pipeline_type")})

    return results


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run(config=None):
    """Run all AE agent tasks."""
    logger.info("\nAE AGENT")
    results = {"responses_sent": 0, "briefings_created": 0, "proposals_created": 0}

    if config is None:
        config = get_config()

    if config.get("outreach_mode") == "off":
        logger.info("  Outreach mode: OFF — AE skipping")
        return results

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — AE skipping")
        return results

    qualified_results = handle_new_qualifieds(config)
    results["responses_sent"] = qualified_results["responses_sent"]

    prep_results = generate_meeting_preps(config)
    results["briefings_created"] = prep_results["briefings_created"]

    proposal_results = generate_proposals(config)
    results["proposals_created"] = proposal_results["proposals_created"]

    logger.info(f"  AE Summary: {results['responses_sent']} responses, "
                f"{results['briefings_created']} briefings, {results['proposals_created']} proposals")
    return results


def main():
    run()


if __name__ == "__main__":
    main()
