#!/usr/bin/env python3
"""
A-Line Role Enricher — Decision maker research + sourcing brief extraction.

Trigger: All roles with enrichment_status='pending'
Flow:
  1. Decision Maker Research (Claude Sonnet) — identify hiring manager
  2. Sourcing Brief Extraction (Claude Sonnet) — structured role analysis
  3. Set enrichment_status='complete'

Usage: python -m enrichment.role_enricher
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("role_enricher")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def supabase_request(method, table, data=None, params=None, upsert=False):
    """Make a request to Supabase REST API."""
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

        if resp.status_code in (200, 201):
            return resp.json()
        else:
            logger.error(f"Supabase {method} {table}: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Supabase error: {e}")
        return None


def clean_json_response(text):
    """Strip markdown fences and extract JSON from Claude response."""
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
        idx_obj = t.find('{')
        idx_arr = t.find('[')
        if idx_obj >= 0 and (idx_arr < 0 or idx_obj < idx_arr):
            t = t[idx_obj:]
        elif idx_arr >= 0:
            t = t[idx_arr:]
    if t and t[0] in ('{', '['):
        open_ch = t[0]
        close_ch = '}' if open_ch == '{' else ']'
        depth = 0
        for i, c in enumerate(t):
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
            if depth == 0:
                t = t[:i + 1]
                break
    return t


def claude_request(prompt, max_tokens=1500, system=None):
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


# ═══════════════════════════════════════════════════════════
# ENRICHMENT STEPS
# ═══════════════════════════════════════════════════════════

def research_decision_maker(role, company):
    """Step 1: Identify the hiring manager via Claude."""
    company_name = company.get("name", "Unknown")
    job_url = role.get("source_url", "") or ""
    job_title = role.get("title", "")
    headcount = company.get("headcount", "unknown")

    prompt = f"""You are a decision maker research agent. Given a company name, job posting URL, and job title, identify the most likely hiring manager — the person who will actually make the hiring decision, not necessarily the CEO.

Company: {company_name}
Job URL: {job_url}
Job Title: {job_title}
Company Headcount: {headcount}

STEP 1 — READ THE POSTING
- Fetch and read the full job posting
- Extract any explicit name, title, or reporting line mentioned
- Look for phrases like: "reports to", "works with", "in close collaboration with", "Zusammenarbeit mit"
- If a reporting line is explicit → use it directly, skip Step 2

STEP 2 — INFER DECISION MAKER BY ROLE + HEADCOUNT

Use this matrix:

| Role Type                        | <30 employees     | 30–100 employees        | 100–300 employees        | >300 employees             |
|----------------------------------|-------------------|-------------------------|--------------------------|----------------------------|
| Finance / Controlling / CFO      | CEO/GF            | CEO or CFO if exists    | CFO / Finance Director   | CFO or Finance VP          |
| HR / People & Culture            | CEO/GF            | Head of People / CHRO   | CHRO / HR Director       | HR BP or HRBP              |
| Engineering / Tech               | CTO / CEO         | CTO                     | CTO / VP Engineering     | VP Engineering / EM        |
| Sales / GTM / Revenue            | CEO/GF            | VP Sales / CCO          | VP Sales / CRO           | Sales Director / RD        |
| Marketing / Growth               | CEO/GF            | Head of Marketing       | CMO / Marketing Director | Marketing Director         |
| Product                          | CEO/CTO           | CPO / Head of Product   | CPO                      | Product Director / GM      |
| Operations / General Management  | CEO/GF            | COO / Head of Ops       | COO                      | Operations Director        |
| Customer Success / Support       | CEO/GF            | Head of CS              | VP Customer Success      | CS Director                |
| Data / Analytics                 | CTO / CEO         | Head of Data / CTO      | VP Data / CDO            | Data Director              |

STEP 3 — FIND THE PERSON
Search in this order:
1. "[company] [inferred title] LinkedIn" (e.g. "{company_name} CFO LinkedIn")
2. "[company] Impressum" → always lists legal GF for German GmbHs
3. "[company] Über uns" or "[company] team page"
4. "[company] [role type] name" (e.g. "{company_name} Head of Finance")

STEP 4 — VALIDATE
- Does this person's seniority match the role being hired?
- Is it plausible they'd own this hiring decision at this company size?
- If the company is >200 people and you only found the CEO: flag confidence as "low"

Return ONLY a JSON object:

{{
  "decision_maker_name": "full name or null",
  "decision_maker_title": "their current title",
  "decision_maker_linkedin": "LinkedIn URL or null",
  "confidence": "high | medium | low",
  "confidence_reason": "e.g. 'confirmed via Impressum', 'inferred from reporting line in posting', 'matrix inference at 25 employees'",
  "is_ceo": true/false,
  "source": "Impressum | team page | LinkedIn | job posting | inferred"
}}

