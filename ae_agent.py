#!/usr/bin/env python3
"""
A-Line AE Agent — Bottom of Funnel.

Handles:
  - First response to qualified leads (after SDR handoff)
  - Meeting preparation & briefing documents
  - Post-meeting follow-up emails
  - Proposal drafts
  - Deeper company research for qualified leads

Called by orchestrator.py as Phase 4b.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger("ae_agent")

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
    """Load AE soul file."""
    path = os.path.join(os.path.dirname(__file__), "agent_soul_ae.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


AE_SOUL = load_soul()


def send_email(from_email, to_email, cc_email, subject, body_html):
    """Send email via Resend."""
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


# ═══════════════════════════════════════════════════════════
# QUALIFIED LEAD RESPONSE — First AE touch after handoff
# ═══════════════════════════════════════════════════════════

def handle_new_qualifieds(config):
    """Respond to leads that just got handed off from SDR."""
    results = {"responses_sent": 0}

    outreach_mode = config.get("outreach_mode", "draft")
    from_email = config.get("outreach_from_email", "niels@arteq.app")
    cc_email = config.get("outreach_cc", "niels@arteq.app")

    # Find replies that were handed off but not yet responded to by AE
    handoff_replies = supabase_request("GET", "outreach", params={
        "select": "id,thread_id,company_id,contact_id,subject,body_html,raw_text,reply_sentiment,created_at",
        "direction": "eq.inbound",
        "status": "eq.handoff_ae",
        "order": "created_at.asc",
        "limit": "10",
    })

    if not handoff_replies:
        return results

    logger.info(f"  🎯 {len(handoff_replies)} qualified leads to respond to")

    for reply in handoff_replies:
        thread_id = reply.get("thread_id")
        company_id = reply.get("company_id")
        contact_id = reply.get("contact_id")

        if not company_id or not contact_id:
            continue

        # Load company + contact
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

        # Load full conversation thread
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

        # Build richer context than SDR
        context = f"Company: {company['name']}\n"
        context += f"Industry: {company.get('industry', '?')} | Funding: {company.get('funding_stage', '?')}\n"
        context += f"Contact: {dm['name']} ({dm.get('title', '?')})\n"

        if dm.get("linkedin_url"):
            context += f"LinkedIn: {dm['linkedin_url']}\n"

        if intel["roles"]:
            context += "Offene/aktive Rollen:\n"
            for r in intel["roles"][:5]:
                context += f"  - {r['title']} ({r.get('engagement_type', '?')}) — Score: {r.get('final_score', '?')}\n"

        if intel["signals"]:
            context += "Relevante Signale:\n"
            for s in intel["signals"][:5]:
                context += f"  - [{s.get('type')}] {s.get('title', '')[:60]} (urgency: {s.get('urgency', '?')})\n"

        if intel["contacts"]:
            context += "Weitere Kontakte:\n"
            for c in intel["contacts"][:3]:
                ci = c.get("contact", {})
                context += f"  - {ci.get('name', '?')} ({ci.get('title', '?')})\n"

        dm_name = dm.get("name", "?")
        dm_title = dm.get("title", "?")
        co_name = company.get("name", "?")
        first_name = dm_name.split()[0] if dm_name != "?" else "?"

        prompt = f"""Du übernimmst diese Konversation vom SDR Agent. Die Person hat positives Interesse gezeigt.

Kontext:
{context}

Bisherige Konversation:
{conv_history}

Reply-Sentiment: {reply.get('reply_sentiment', 'interested')}

Deine Aufgabe:
- Nimm den Faden natürlich auf — die Person soll keinen Bruch merken
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
            logger.error(f"  JSON parse error for AE response to {co_name}")
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
                logger.info(f"  🎯 AE RESPONSE: {subject} → {dm['email']}")

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

        log_decision("ae_response", "company", company_id,
                     f"AE responded to qualified lead {dm_name} at {co_name}",
                     {"thread_id": thread_id, "agent": "ae"})
        log_dossier(company_id, "outreach",
                    f"AE Response: {subject}",
                    f"Qualified lead response to {dm_name}\n\n{body_html[:500]}")

        time.sleep(1)

    return results


# ═══════════════════════════════════════════════════════════
# MEETING PREP — Briefing documents for Niels
# ═══════════════════════════════════════════════════════════

