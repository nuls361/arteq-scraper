#!/usr/bin/env python3
"""
A-Line Company Enricher — Deep enrichment for pending companies.

Trigger: All companies with enrichment_status='pending'
Flow:
  1. Basics: Domain, industry, founding year, HQ (website scrape)
  2. Headcount: Apollo Organizations API
  3. Funding: Apollo org data + signals from DB
  4. Revenue estimate: Claude (headcount + industry + funding)
  5. Decision makers: Apollo People Search — C-Level, Board, HR-Leads
  6. Key employees: Apollo People Search — VP+, Head of, Director
  7. Tech Stack: HTML analysis
  8. All open roles: Check DB for hot roles at same company
  9. Claude synthesis: Summarize, set arteq_fit, write company_dossier
  10. Set enrichment_status='complete'

Usage: python -m enrichment.company_enricher
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("company_enricher")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

# Modern tech stack indicators (from company_discovery.py)
MODERN_TECH_SIGNALS = {
    "high_fit": [
        "React", "Next.js", "Vue.js", "Nuxt", "Angular", "TypeScript",
        "Kubernetes", "Docker", "AWS", "Google Cloud", "Azure",
        "Terraform", "Datadog", "Segment", "Mixpanel", "Amplitude",
        "Stripe", "HubSpot", "Salesforce", "Intercom",
        "GraphQL", "Node.js", "Python", "Go", "Rust",
    ],
    "low_fit": [
        "jQuery", "WordPress", "Joomla", "Drupal", "Wix", "Squarespace",
    ],
}


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


def log_apollo_credit(company_id, action, credits=1):
    """Track Apollo credit usage."""
    supabase_request("POST", "apollo_credit_ledger", data={
        "entity_type": "company",
        "entity_id": str(company_id),
        "action": action,
        "credits": credits,
    })


def get_apollo_budget():
    """Check remaining Apollo credit budget for the month."""
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    result = supabase_request("GET", "apollo_credit_ledger", params={
        "select": "credits",
        "created_at": f"gte.{month_start}T00:00:00Z",
    })
    used = sum(r["credits"] for r in (result or []))

    # Get budget from agent_config
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

def enrich_via_apollo_org(domain):
    """Fetch organization data from Apollo."""
    if not APOLLO_API_KEY or not domain:
        return None

    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/organizations/enrich",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_API_KEY,
            },
            json={"domain": domain},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("organization", {})
    except Exception as e:
        logger.error(f"Apollo org error for {domain}: {e}")
        return None


def search_apollo_people(company_name, titles, domain=None, per_page=5):
    """Search for people at a company via Apollo."""
    if not APOLLO_API_KEY:
        return []

    payload = {
        "person_titles": titles,
        "q_organization_name": company_name,
        "page": 1,
        "per_page": per_page,
    }
    if domain:
        payload["q_organization_domains"] = domain

    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_API_KEY,
            },
            json=payload,
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        people = resp.json().get("people", [])
        results = []
        for p in people:
            name = p.get("name", "")
            if not name or len(name) < 2:
                continue
            results.append({
                "name": name,
                "title": p.get("title", ""),
                "linkedin_url": p.get("linkedin_url", ""),
                "apollo_id": p.get("id", ""),
                "email": p.get("email"),
                "phone": None,
                "source": "apollo_search",
            })
        return results
    except Exception as e:
        logger.error(f"Apollo people search error: {e}")
        return []


def analyze_tech_stack(domain):
    """Analyze a company's tech stack by checking HTTP headers and HTML patterns."""
    if not domain:
        return None

    url = f"https://{domain}" if not domain.startswith("http") else domain
    tech_detected = []

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; A-LineBot/1.0)",
        }, allow_redirects=True)

        html = resp.text[:50000].lower()
        headers_str = str(resp.headers).lower()

        tech_checks = {
            "React": ["react", "reactdom", "__next", "/_next/"],
            "Next.js": ["__next", "/_next/", "nextjs"],
            "Vue.js": ["vue.js", "vuejs", "__vue", "nuxt"],
            "Angular": ["ng-version", "angular", "ng-app"],
            "WordPress": ["wp-content", "wp-includes", "wordpress"],
            "Shopify": ["shopify", "cdn.shopify"],
            "HubSpot": ["hubspot", "hs-scripts", "hbspt"],
            "Intercom": ["intercom", "intercomcdn"],
            "Segment": ["segment.com/analytics", "analytics.js", "cdn.segment"],
            "Stripe": ["stripe.com", "js.stripe"],
            "Google Analytics": ["google-analytics", "gtag", "googletagmanager"],
            "Mixpanel": ["mixpanel"],
            "Salesforce": ["salesforce", "pardot"],
            "Cloudflare": ["cloudflare"],
            "AWS": ["amazonaws.com"],
            "Google Cloud": ["googleapis.com", "gstatic"],
            "Sentry": ["sentry.io", "sentry-trace"],
        }

        for tech, patterns in tech_checks.items():
            for pattern in patterns:
                if pattern in html or pattern in headers_str:
                    tech_detected.append(tech)
                    break

    except Exception as e:
        logger.debug(f"Tech stack check failed for {domain}: {e}")
        return None

    if not tech_detected:
        return None

    high_fit = [t for t in tech_detected if t in MODERN_TECH_SIGNALS["high_fit"]]
    low_fit = [t for t in tech_detected if t in MODERN_TECH_SIGNALS["low_fit"]]

    if low_fit and not high_fit:
        tech_fit = "low"
    elif len(high_fit) >= 3:
        tech_fit = "high"
    elif high_fit:
        tech_fit = "medium"
    else:
        tech_fit = "unknown"

    return {
        "technologies": tech_detected,
        "tech_fit": tech_fit,
    }


