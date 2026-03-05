#!/usr/bin/env python3
"""
Enrich existing hot/warm roles with decision maker contacts via Apollo.
Reads roles + companies from Supabase, finds DMs, writes contacts back.
"""
import os
import sys
import time
import logging
import requests

# Load .env
from pathlib import Path
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def supa_get(table, params=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=HEADERS, timeout=15)
    return r.json() if r.status_code == 200 else []


def supa_post(table, data):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=data, timeout=15)
    return r.json() if r.status_code in (200, 201) else None


def supa_patch(table, params, data):
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=HEADERS, json=data, timeout=15)
    return r.status_code in (200, 201, 204)


def guess_dm_titles(role_title):
    title = (role_title or "").lower()
    if any(k in title for k in ["cfo", "finance", "kaufmännisch"]):
        return ["CEO", "Geschäftsführer", "COO", "Managing Director"]
    if any(k in title for k in ["cto", "engineering", "ai", "tech"]):
        return ["CEO", "Geschäftsführer", "COO", "Founder"]
    if any(k in title for k in ["coo", "operations"]):
        return ["CEO", "Geschäftsführer", "Founder"]
    if any(k in title for k in ["chro", "people", "hr"]):
        return ["CEO", "COO", "Geschäftsführer"]
    if any(k in title for k in ["geschäftsführer", "managing director"]):
        return ["Vorstand", "Chairman", "Board Member"]
    return ["CEO", "Geschäftsführer", "Managing Director", "Founder"]


def search_apollo(company_name, titles, company_domain=None):
    if not APOLLO_API_KEY or not company_name:
        return []
    payload = {
        "person_titles": titles,
        "q_organization_name": company_name,
        "page": 1,
        "per_page": 5,
    }
    if company_domain:
        payload["q_organization_domains"] = company_domain

    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": APOLLO_API_KEY},
            json=payload, timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"  Apollo {resp.status_code}: {resp.text[:200]}")
            return []

        people = resp.json().get("people", [])
        results = []
        for p in people[:5]:
            name = p.get("name", "")
            if not name or len(name) < 2:
                continue
            results.append({
                "name": name,
                "title": p.get("title", titles[0] if titles else ""),
                "linkedin_url": p.get("linkedin_url", ""),
                "apollo_id": p.get("id", ""),
                "source": "apollo_search",
            })
            if len(results) >= 3:
                break
        return results
    except Exception as e:
        logger.error(f"  Apollo search error: {e}")
        return []