def generate_meeting_preps(config):
    """Generate meeting prep briefings for companies in meeting_prep stage."""
    results = {"briefings_created": 0}

    # Find companies with scheduled meetings that don't have a prep yet
    companies = supabase_request("GET", "company", params={
        "select": "id,name,industry,funding_stage,domain,meeting_scheduled_at,pipeline_stage",
        "pipeline_stage": "eq.meeting_prep",
        "agent_owner": "eq.ae",
        "meeting_scheduled_at": "not.is.null",
        "order": "meeting_scheduled_at.asc",
        "limit": "5",
    })

    if not companies:
        return results

    for company in companies:
        # Check if prep already exists
        existing_prep = supabase_request("GET", "meeting_prep", params={
            "company_id": f"eq.{company['id']}",
            "select": "id",
            "limit": "1",
        })
        if existing_prep and len(existing_prep) > 0:
            continue

        intel = gather_company_intel(company["id"])

        # Build rich context
        context = f"Company: {company['name']}\n"
        context += f"Industry: {company.get('industry', '?')} | Funding: {company.get('funding_stage', '?')}\n"
        context += f"Domain: {company.get('domain', '?')}\n"
        context += f"Meeting: {company.get('meeting_scheduled_at', '?')}\n\n"

        if intel["roles"]:
            context += "Offene/aktive Rollen:\n"
            for r in intel["roles"][:10]:
                context += f"  - {r['title']} ({r.get('engagement_type', '?')}) — Status: {r.get('status', '?')}\n"

        if intel["signals"]:
            context += "\nSignale:\n"
            for s in intel["signals"][:10]:
                context += f"  - [{s.get('type')}] {s.get('title', '')} (urgency: {s.get('urgency', '?')})\n"

        stakeholder_info = ""
        if intel["contacts"]:
            context += "\nKontakte:\n"
            for c in intel["contacts"]:
                ci = c.get("contact", {})
                dm_marker = " ★ Decision Maker" if c.get("is_decision_maker") else ""
                context += f"  - {ci.get('name', '?')} — {ci.get('title', '?')}{dm_marker}\n"
                if ci.get("linkedin_url"):
                    context += f"    LinkedIn: {ci['linkedin_url']}\n"
                stakeholder_info += f"- {ci.get('name', '?')} ({ci.get('title', '?')})\n"

        # Load conversation history
        outreach = supabase_request("GET", "outreach", params={
            "company_id": f"eq.{company['id']}",
            "select": "direction,subject,body_html,raw_text,reply_sentiment,created_at",
            "order": "created_at.asc",
            "limit": "20",
        })
        if outreach:
            context += "\nBisherige Kommunikation:\n"
            for msg in outreach:
                sender = "A-Line" if msg.get("direction") == "outbound" else "Kontakt"
                body = msg.get("raw_text") or re.sub(r"<[^>]+>", "", msg.get("body_html", ""))
                body = re.sub(r"\s+", " ", body).strip()
                context += f"  [{sender}]: {body[:200]}\n"

        prompt = f"""Erstelle ein Meeting-Briefing für Niels.

{context}

Das Briefing soll enthalten:

1. **Company Summary** — Was macht die Firma, wie groß, welche Phase?
2. **Stakeholder** — Wer sitzt vermutlich am Tisch? Hintergrund.
3. **Hypothese** — Was ist vermutlich ihr Problem? Warum haben sie Interesse?
4. **A-Line-Fit** — Welcher Executive-Typ passt? Fractional oder Interim? Warum?
5. **Talking Points** — 3-4 gute Fragen die Niels stellen sollte
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
            logger.error(f"  JSON parse error for meeting prep: {company['name']}")
            continue

        supabase_request("POST", "meeting_prep", data={
            "company_id": company["id"],
            "meeting_date": company.get("meeting_scheduled_at"),
            "briefing_html": prep_data.get("briefing_html", ""),
            "stakeholders": prep_data.get("stakeholders", []),
            "hypotheses": prep_data.get("hypotheses", []),
            "talking_points": prep_data.get("talking_points", []),
            "red_flags": prep_data.get("red_flags", []),
            "status": "draft",
        })

        results["briefings_created"] += 1
        logger.info(f"  📋 BRIEFING: {company['name']}")

        log_decision("ae_meeting_prep", "company", company["id"],
                     f"AE created meeting briefing for {company['name']}",
                     {"agent": "ae"})
        log_dossier(company["id"], "agent_action",
                    f"Meeting Briefing erstellt",
                    prep_data.get("briefing_html", "")[:1000])

    return results


# ═══════════════════════════════════════════════════════════
# PROPOSAL DRAFTS — Generate proposals for Niels to review
# ═══════════════════════════════════════════════════════════

def generate_proposals(config):
    """Generate proposal drafts for companies in proposal stage."""
    results = {"proposals_created": 0}

    companies = supabase_request("GET", "company", params={
        "select": "id,name,industry,funding_stage,domain,pipeline_stage",
        "pipeline_stage": "eq.proposal",
        "proposal_status": "in.(none,drafting)",
        "agent_owner": "eq.ae",
        "limit": "5",
    })

    if not companies:
        return results

    for company in companies:
        existing = supabase_request("GET", "proposal_draft", params={
            "company_id": f"eq.{company['id']}",
            "status": "in.(draft,sent)",
            "select": "id",
            "limit": "1",
        })
        if existing and len(existing) > 0:
            continue

        intel = gather_company_intel(company["id"])

        # Find the main contact
        dm = None
        for c in intel["contacts"]:
            if c.get("is_decision_maker") and c.get("contact", {}).get("email"):
                dm = c["contact"]
                break
        if not dm and intel["contacts"]:
            dm = intel["contacts"][0].get("contact", {})

        context = f"Company: {company['name']}\n"
        context += f"Industry: {company.get('industry', '?')} | Funding: {company.get('funding_stage', '?')}\n"

        if intel["roles"]:
            context += "Aktive Rollen:\n"
            for r in intel["roles"][:5]:
                context += f"  - {r['title']} ({r.get('engagement_type', '?')})\n"

        # Load meeting prep if exists
        prep = supabase_request("GET", "meeting_prep", params={
            "company_id": f"eq.{company['id']}",
            "select": "briefing_html,hypotheses,talking_points",
            "order": "created_at.desc",
            "limit": "1",
        })
        if prep and len(prep) > 0:
            context += f"\nMeeting-Briefing Hypothesen: {json.dumps(prep[0].get('hypotheses', []))}\n"

        prompt = f"""Erstelle einen Proposal-Draft für {company['name']}.