def upsert_contact(person, company_id, is_decision_maker=False):
    """Insert or update a contact and link to company."""
    if not person.get("name"):
        return None

    # Check existing by linkedin_url or name
    existing = None
    if person.get("linkedin_url"):
        existing = supabase_request("GET", "contact", params={
            "linkedin_url": f"eq.{person['linkedin_url']}",
            "select": "id",
            "limit": "1",
        })
    if not existing:
        existing = supabase_request("GET", "contact", params={
            "name": f"eq.{person['name']}",
            "select": "id",
            "limit": "1",
        })

    contact_data = {k: v for k, v in {
        "name": person["name"],
        "title": person.get("title", ""),
        "linkedin_url": person.get("linkedin_url", ""),
        "email": person.get("email"),
        "phone": person.get("phone"),
        "source": person.get("source", "apollo_search"),
        "enrichment_status": "pending",
    }.items() if v is not None}

    if existing and len(existing) > 0:
        contact_id = existing[0]["id"]
        update = {k: v for k, v in {
            "email": person.get("email"),
            "phone": person.get("phone"),
            "linkedin_url": person.get("linkedin_url"),
            "title": person.get("title"),
        }.items() if v}
        if update:
            supabase_request("PATCH", f"contact?id=eq.{contact_id}", data=update)
    else:
        result = supabase_request("POST", "contact", data=contact_data)
        if result and len(result) > 0:
            contact_id = result[0]["id"]
        else:
            return None

    # Link to company
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
            "role_at_company": person.get("title", ""),
            "is_decision_maker": is_decision_maker,
        })

    return contact_id


# ═══════════════════════════════════════════════════════════
# MAIN ENRICHMENT FLOW
# ═══════════════════════════════════════════════════════════