Rules:
- Never guess a name. null + low confidence is better than a wrong name.
- German Impressum = ground truth for GF identity.
- For roles at <50 employees: CEO/GF is almost always correct unless posting explicitly names someone else.
- For roles at >100 employees: do not default to CEO without evidence."""

    text = claude_request(prompt, max_tokens=800, system="You are a decision maker research agent. Return only valid JSON.")
    if not text:
        return None

    try:
        result = json.loads(clean_json_response(text))
        return result
    except json.JSONDecodeError as e:
        logger.error(f"  DM research JSON parse error: {e}")
        return None


def extract_sourcing_brief(role, company, dm_result):
    """Step 2: Extract structured sourcing brief from role description."""
    company_name = company.get("name", "Unknown")
    headcount = company.get("headcount", "unknown")
    description = role.get("description", "") or ""
    job_title = role.get("title", "")

    dm_name = dm_result.get("decision_maker_name", "unknown") if dm_result else "unknown"
    dm_title = dm_result.get("decision_maker_title", "unknown") if dm_result else "unknown"

    # If no description, use title + URL as context
    job_context = description if description else f"Job Title: {job_title}\nJob URL: {role.get('source_url', 'N/A')}"

    prompt = f"""You are a sourcing brief extraction agent. Analyze the following job posting and extract a structured sourcing brief for a recruiter.

Company: {company_name}
Company Headcount: {headcount}
Decision Maker: {dm_name} ({dm_title})

Job Posting:
{job_context[:4000]}

Return ONLY a JSON object with these exact fields:

{{
  "role_title": "exact title from posting",
  "location": "city + remote policy",
  "work_model": "remote | hybrid | onsite",
  "employment_type": "full-time | part-time | fractional | interim",
  "reports_to": "who this role reports to",
  "team_size_context": "team context if mentioned",

  "must_have": [
    "requirement 1",
    "requirement 2"
  ],

  "nice_to_have": [
    "nice-to-have 1",
    "nice-to-have 2"
  ],

  "seniority": "Junior | Mid | Senior | Lead | Head of | C-Level",

  "ideal_candidate_profile": {{
    "background": "ideal background description",
    "years_experience": "range",
    "company_types_to_target": ["type 1", "type 2"],
    "titles_to_search": ["title 1", "title 2"],
    "titles_to_exclude": ["title 1 (reason)"]
  }},

  "red_flags_to_filter_out": [
    "red flag 1",
    "red flag 2"
  ],

  "compensation_signal": "any salary/equity info or null",
  "urgency": "assessment of hiring urgency"
}}