def enrich_apollo(apollo_id=None, name=None, domain=None):
    if not APOLLO_API_KEY:
        return None
    payload = {}
    if apollo_id:
        payload["id"] = apollo_id
    elif name and domain:
        parts = name.split(" ", 1)
        payload["first_name"] = parts[0]
        if len(parts) > 1:
            payload["last_name"] = parts[1]
        payload["organization_domain"] = domain
    else:
        return None

    payload["reveal_personal_emails"] = False
    payload["reveal_phone_number"] = True

    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/people/match",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": APOLLO_API_KEY},
            json=payload, timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"  Apollo enrich {resp.status_code}: {resp.text[:200]}")
            return None

        person = resp.json().get("person")
        if not person:
            return None

        return {
            "email": person.get("email"),
            "email_status": person.get("email_status"),
            "phone": (person.get("phone_numbers") or [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
        }
    except Exception as e:
        logger.error(f"  Apollo enrich error: {e}")
        return None


def search_linkedin_ddg(company_name, title_guess):
    """Fallback: Search DuckDuckGo for LinkedIn profile."""
    import re
    if not company_name or not title_guess:
        return None
    title = title_guess.strip().split("/")[0].strip()
    query = f'site:linkedin.com/in "{title}" "{company_name}"'
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://duckduckgo.com/",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        results = re.findall(
            r'href="[^"]*?(https?://\w{0,3}\.?linkedin\.com/in/[^"&?]+)[^"]*"[^>]*>([^<]+)',
            html
        )
        if not results:
            results = re.findall(
                r'(https?://\w{0,3}\.?linkedin\.com/in/[^\s"&?]+).*?<a[^>]*>([^<]+)',
                html, re.DOTALL
            )
        if not results:
            return None
        for linkedin_url, raw_name in results[:5]:
            linkedin_url = linkedin_url.split("&")[0].split("?")[0]
            linkedin_url = re.sub(r'/+$', '', linkedin_url)
            name = raw_name.strip()
            name = re.sub(r'\s*[\|–—-]\s*LinkedIn.*$', '', name, flags=re.IGNORECASE)
            parts = re.split(r'\s*[\|–—-]\s*', name)
            name = parts[0].strip() if parts else name
            if len(name) < 3 or len(name) > 60 or "/" in name or "linkedin" in name.lower():
                continue
            detected_title = title_guess
            if len(parts) > 1:
                detected_title = parts[1].strip()[:100]
            logger.info(f"  → DDG found: {name} ({detected_title}) — {linkedin_url}")
            return {
                "name": name,
                "title": detected_title,
                "linkedin_url": linkedin_url,
                "source": "duckduckgo",
            }
        return None
    except Exception as e:
        logger.warning(f"  DDG search error: {e}")
        return None


def upsert_contact(dm, company_id, is_primary):
    """Insert or update contact, link to company."""
    # Check existing by linkedin_url
    existing = None
    if dm.get("linkedin_url"):
        existing = supa_get("contact", f"linkedin_url=eq.{dm['linkedin_url']}&select=id&limit=1")
    if not existing:
        existing = supa_get("contact", f"name=eq.{dm['name']}&select=id&limit=1") if dm.get("name") else []

    contact_data = {k: v for k, v in {
        "name": dm["name"],
        "title": dm.get("title", ""),
        "linkedin_url": dm.get("linkedin_url", ""),
        "email": dm.get("email"),
        "email_status": dm.get("email_status"),
        "phone": dm.get("phone"),
        "source": dm.get("source", "apollo_search"),
    }.items() if v is not None}

    if existing and len(existing) > 0:
        contact_id = existing[0]["id"]
        update = {k: v for k, v in {
            "email": dm.get("email"),
            "phone": dm.get("phone"),
            "linkedin_url": dm.get("linkedin_url"),
            "title": dm.get("title"),
        }.items() if v}
        if update:
            supa_patch("contact", f"id=eq.{contact_id}", update)
    else:
        result = supa_post("contact", contact_data)
        if result and len(result) > 0:
            contact_id = result[0]["id"]
        else:
            return

    # Link to company
    existing_link = supa_get("company_contact", f"company_id=eq.{company_id}&contact_id=eq.{contact_id}&select=id&limit=1")
    if not existing_link:
        supa_post("company_contact", {
            "company_id": company_id,
            "contact_id": contact_id,
            "role_at_company": dm.get("title", ""),
            "is_decision_maker": is_primary,
        })


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing SUPABASE_URL/SUPABASE_KEY")
        sys.exit(1)
    if not APOLLO_API_KEY:
        print("Missing APOLLO_API_KEY")
        sys.exit(1)

    # Get tiers to enrich (default: hot + warm)
    tiers = sys.argv[1:] if len(sys.argv) > 1 else ["hot", "warm"]
    tier_filter = ",".join(tiers)

    print(f"\n{'='*70}")
    print(f"  A-LINE CONTACT ENRICHMENT — Tiers: {', '.join(tiers)}")
    print(f"  Apollo: ON | Supabase: ON")
    print(f"{'='*70}\n")

    # Load roles for selected tiers
    roles = supa_get("role", f"tier=in.({tier_filter})&select=id,title,company_id&limit=500")
    logger.info(f"Found {len(roles)} roles in tiers: {tier_filter}")

    # Get unique company IDs
    company_ids = list(set(r["company_id"] for r in roles if r.get("company_id")))
    logger.info(f"Across {len(company_ids)} unique companies")

    # Load companies
    companies = {}
    for cid in company_ids:
        data = supa_get("company", f"id=eq.{cid}&select=id,name,domain,website&limit=1")
        if data:
            companies[cid] = data[0]

    # Check which companies already have contacts
    existing_links = supa_get("company_contact", f"company_id=in.({','.join(company_ids)})&select=company_id&limit=1000")
    companies_with_contacts = set(l["company_id"] for l in existing_links)

    companies_to_enrich = [c for cid, c in companies.items() if cid not in companies_with_contacts]
    logger.info(f"Companies needing contacts: {len(companies_to_enrich)} (skipping {len(companies_with_contacts)} already enriched)")

    if not companies_to_enrich:
        print("All companies already have contacts!")
        return

    found = 0
    credits = 0

    for co in companies_to_enrich:
        name = co.get("name", "")
        domain = (co.get("domain") or co.get("website") or "").replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] or None

        # Find matching role title for DM guessing
        role_titles = [r["title"] for r in roles if r["company_id"] == co["id"]]
        dm_titles = guess_dm_titles(role_titles[0] if role_titles else "")

        is_hot = any(r.get("tier") == "hot" for r in roles if r["company_id"] == co["id"])

        logger.info(f"Searching: {name} ({domain or 'no domain'}) — titles: {dm_titles}" + (" [HOT]" if is_hot else ""))

        # Apollo search (free tier may not work)
        dm_list = search_apollo(name, dm_titles, domain)

        # DuckDuckGo LinkedIn fallback
        if not dm_list:
            logger.info(f"  Apollo failed/empty, trying DDG fallback...")
            for t in dm_titles[:2]:
                dm = search_linkedin_ddg(name, t)
                if dm:
                    dm_list = [dm]
                    break
                time.sleep(2)

        if not dm_list:
            logger.info(f"  No contacts found for {name}")
            time.sleep(1)
            continue

        primary = dm_list[0]

        # Enrich primary DM for hot leads (costs 1 credit)
        if is_hot:
            enrichment = enrich_apollo(
                apollo_id=primary.get("apollo_id"),
                name=primary.get("name"),
                domain=domain,
            )
            if enrichment:
                primary["email"] = enrichment.get("email")
                primary["email_status"] = enrichment.get("email_status")
                primary["phone"] = enrichment.get("phone")
                credits += 1
                logger.info(f"  Enriched: {primary['name']} → {primary.get('email', '?')} / {primary.get('phone', '?')}")

        # Write contacts to DB
        for idx, dm in enumerate(dm_list):
            upsert_contact(dm, co["id"], is_primary=(idx == 0))

        found += 1
        logger.info(f"  → {len(dm_list)} contact(s) saved for {name}")
        time.sleep(1.5)

    print(f"\n{'='*70}")
    print(f"  DONE: {found}/{len(companies_to_enrich)} companies enriched")
    print(f"  Apollo credits used: {credits}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