def enrich_company(company):
    """Full enrichment pipeline for a single company."""
    company_id = company["id"]
    company_name = company["name"]
    domain = (company.get("domain") or "").replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] or None

    logger.info(f"\nEnriching: {company_name} ({domain or 'no domain'})")

    # Mark as enriching
    supabase_request("PATCH", f"company?id=eq.{company_id}", data={
        "enrichment_status": "enriching",
    })

    enrichment_data = {}
    contacts_found = 0

    # ── 1. Apollo Organization Enrichment ──
    if domain and APOLLO_API_KEY:
        org = enrich_via_apollo_org(domain)
        if org:
            enrichment_data["headcount"] = str(org.get("estimated_num_employees", "")) or None
            enrichment_data["industry"] = org.get("industry") or company.get("industry")
            enrichment_data["founded_year"] = org.get("founded_year")
            enrichment_data["hq_city"] = org.get("city")

            funding = org.get("total_funding")
            if funding:
                enrichment_data["funding_amount"] = f"${funding:,.0f}" if isinstance(funding, (int, float)) else str(funding)

            logger.info(f"  Apollo org: headcount={enrichment_data.get('headcount')}, industry={enrichment_data.get('industry')}")
            log_apollo_credit(company_id, "org_enrich", 0)  # Org enrichment is free
        time.sleep(0.5)

    # ── 2. Decision Makers (Apollo People Search) ──
    budget = get_apollo_budget()
    if APOLLO_API_KEY and budget > 10:
        dm_titles = ["CEO", "Geschäftsführer", "COO", "CFO", "CTO", "CHRO",
                      "Managing Director", "Founder", "Co-Founder",
                      "Board Member", "Vorstand"]
        dm_results = search_apollo_people(company_name, dm_titles, domain, per_page=5)
        for person in dm_results:
            cid = upsert_contact(person, company_id, is_decision_maker=True)
            if cid:
                contacts_found += 1
        logger.info(f"  Decision makers: {len(dm_results)} found")
        log_apollo_credit(company_id, "people_search_dm", 1)
        time.sleep(0.5)

        # ── 3. Key Employees (VP+, Head of, Director) ──
        key_titles = ["VP Finance", "VP Operations", "VP Engineering", "VP People",
                       "Head of Finance", "Head of People", "Head of Engineering",
                       "Head of HR", "Head of Operations", "Director of Finance",
                       "Personalleiter", "Kaufmännischer Leiter"]
        key_results = search_apollo_people(company_name, key_titles, domain, per_page=5)
        for person in key_results:
            cid = upsert_contact(person, company_id, is_decision_maker=False)
            if cid:
                contacts_found += 1
        logger.info(f"  Key employees: {len(key_results)} found")
        log_apollo_credit(company_id, "people_search_key", 1)
        time.sleep(0.5)

    # ── 4. Tech Stack Analysis ──
    if domain:
        tech = analyze_tech_stack(domain)
        if tech:
            enrichment_data["tech_stack"] = ", ".join(tech["technologies"][:8])
            logger.info(f"  Tech stack: {', '.join(tech['technologies'][:5])} → {tech['tech_fit']} fit")

    # ── 5. Gather existing intel from DB ──
    roles = supabase_request("GET", "role", params={
        "company_id": f"eq.{company_id}",
        "select": "title,tier,is_hot,engagement_type,role_function,status",
        "status": "neq.expired",
        "limit": "20",
    }) or []

    signals = supabase_request("GET", "signal", params={
        "company_id": f"eq.{company_id}",
        "select": "type,title,relevance_score,urgency,is_hot,interim_relevance",
        "order": "detected_at.desc",
        "limit": "15",
    }) or []

    contacts = supabase_request("GET", "company_contact", params={
        "company_id": f"eq.{company_id}",
        "select": "is_decision_maker,role_at_company,contact:contact_id(name,title,email)",
    }) or []

    # ── 6. Claude Synthesis ──
    context = f"Company: {company_name}\n"
    context += f"Domain: {domain or '?'}\n"
    context += f"Industry: {enrichment_data.get('industry', company.get('industry', '?'))}\n"
    context += f"Headcount: {enrichment_data.get('headcount', company.get('headcount', '?'))}\n"
    context += f"Funding: {enrichment_data.get('funding_amount', company.get('funding_amount', '?'))}\n"
    context += f"Founded: {enrichment_data.get('founded_year', '?')}\n"
    context += f"HQ: {enrichment_data.get('hq_city', company.get('hq_city', '?'))}\n"
    context += f"Tech Stack: {enrichment_data.get('tech_stack', '?')}\n\n"

    if roles:
        context += f"Open Roles ({len(roles)}):\n"
        for r in roles[:10]:
            context += f"  - {r['title']} [{r.get('tier', '?')}/{r.get('engagement_type', '?')}] {'HOT' if r.get('is_hot') else ''}\n"

    if signals:
        context += f"\nSignals ({len(signals)}):\n"
        for s in signals[:10]:
            context += f"  - [{s.get('type')}] {s.get('title', '')[:60]} (urgency: {s.get('urgency', '?')}) {'HOT' if s.get('is_hot') else ''}\n"

    if contacts:
        context += f"\nContacts ({len(contacts)}):\n"
        for c in contacts[:5]:
            ci = c.get("contact", {})
            dm = " [DM]" if c.get("is_decision_maker") else ""
            context += f"  - {ci.get('name', '?')} ({ci.get('title', '?')}){dm} {'email' if ci.get('email') else ''}\n"

    prompt = f"""You are the AI agent for A-Line, a DACH-focused Fractional/Interim Executive placement firm.

Create a company assessment:

{context}

Respond in JSON:
{{
  "composite_score": 0-100,
  "arteq_fit": "high|medium|low",
  "revenue_estimate": "estimated revenue based on headcount + industry + funding",
  "summary": "2-3 sentences: What does the company do, why is it relevant for A-Line?",
  "recommended_status": "lead|prospect|active",
  "outreach_priority": 1-10,
  "dossier_html": "<h3>Company Dossier: [Name]</h3><p><strong>Industry:</strong> ... <strong>HQ:</strong> ... <strong>Status:</strong> ...</p><h4>Open Role Analysis</h4><p>...</p><h4>Why A-Line?</h4><ul><li>...</li></ul><h4>Next Steps</h4><ul><li>...</li></ul>"
}}

Scoring criteria:
- Hot Roles + Interim/Fractional signal → high fit
- Series A+ Funding + rapid growth → likely need leadership
- C-Level departure + no replacement → urgent
- Decision maker with email available → outreach-ready (bonus)
- Agency/consultancy → low fit (low score)

IMPORTANT: Write ALL dossier_html content in English."""

    text = claude_request(prompt, max_tokens=1500)
    if text:
        try:
            synthesis = json.loads(clean_json_response(text))

            enrichment_data["composite_score"] = synthesis.get("composite_score", 0)
            enrichment_data["arteq_fit"] = synthesis.get("arteq_fit", "unknown")
            enrichment_data["outreach_priority"] = synthesis.get("outreach_priority")

            new_status = synthesis.get("recommended_status", "lead")
            old_status = company.get("status", "lead")
            if new_status != old_status:
                if (old_status == "lead" and new_status in ("prospect", "active")) or \
                   (old_status == "prospect" and new_status == "active"):
                    enrichment_data["status"] = new_status

            # Remove previous enrichment dossier (avoid duplicates on re-runs)
            supabase_request("DELETE", "company_dossier",
                params={"company_id": f"eq.{company_id}", "source": "eq.company_enricher"})

            # Write dossier
            supabase_request("POST", "company_dossier", data={
                "company_id": company_id,
                "entry_type": "agent_action",
                "title": f"Company Enrichment — Score: {synthesis.get('composite_score', 0)}/100",
                "content": synthesis.get("dossier_html", synthesis.get("summary", "")),
                "source": "company_enricher",
                "author": "A-Line Agent",
            })

            logger.info(f"  Claude synthesis: score={synthesis.get('composite_score')}, fit={synthesis.get('arteq_fit')}")

        except json.JSONDecodeError as e:
            logger.error(f"  Claude JSON parse error: {e}")

    # ── 7. Update company record ──
    update_data = {k: v for k, v in enrichment_data.items() if v is not None}
    update_data["enrichment_status"] = "complete"
    update_data["last_orchestrator_eval"] = datetime.now(timezone.utc).isoformat()

    supabase_request("PATCH", f"company?id=eq.{company_id}", data=update_data)

    logger.info(f"  Enrichment complete: {company_name} (contacts: {contacts_found})")
    return True


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run():
    """Run enrichment for all pending companies."""
    logger.info("=" * 60)
    logger.info("A-Line Company Enricher — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Get pending companies
    companies = supabase_request("GET", "company", params={
        "select": "id,name,domain,industry,funding_stage,headcount,status,hq_city,funding_amount",
        "enrichment_status": "eq.pending",
        "order": "created_at.desc",
        "limit": "20",
    })

    if not companies:
        logger.info("No pending companies to enrich — done")
        return

    logger.info(f"Found {len(companies)} companies to enrich")

    budget = get_apollo_budget()
    logger.info(f"Apollo budget remaining: {budget} credits")

    enriched = 0
    for company in companies:
        if get_apollo_budget() < 5:
            logger.warning("Apollo budget too low — stopping enrichment")
            break

        try:
            if enrich_company(company):
                enriched += 1
        except Exception as e:
            logger.error(f"Error enriching {company['name']}: {e}")
            # Mark as failed but don't block others
            supabase_request("PATCH", f"company?id=eq.{company['id']}", data={
                "enrichment_status": "pending",  # Will retry next run
            })

        time.sleep(1)

    logger.info("=" * 60)
    logger.info(f"COMPANY ENRICHER SUMMARY: {enriched}/{len(companies)} enriched")
    logger.info("=" * 60)


def main():
    run()


if __name__ == "__main__":
    main()
