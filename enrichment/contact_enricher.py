#!/usr/bin/env python3
"""
A-Line Contact Enricher — Deep enrichment for contacts at enriched companies.

Trigger: Contacts at companies with enrichment_status='complete', contact enrichment_status='pending'
Per contact:
  1. Contact details: Email, phone, LinkedIn (Apollo People Match — 1 credit)
  2. Career history: Apollo person data → last 3 jobs, tenure
  3. Thought leadership: DuckDuckGo search for podcasts/conferences/interviews
  4. Decision maker score: Claude rates 0-100
  5. Personal hooks: Claude finds commonalities, current topics
  6. Set enrichment_status='complete'

Usage: python -m enrichment.contact_enricher
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("contact_enricher")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")


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


def log_apollo_credit(entity_id, action, credits=1):
    """Track Apollo credit usage."""
    supabase_request("POST", "apollo_credit_ledger", data={
        "entity_type": "contact",
        "entity_id": str(entity_id),
        "action": action,
        "credits": credits,
    })


def get_apollo_budget():
    """Check remaining Apollo budget for the month."""
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    result = supabase_request("GET", "apollo_credit_ledger", params={
        "select": "credits",
        "created_at": f"gte.{month_start}T00:00:00Z",
    })
    used = sum(r["credits"] for r in (result or []))

    config = supabase_request("GET", "agent_config", params={
        "key": "eq.apollo_monthly_credit_budget",
        "select": "value",
        "limit": "1",
    })
    budget = int((config or [{}])[0].get("value", "500")) if config else 500
    return budget - used


# ═══════════════════════════════════════════════════════════
# ENRICHMENT STEPS
# ═══════════════════════════════════════════════════════════

def enrich_via_apollo_match(contact, company_domain=None):
    """
    Apollo People Match — get email, phone, career history.
    Costs 1 credit per match.
    """
    if not APOLLO_API_KEY:
        return None

    payload = {"reveal_personal_emails": False, "reveal_phone_number": True}

    # Prefer apollo_id if available
    apollo_id = contact.get("apollo_id")
    if apollo_id:
        payload["id"] = apollo_id
    elif contact.get("name") and company_domain:
        parts = contact["name"].split(" ", 1)
        payload["first_name"] = parts[0]
        if len(parts) > 1:
            payload["last_name"] = parts[1]
        payload["organization_domain"] = company_domain
    elif contact.get("linkedin_url"):
        payload["linkedin_url"] = contact["linkedin_url"]
    else:
        return None

    try:
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
            return None

        person = resp.json().get("person")
        if not person:
            return None

        # Extract career history (last 3 jobs)
        employment = person.get("employment_history", []) or []
        career_history = []
        for job in employment[:3]:
            career_history.append({
                "company": job.get("organization_name", ""),
                "title": job.get("title", ""),
                "start_date": job.get("start_date", ""),
                "end_date": job.get("end_date", ""),
                "current": job.get("current", False),
            })

        return {
            "email": person.get("email"),
            "email_status": person.get("email_status"),
            "phone": (person.get("phone_numbers") or [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
            "linkedin_url": person.get("linkedin_url") or contact.get("linkedin_url"),
            "title": person.get("title") or contact.get("title"),
            "career_history": career_history,
        }
    except Exception as e:
        logger.error(f"Apollo match error: {e}")
        return None


def search_thought_leadership(name, company_name):
    """Search DuckDuckGo for thought leadership: podcasts, conferences, interviews."""
    results_data = []
    query = f'"{name}" "{company_name}" podcast OR conference OR interview OR keynote OR panel'

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            url = r.get("href", "")

            # Filter for actual thought leadership content
            combined = f"{title} {body}".lower()
            if any(kw in combined for kw in ["podcast", "conference", "interview", "keynote",
                                              "panel", "speaker", "talk", "webinar",
                                              "vortrag", "konferenz"]):
                results_data.append({
                    "title": title[:200],
                    "url": url,
                    "snippet": body[:300],
                    "type": "thought_leadership",
                })

    except Exception as e:
        logger.debug(f"DDG thought leadership search error for {name}: {e}")

    return results_data if results_data else None


def score_decision_maker(contact, company_context):
    """Use Claude to rate decision maker score 0-100 and find personal hooks."""
    if not ANTHROPIC_KEY:
        return None, None

    career = contact.get("career_history") or []
    career_text = ""
    for job in career:
        career_text += f"  - {job.get('title', '?')} at {job.get('company', '?')} ({job.get('start_date', '?')} - {job.get('end_date', 'present')})\n"

    thought = contact.get("thought_leadership") or []
    thought_text = ""
    for item in thought:
        thought_text += f"  - {item.get('title', '?')} ({item.get('url', '')})\n"

    prompt = f"""Rate this person as a decision maker for hiring interim/fractional executives.