Rules:
- Extract from the actual posting text — do not invent requirements not mentioned.
- For must_have vs nice_to_have: if the posting says "idealerweise", "wünschenswert", "nice to have" → nice_to_have.
- ALWAYS write in English, even if the posting is in German. Translate all requirements, descriptions, and profiles to English.
- If information is not available, use null or empty arrays — never hallucinate."""

    text = claude_request(prompt, max_tokens=2000, system="You are a sourcing brief extraction agent. Return only valid JSON.")
    if not text:
        return None

    try:
        result = json.loads(clean_json_response(text))
        return result
    except json.JSONDecodeError as e:
        logger.error(f"  Sourcing brief JSON parse error: {e}")
        return None


def sourcing_brief_to_html(brief):
    """Convert sourcing brief JSON to formatted HTML for dossier entry."""
    if not brief:
        return "<p>No sourcing brief available.</p>"

    html = '<h3>Sourcing Brief</h3>'

    # Role overview
    parts = []
    if brief.get("role_title"):
        parts.append(f"<strong>Role:</strong> {brief['role_title']}")
    if brief.get("location"):
        parts.append(f"<strong>Location:</strong> {brief['location']}")
    if brief.get("work_model"):
        parts.append(f"<strong>Work Model:</strong> {brief['work_model']}")
    if brief.get("employment_type"):
        parts.append(f"<strong>Type:</strong> {brief['employment_type']}")
    if brief.get("seniority"):
        parts.append(f"<strong>Seniority:</strong> {brief['seniority']}")
    if brief.get("reports_to"):
        parts.append(f"<strong>Reports to:</strong> {brief['reports_to']}")
    if parts:
        html += '<p>' + ' · '.join(parts) + '</p>'

    # Must-haves
    must_have = brief.get("must_have", [])
    if must_have:
        html += '<h4>Must-Have Requirements</h4><ul>'
        for item in must_have:
            html += f'<li>{item}</li>'
        html += '</ul>'

    # Nice-to-haves
    nice_to_have = brief.get("nice_to_have", [])
    if nice_to_have:
        html += '<h4>Nice-to-Have</h4><ul>'
        for item in nice_to_have:
            html += f'<li>{item}</li>'
        html += '</ul>'

    # Ideal candidate
    profile = brief.get("ideal_candidate_profile", {})
    if profile:
        html += '<h4>Ideal Candidate Profile</h4>'
        if profile.get("background"):
            html += f'<p><strong>Background:</strong> {profile["background"]}</p>'
        if profile.get("years_experience"):
            html += f'<p><strong>Experience:</strong> {profile["years_experience"]}</p>'
        if profile.get("titles_to_search"):
            html += '<p><strong>Target Titles:</strong> ' + ', '.join(profile["titles_to_search"]) + '</p>'
        if profile.get("company_types_to_target"):
            html += '<p><strong>Target Companies:</strong> ' + ', '.join(profile["company_types_to_target"]) + '</p>'

    # LinkedIn boolean search

    # Red flags
    red_flags = brief.get("red_flags_to_filter_out", [])
    if red_flags:
        html += '<h4>Red Flags</h4><ul>'
        for item in red_flags:
            html += f'<li>{item}</li>'
        html += '</ul>'

    # Compensation + urgency
    extras = []
    if brief.get("compensation_signal"):
        extras.append(f"<strong>Compensation:</strong> {brief['compensation_signal']}")
    if brief.get("urgency"):
        extras.append(f"<strong>Urgency:</strong> {brief['urgency']}")
    if extras:
        html += '<p>' + ' · '.join(extras) + '</p>'

    return html


# ═══════════════════════════════════════════════════════════
# CONTACT CREATION
# ═══════════════════════════════════════════════════════════

def upsert_dm_contact(name, title, linkedin_url, company_id):
    """Create or update a contact record for the hiring manager and link to company."""
    if not name or not company_id:
        return None

    # Check existing by linkedin_url or name
    existing = None
    if linkedin_url:
        existing = supabase_request("GET", "contact", params={
            "linkedin_url": f"eq.{linkedin_url}",
            "select": "id",
            "limit": "1",
        })
    if not existing:
        existing = supabase_request("GET", "contact", params={
            "name": f"eq.{name}",
            "select": "id",
            "limit": "1",
        })

    if existing and len(existing) > 0:
        contact_id = existing[0]["id"]
        update = {k: v for k, v in {
            "title": title,
            "linkedin_url": linkedin_url,
        }.items() if v}
        if update:
            supabase_request("PATCH", f"contact?id=eq.{contact_id}", data=update)
    else:
        result = supabase_request("POST", "contact", data={
            "name": name,
            "title": title or "",
            "linkedin_url": linkedin_url or "",
            "enrichment_status": "pending",
        })
        if result and len(result) > 0:
            contact_id = result[0]["id"]
        else:
            return None

    # Link to company via company_contact
    existing_link = supabase_request("GET", "company_contact", params={
        "company_id": f"eq.{company_id}",
        "contact_id": f"eq.{contact_id}",
        "select": "id",
        "limit": "1",
    })
    if not existing_link:
        supabase_request("POST", "company_contact", data={
            "company_id": company_id,
            "contact_id": contact_id,
            "role_at_company": title or "",
            "is_decision_maker": True,
        })

    return contact_id


# ═══════════════════════════════════════════════════════════
# MAIN ENRICHMENT FLOW
# ═══════════════════════════════════════════════════════════

def enrich_role(role, company):
    """Full enrichment pipeline for a single role."""
    role_id = role["id"]
    role_title = role.get("title", "Unknown")
    company_name = company.get("name", "Unknown")

    logger.info(f"\nEnriching role: {role_title} at {company_name}")

    # Mark as enriching
    supabase_request("PATCH", f"role?id=eq.{role_id}", data={
        "enrichment_status": "enriching",
    })

    # ── Step 1: Decision Maker Research ──
    logger.info("  Step 1: Decision maker research...")
    dm_result = research_decision_maker(role, company)

    if dm_result:
        update_data = {}
        if dm_result.get("decision_maker_name"):
            update_data["hiring_manager_name"] = dm_result["decision_maker_name"]
        if dm_result.get("decision_maker_title"):
            update_data["hiring_manager_title"] = dm_result["decision_maker_title"]
        if dm_result.get("decision_maker_linkedin"):
            update_data["hiring_manager_linkedin"] = dm_result["decision_maker_linkedin"]
        if dm_result.get("confidence"):
            update_data["hiring_manager_confidence"] = dm_result["confidence"]

        if update_data:
            supabase_request("PATCH", f"role?id=eq.{role_id}", data=update_data)

        # Write DM research dossier entry
        dm_name = dm_result.get("decision_maker_name", "Not found")
        dm_title = dm_result.get("decision_maker_title", "")
        confidence = dm_result.get("confidence", "low")
        dm_html = f'<h3>Decision Maker Research</h3>'
        dm_html += f'<p><strong>Hiring Manager:</strong> {dm_name}</p>'
        if dm_title:
            dm_html += f'<p><strong>Title:</strong> {dm_title}</p>'
        if dm_result.get("decision_maker_linkedin"):
            dm_html += f'<p><strong>LinkedIn:</strong> <a href="{dm_result["decision_maker_linkedin"]}" target="_blank">Profile</a></p>'
        dm_html += f'<p><strong>Confidence:</strong> {confidence}</p>'
        if dm_result.get("confidence_reason"):
            dm_html += f'<p><strong>Reason:</strong> {dm_result["confidence_reason"]}</p>'

        # Create real contact record for the hiring manager
        contact_id = None
        if dm_name and dm_name != "Not found":
            contact_id = upsert_dm_contact(dm_name, dm_title,
                dm_result.get("decision_maker_linkedin"), role.get("company_id"))

        supabase_request("POST", "company_dossier", data={
            "company_id": role.get("company_id"),
            "role_id": role_id,
            "contact_id": contact_id,
            "entry_type": "role_dm_research",
            "title": f"Decision Maker: {dm_name} — {confidence} confidence",
            "content": dm_html,
            "source": "role_enricher",
            "author": "A-Line Agent",
        })

        logger.info(f"  DM found: {dm_name} ({dm_title}) [{confidence}]{' → contact created' if contact_id else ''}")
    else:
        logger.info("  DM research: no result")

    time.sleep(1)

    # ── Step 2: Sourcing Brief Extraction ──
    logger.info("  Step 2: Sourcing brief extraction...")
    brief = extract_sourcing_brief(role, company, dm_result)

    if brief:
        supabase_request("PATCH", f"role?id=eq.{role_id}", data={
            "sourcing_brief": json.dumps(brief),
        })

        # Write sourcing brief dossier entry
        brief_html = sourcing_brief_to_html(brief)
        supabase_request("POST", "company_dossier", data={
            "company_id": role.get("company_id"),
            "role_id": role_id,
            "entry_type": "role_analysis",
            "title": f"Sourcing Brief: {role_title}",
            "content": brief_html,
            "source": "role_enricher",
            "author": "A-Line Agent",
        })

        logger.info(f"  Sourcing brief: {len(brief.get('must_have', []))} must-haves, {len(brief.get('nice_to_have', []))} nice-to-haves")
    else:
        logger.info("  Sourcing brief: no result")

    # ── Step 3: Mark complete ──
    supabase_request("PATCH", f"role?id=eq.{role_id}", data={
        "enrichment_status": "complete",
    })

    logger.info(f"  Role enrichment complete: {role_title}")
    return True


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run():
    """Run enrichment for all pending roles."""
    logger.info("=" * 60)
    logger.info("A-Line Role Enricher — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    if not ANTHROPIC_KEY:
        logger.error("Missing ANTHROPIC_API_KEY")
        return

    # Get pending roles with company data
    roles = supabase_request("GET", "role", params={
        "select": "id,title,company_id,source_url,description,tier,engagement_type,location",
        "enrichment_status": "eq.pending",
        "status": "eq.active",
        "order": "created_at.desc",
        "limit": "20",
    })

    if not roles:
        logger.info("No pending roles to enrich — done")
        return

    logger.info(f"Found {len(roles)} roles to enrich")

    enriched = 0
    for role in roles:
        # Fetch company for this role
        company_rows = supabase_request("GET", "company", params={
            "id": f"eq.{role['company_id']}",
            "select": "id,name,domain,headcount,industry",
            "limit": "1",
        })
        company = company_rows[0] if company_rows else {"id": role["company_id"], "name": "Unknown"}

        try:
            if enrich_role(role, company):
                enriched += 1
        except Exception as e:
            logger.error(f"Error enriching role {role.get('title', '?')}: {e}")
            supabase_request("PATCH", f"role?id=eq.{role['id']}", data={
                "enrichment_status": "pending",
            })

        time.sleep(1)

    logger.info("=" * 60)
    logger.info(f"ROLE ENRICHER SUMMARY: {enriched}/{len(roles)} enriched")
    logger.info("=" * 60)


def main():
    run()


if __name__ == "__main__":
    main()