{context}

Das Proposal soll enthalten:
1. **Situationsanalyse** — Was ist die Herausforderung der Company?
2. **Empfohlenes Profil** — Welcher Executive-Typ passt? (Titel, Erfahrung, Branche)
3. **Engagement-Modell** — Fractional oder Interim? Tage/Woche? Geschätzte Laufzeit?
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
            logger.error(f"  JSON parse error for proposal: {company['name']}")
            continue

        supabase_request("POST", "proposal_draft", data={
            "company_id": company["id"],
            "contact_id": dm.get("id") if dm else None,
            "title": proposal_data.get("title", f"Proposal: {company['name']}"),
            "content_html": proposal_data.get("content_html", ""),
            "executive_profile": proposal_data.get("executive_profile"),
            "engagement_model": proposal_data.get("engagement_model"),
            "status": "draft",
        })

        supabase_request("PATCH", f"company?id=eq.{company['id']}", data={
            "proposal_status": "drafting",
        })

        results["proposals_created"] += 1
        logger.info(f"  📄 PROPOSAL DRAFT: {company['name']}")

        log_decision("ae_proposal", "company", company["id"],
                     f"AE created proposal draft for {company['name']}",
                     {"agent": "ae"})
        log_dossier(company["id"], "agent_action",
                    f"Proposal-Draft erstellt",
                    proposal_data.get("content_html", "")[:1000])

    return results


# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT (called by orchestrator)
# ═══════════════════════════════════════════════════════════

def run(config):
    """Run all AE agent tasks. Returns combined results dict."""
    logger.info("\n🎯 AE AGENT")
    results = {"responses_sent": 0, "briefings_created": 0, "proposals_created": 0}

    if config.get("outreach_mode") == "off":
        logger.info("  Outreach mode: OFF — AE skipping")
        return results

    if not ANTHROPIC_KEY:
        logger.info("  No ANTHROPIC_API_KEY — AE skipping")
        return results

    # Step 1: Respond to newly qualified leads (SDR handoffs)
    qualified_results = handle_new_qualifieds(config)
    results["responses_sent"] = qualified_results["responses_sent"]

    # Step 2: Generate meeting preps
    prep_results = generate_meeting_preps(config)
    results["briefings_created"] = prep_results["briefings_created"]

    # Step 3: Generate proposals
    proposal_results = generate_proposals(config)
    results["proposals_created"] = proposal_results["proposals_created"]

    logger.info(f"  AE Summary: {results['responses_sent']} responses, "
                f"{results['briefings_created']} briefings, {results['proposals_created']} proposals")
    return results