Contact: {contact.get('name', '?')} — {contact.get('title', '?')}
Company: {company_context}

Career History:
{career_text or '  (not available)'}

Thought Leadership:
{thought_text or '  (not found)'}

Email: {'yes' if contact.get('email') else 'no'}
LinkedIn: {'yes' if contact.get('linkedin_url') else 'no'}

Rate:
1. decision_maker_score (0-100): How likely is this person to decide on hiring an interim/fractional exec?
   - CEO/Geschäftsführer + email = 90+
   - CFO/COO with executive hiring authority = 70-90
   - VP/Head of with team leadership = 50-70
   - HR Lead = 60-80 (gatekeepers)
   - No email = -20 penalty

2. personal_hooks: 2-3 conversation starters based on their background

Respond in JSON:
{{"decision_maker_score": 85, "personal_hooks": ["Hook 1", "Hook 2"]}}"""

    try:
        body = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=30,
        )
        if resp.status_code != 200:
            return None, None

        data = resp.json()
        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()

        result = json.loads(clean_json_response(text))
        return result.get("decision_maker_score"), result.get("personal_hooks")

    except Exception as e:
        logger.error(f"Claude DM scoring error: {e}")
        return None, None


# ═══════════════════════════════════════════════════════════
# MAIN ENRICHMENT FLOW
# ═══════════════════════════════════════════════════════════

def enrich_contact(contact, company):
    """Full enrichment pipeline for a single contact."""
    contact_id = contact["id"]
    contact_name = contact.get("name", "?")
    company_name = company.get("name", "?")
    company_domain = (company.get("domain") or "").replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] or None

    logger.info(f"  Enriching contact: {contact_name} ({contact.get('title', '?')}) at {company_name}")

    update_data = {}

    # ── 1. Apollo People Match (email, phone, career) ──
    if get_apollo_budget() > 5:
        apollo_data = enrich_via_apollo_match(contact, company_domain)
        if apollo_data:
            if apollo_data.get("email") and not contact.get("email"):
                update_data["email"] = apollo_data["email"]
                update_data["email_status"] = apollo_data.get("email_status")
            if apollo_data.get("phone") and not contact.get("phone"):
                update_data["phone"] = apollo_data["phone"]
            if apollo_data.get("linkedin_url") and not contact.get("linkedin_url"):
                update_data["linkedin_url"] = apollo_data["linkedin_url"]
            if apollo_data.get("title"):
                update_data["title"] = apollo_data["title"]

            # Career history
            if apollo_data.get("career_history"):
                update_data["career_history"] = json.dumps(apollo_data["career_history"])
                contact["career_history"] = apollo_data["career_history"]

            log_apollo_credit(contact_id, "people_match", 1)
            logger.info(f"    Apollo: email={apollo_data.get('email', '?')}, career={len(apollo_data.get('career_history', []))} jobs")
        time.sleep(0.5)

    # ── 2. Thought Leadership (DuckDuckGo) ──
    thought = search_thought_leadership(contact_name, company_name)
    if thought:
        update_data["thought_leadership"] = json.dumps(thought)
        contact["thought_leadership"] = thought
        logger.info(f"    Thought leadership: {len(thought)} items found")
    time.sleep(1)

    # ── 3. Decision Maker Score + Personal Hooks (Claude) ──
    # Merge latest data for scoring
    merged_contact = {**contact, **update_data}
    company_context = f"{company_name} ({company.get('industry', '?')}, {company.get('headcount', '?')} employees)"

    dm_score, hooks = score_decision_maker(merged_contact, company_context)
    if dm_score is not None:
        update_data["decision_maker_score"] = dm_score
        logger.info(f"    DM score: {dm_score}/100")

    # ── 4. Update contact record ──
    update_data["enrichment_status"] = "complete"
    supabase_request("PATCH", f"contact?id=eq.{contact_id}", data=update_data)

    # Write contact intel to contact's own dossier thread
    if dm_score is not None:
        intel_parts = [f"<h3>Contact Intel: {contact_name}</h3>"]
        intel_parts.append(f"<p><strong>DM Score:</strong> {dm_score}/100</p>")
        intel_parts.append(f"<p><strong>Title:</strong> {contact.get('title', '—')}</p>")
        if contact.get("career_history"):
            intel_parts.append("<h4>Career History</h4><ul>")
            for job in (contact["career_history"] if isinstance(contact["career_history"], list) else []):
                intel_parts.append(f"<li>{job.get('title', '?')} at {job.get('company', '?')}</li>")
            intel_parts.append("</ul>")
        if contact.get("thought_leadership"):
            items = contact["thought_leadership"] if isinstance(contact["thought_leadership"], list) else []
            if items:
                intel_parts.append("<h4>Thought Leadership</h4><ul>")
                for item in items:
                    intel_parts.append(f"<li><a href=\"{item.get('url', '#')}\">{item.get('title', '?')}</a></li>")
                intel_parts.append("</ul>")

        supabase_request("POST", "company_dossier", data={
            "contact_id": contact_id,
            "company_id": company.get("id"),
            "entry_type": "contact_intel",
            "title": f"Contact Intel: {contact_name} — DM Score {dm_score}/100",
            "content": "\n".join(intel_parts),
            "source": "contact_enricher",
            "author": "A-Line Agent",
        })

    # Write personal hooks separately
    if hooks:
        hooks_text = "\n".join(f"<li>{h}</li>" for h in hooks)
        supabase_request("POST", "company_dossier", data={
            "contact_id": contact_id,
            "company_id": company.get("id"),
            "entry_type": "personal_hooks",
            "title": f"Personal Hooks: {contact_name}",
            "content": f"<h3>Personal Hooks</h3><p><strong>DM Score:</strong> {dm_score}/100</p><ul>{hooks_text}</ul>",
            "source": "contact_enricher",
            "author": "A-Line Agent",
        })

    return True


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run():
    """Run enrichment for all pending contacts at enriched companies."""
    logger.info("=" * 60)
    logger.info("A-Line Contact Enricher — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Get enriched companies
    companies = supabase_request("GET", "company", params={
        "select": "id,name,domain,industry,headcount",
        "enrichment_status": "eq.complete",
        "limit": "50",
    })

    if not companies:
        logger.info("No enriched companies found — done")
        return

    company_map = {c["id"]: c for c in companies}
    company_ids = ",".join(c["id"] for c in companies)

    # Get pending contacts at these companies
    links = supabase_request("GET", "company_contact", params={
        "company_id": f"in.({company_ids})",
        "select": "company_id,contact:contact_id(id,name,title,email,phone,linkedin_url,enrichment_status,apollo_id)",
    })

    if not links:
        logger.info("No contacts found — done")
        return

    # Filter to pending contacts
    pending = []
    for link in links:
        contact = link.get("contact")
        if contact and contact.get("enrichment_status") == "pending":
            pending.append({
                "contact": contact,
                "company_id": link["company_id"],
            })

    if not pending:
        logger.info("No pending contacts to enrich — done")
        return

    logger.info(f"Found {len(pending)} pending contacts to enrich")

    budget = get_apollo_budget()
    logger.info(f"Apollo budget remaining: {budget} credits")

    enriched = 0
    for item in pending:
        if get_apollo_budget() < 3:
            logger.warning("Apollo budget too low — stopping contact enrichment")
            break

        contact = item["contact"]
        company = company_map.get(item["company_id"], {})

        try:
            if enrich_contact(contact, company):
                enriched += 1
        except Exception as e:
            logger.error(f"Error enriching contact {contact.get('name', '?')}: {e}")

        time.sleep(0.5)

    logger.info("=" * 60)
    logger.info(f"CONTACT ENRICHER SUMMARY: {enriched}/{len(pending)} enriched")
    logger.info("=" * 60)


def main():
    run()


if __name__ == "__main__":
    main()
