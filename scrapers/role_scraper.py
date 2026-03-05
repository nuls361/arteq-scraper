#!/usr/bin/env python3
"""
A-Line Role Scraper — Consolidated multi-source pipeline.

Sources: JSearch (Google for Jobs), Arbeitnow
Flow: Scrape → Dedup → Claude Qualification Scoring (0-100) → Tier Mapping → Write to DB → Trigger enrichment

Usage: python -m scrapers.role_scraper
Schedule: 06:00 UTC (07:00 CET)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("role_scraper")

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")

# ── Blacklists ──

EXCLUDED_COMPANIES = [
    # Big staffing / recruitment
    "hays", "robert half", "michael page", "page group",
    "kienbaum", "spencer stuart", "randstad", "adecco",
    "manpower", "brunel", "gulp", "amadeus fire", "dis ag",
    "jobot", "insight global", "robert walters",
    # Big 4 / MBB consulting
    "mckinsey", "bcg", "bain", "deloitte", "pwc", "kpmg", "ey",
    "accenture", "ernst & young",
    # DACH interim management agencies (competitors)
    "atreus", "finatal", "evolution consulting", "jan pethe",
    "ocm consulting", "morgan philips", "ad idem", "papeve",
    "butterflymanager", "interim-x", "bridge imp", "taskforce",
    "aurum interim", "interim partners", "board search",
    "hunting/her", "boyden", "egon zehnder", "odgers berndtson",
    "signium", "rochus mummert", "heads!", "mercuri urval",
    "frederickson partners", "russell reynolds", "the interim group",
    "ef interim", "contagi interim", "tema consulting",
    "cfo centre", "the cfo centre", "cfos2go",
    "personalberatung", "executive search", "interim management gmbh",
    "interim-management", "recruiting gmbh", "headhunter",
]

EXCLUDED_TITLES = [
    "intern ", "internship", "praktikum", "werkstudent",
    "junior", "assistant to", "working student", "trainee",
]

DACH_SIGNALS = [
    "germany", "deutschland", "austria", "österreich", "switzerland", "schweiz",
    "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln",
    "düsseldorf", "stuttgart", "vienna", "wien", "zurich", "zürich",
    "leipzig", "dresden", "hannover", "nürnberg", "dortmund", "essen", "bremen",
    "graz", "salzburg", "bern", "basel", "magdeburg", "heidelberg", "potsdam",
    "lübeck", "aalen", "starnberg", "ludwigshafen", "bochum", "freiburg",
    "karlsruhe", "mannheim", "bonn", "wiesbaden", "mainz", "augsburg",
]

JSEARCH_QUERIES = [
    "Interim CFO in Germany",
    "Interim CTO in Germany",
    "Fractional CFO in Germany",
    "Interim Geschäftsführer in Deutschland",
    "Interim Head of Finance in Germany",
    "CFO in Berlin",
    "CTO Startup in Berlin",
    "Head of Finance in Berlin",
    "Head of People in Berlin",
    "CFO in München",
    "Head of Finance in Munich",
    "COO Startup in Germany",
    "VP Finance in Germany",
    "Head of Engineering in Berlin",
    "Head of Operations in Germany",
]

ARBEITNOW_KEYWORDS = [
    "cfo", "cto", "coo", "interim", "fractional",
    "head of finance", "head of people", "head of operations",
    "vp finance", "geschäftsführer", "finance director",
    "chief financial", "chief technology", "chief operating",
]


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def safe(val, default=""):
    return val if val is not None else default


def is_dach(location):
    loc = safe(location).lower()
    return any(s in loc for s in DACH_SIGNALS)


def is_excluded(company, title):
    c = safe(company).lower()
    t = safe(title).lower()
    if any(ex in c for ex in EXCLUDED_COMPANIES):
        return True
    if any(ex in t for ex in EXCLUDED_TITLES):
        return True
    return False


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


# ═══════════════════════════════════════════════════════════
# SOURCE 1: JSearch (Google for Jobs)
# ═══════════════════════════════════════════════════════════

def scrape_jsearch():
    """JSearch API — Google for Jobs wrapper."""
    if not JSEARCH_API_KEY:
        logger.warning("JSearch: No API key, skipping")
        return []

    headers = {
        "X-RapidAPI-Key": JSEARCH_API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    jobs = []
    consecutive_429s = 0

    for query in JSEARCH_QUERIES:
        if consecutive_429s >= 3:
            logger.warning(f"JSearch: {consecutive_429s} consecutive 429s — quota exceeded, stopping")
            break

        for attempt in range(4):
            try:
                resp = requests.get(
                    "https://jsearch.p.rapidapi.com/search",
                    headers=headers,
                    params={"query": query, "page": "1", "num_pages": "1",
                            "date_posted": "month", "country": "de"},
                    timeout=20,
                )
                if resp.status_code == 429:
                    wait = 5 * (2 ** attempt)
                    logger.warning(f"JSearch 429 for '{query}' — retry {attempt+1}/3 in {wait}s")
                    consecutive_429s += 1
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                consecutive_429s = 0
                data = resp.json()
                for raw in data.get("data") or []:
                    company = safe(raw.get("employer_name"), "Unknown")
                    title = safe(raw.get("job_title"), "Unknown")
                    if is_excluded(company, title):
                        continue

                    city = safe(raw.get("job_city"))
                    state = safe(raw.get("job_state"))
                    country = safe(raw.get("job_country"))
                    remote = raw.get("job_is_remote", False) or False
                    loc = ", ".join(p for p in [city, state, country] if p)
                    if remote:
                        loc += " (Remote)" if loc else "Remote"

                    if not is_dach(loc) and country not in ("DE", "AT", "CH"):
                        continue

                    jobs.append({
                        "company": company,
                        "title": title,
                        "location": loc,
                        "is_remote": remote,
                        "description": safe(raw.get("job_description")),
                        "url": safe(raw.get("job_apply_link")) or safe(raw.get("job_google_link")),
                        "posted": safe(raw.get("job_posted_at_datetime_utc"))[:10] if raw.get("job_posted_at_datetime_utc") else "",
                        "source": "jsearch",
                    })
                break
            except Exception as e:
                logger.error(f"JSearch error for '{query}': {e}")
                break
        time.sleep(3)

    logger.info(f"JSearch: {len(jobs)} DACH jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# SOURCE 2: Arbeitnow (Free API)
# ═══════════════════════════════════════════════════════════

def scrape_arbeitnow():
    """Arbeitnow Free API — DACH startup jobs from ATS systems."""
    jobs = []
    page = 1
    max_pages = 5
    seen_slugs = set()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.arbeitnow.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    })

    try:
        session.get("https://www.arbeitnow.com/", timeout=10)
    except Exception:
        pass

    while page <= max_pages:
        try:
            url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
            resp = session.get(url, timeout=20)
            if resp.status_code == 403:
                logger.warning(f"Arbeitnow 403 on page {page} — trying without session...")
                resp = requests.get(url, timeout=20, headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                })
                if resp.status_code == 403:
                    logger.error("Arbeitnow blocked (Cloudflare?) — skipping")
                    break
            resp.raise_for_status()
            data = resp.json()

            listings = data.get("data", [])
            if not listings:
                break

            for raw in listings:
                slug = raw.get("slug", "")
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                company = safe(raw.get("company_name"), "Unknown")
                title = safe(raw.get("title"), "Unknown")
                location = safe(raw.get("location"), "")
                remote = raw.get("remote", False)
                description = safe(raw.get("description"), "")
                tags = raw.get("tags", []) or []

                if is_excluded(company, title):
                    continue

                t_lower = title.lower()
                d_lower = description.lower()
                tag_str = " ".join(t.lower() for t in tags)
                combined = f"{t_lower} {d_lower} {tag_str}"

                if not any(kw in combined for kw in ARBEITNOW_KEYWORDS):
                    continue

                if not is_dach(location) and not any(c in location.lower() for c in ["de", "at", "ch"]):
                    if "remote" not in location.lower():
                        continue

                if remote:
                    location += " (Remote)" if location else "Remote"

                clean_desc = re.sub(r'<[^>]+>', ' ', description)
                clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

                job_url = raw.get("url", "")
                if not job_url and slug:
                    job_url = f"https://www.arbeitnow.com/view/{slug}"

                created = safe(raw.get("created_at"), "")
                if created:
                    try:
                        created = datetime.fromtimestamp(int(created)).strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        created = str(created)[:10]

                jobs.append({
                    "company": company,
                    "title": title,
                    "location": location,
                    "is_remote": remote,
                    "description": clean_desc[:5000],
                    "url": job_url,
                    "posted": created,
                    "source": "arbeitnow",
                })

            if not data.get("links", {}).get("next"):
                break
            page += 1
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Arbeitnow error page {page}: {e}")
            break

    logger.info(f"Arbeitnow: {len(jobs)} relevant DACH jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# DEDUP
# ═══════════════════════════════════════════════════════════

COMPANY_SUFFIXES = [
    "gmbh", "ag", "ug", "se", "ltd", "inc", "corp", "co.",
    "haftungsbeschränkt", "limited", "corporation", "company",
    "& co", "& co.", "kg", "ohg", "gbr", "e.v.", "sarl", "sas",
]


def normalize_name(name):
    """Normalize company name for dedup."""
    name = name.lower().strip()
    for suffix in COMPANY_SUFFIXES:
        name = re.sub(rf'\b{re.escape(suffix)}\b', '', name)
    return re.sub(r'[^a-z0-9]', '', name)


def detect_role_function(title):
    """Map role title to function for dedup key."""
    from config import FUNCTION_MAP
    t = title.lower()
    for function, keywords in FUNCTION_MAP.items():
        for kw in keywords:
            if kw in t:
                return function
    return "Other"


def dedup_jobs(jobs):
    """Deduplicate against existing roles in DB. Returns new jobs only."""
    if not jobs:
        return []

    # In-batch dedup
    seen = set()
    unique = []
    for job in jobs:
        key = normalize_name(job["company"]) + "_" + detect_role_function(job["title"])
        if key not in seen:
            seen.add(key)
            unique.append(job)

    # Check DB for existing roles (by source_url)
    source_urls = [j["url"] for j in unique if j.get("url")]
    existing_urls = set()

    for i in range(0, len(source_urls), 50):
        batch = source_urls[i:i + 50]
        url_filter = ",".join(batch)
        result = supabase_request("GET", "role", params={
            "select": "source_url",
            "source_url": f"in.({url_filter})",
        })
        if result:
            existing_urls.update(r["source_url"] for r in result if r.get("source_url"))

    new_jobs = [j for j in unique if j.get("url") not in existing_urls]
    dupes = len(jobs) - len(new_jobs)
    logger.info(f"Dedup: {len(new_jobs)} new jobs ({dupes} duplicates removed)")
    return new_jobs


# ═══════════════════════════════════════════════════════════
# QUALIFICATION SCORING
# ═══════════════════════════════════════════════════════════

def score_to_tier(score):
    """Map a 0-100 qualification score to a tier label."""
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    if score >= 5:
        return "park"
    return "disqualified"


def classify_roles(jobs):
    """
    Use Claude to score roles on a 0-100 qualification rubric.
    Scores are mapped to tiers via score_to_tier():
      hot (>=70), warm (40-69), park (5-39), disqualified (<5).
    Disqualified roles are discarded.
    """
    if not ANTHROPIC_KEY or not jobs:
        return []

    classified = []

    # Process in batches of 3 (longer prompt needs more room)
    for i in range(0, len(jobs), 3):
        batch = jobs[i:i + 3]

        roles_text = ""
        for idx, j in enumerate(batch):
            roles_text += f"""
--- Role {idx + 1} ---
Company: {j['company']}
Title: {j['title']}
Location: {j['location']}
Description: {(j.get('description') or '')[:1200]}
Source: {j['source']}
"""

        prompt = f"""You are a role qualification scorer for A-Line, a DACH fractional/interim executive placement firm.

Score each role posting on a 0-100 scale using this rubric:

## Block 1 — Engagement Type (0-55 pts)
- "Interim" or "Übergangs-" explicit in title: 55
- "Fractional" or "Part-time Executive" explicit in title: 50
- Contract/Freelance C-Level (no interim/fractional keyword, but contract language): 35
- Full-time C-Level at startup/scale-up (likely interim need): 25
- Full-time C-Level at established company: 10
- Full-time VP/Head-level at startup/scale-up: 8
- Full-time VP/Head-level at established company: 3
- Non-executive role: 0

## Block 2 — Role Type (0-20 pts)
- CFO / Finance Director / Geschäftsführer (Finance): 20
- COO / Operations Director: 18
- CTO / Engineering Director: 15
- CHRO / CPO / People Director: 12
- VP Finance / VP Operations: 10
- Head of Finance / Head of Operations: 8
- Other Head/Director-level: 5
- Non-leadership role: 0

## Block 3 — Structural Fit (0-15 pts)
- DACH-based (Germany, Austria, Switzerland): 8
- Remote-OK with DACH connection: 5
- Company language is German: 4
- Role mentions startup/scale-up/growth context: 3

## Block 4 — Company Stage (0-12 pts)
- Early-stage startup (<50 employees, pre-Series B): 12
- Scale-up (50-500 employees, Series B+): 10
- Mid-market (500-2000 employees): 6
- Enterprise (2000+ employees): 2

## Deductions & Bonuses
- Agency/staffing company posting (not the actual employer): -100 (disqualify)
- Role is clearly a permanent back-fill with no interim angle: -10
- Urgency signals ("sofort", "immediately", "ASAP"): +5
- Explicit mention of A-Line's core functions (restructuring, M&A, IPO prep, carve-out): +5

## Agency Cap
If the posting company is a recruitment/staffing agency (not the actual employer), cap total score at 8.

## Disqualification (score = 0, is_disqualified = true)
- Intern/Junior/Working Student/Trainee role
- Big 4 / MBB consulting firm posting
- Role is outside DACH with no DACH connection

Also detect:
- engagement_type: "Interim", "Fractional", or "Full-time"
- role_function: Finance, Engineering, People, Operations, Sales, Marketing, Product, General Management, or Other
- role_level: C-Level, VP, Head/Director, or Other

{roles_text}

Respond ONLY in JSON:
{{"roles": [
  {{
    "index": 1,
    "score": 72,
    "is_disqualified": false,
    "score_breakdown": {{
      "engagement_type_pts": 55,
      "role_type_pts": 20,
      "structural_pts": 7,
      "company_stage_pts": 10,
      "deductions_bonuses": -20,
      "agency_capped": false
    }},
    "reason": "1 sentence explaining the score",
    "engagement_type": "Interim",
    "role_function": "Finance",
    "role_level": "C-Level"
  }}
]}}"""

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )

            if resp.status_code != 200:
                logger.error(f"Claude API {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json()
            text = "".join(
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text"
            )
            result = json.loads(clean_json_response(text))

            for cls in result.get("roles", []):
                idx = cls.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    job = batch[idx]
                    score = cls.get("score", 0)
                    is_disqualified = cls.get("is_disqualified", False)

                    if is_disqualified or score < 5:
                        continue  # Discard disqualified roles

                    tier = score_to_tier(score)
                    job["qualification_score"] = score
                    job["score_breakdown"] = cls.get("score_breakdown", {})
                    job["tier"] = tier
                    job["is_hot"] = tier == "hot"
                    job["classification_reason"] = cls.get("reason", "")
                    job["engagement_type"] = cls.get("engagement_type", "Full-time")
                    job["role_function"] = cls.get("role_function", "Other")
                    job["role_level"] = cls.get("role_level", "Other")
                    classified.append(job)

            time.sleep(0.5)

        except json.JSONDecodeError as e:
            logger.error(f"Claude JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Claude error: {type(e).__name__}: {e}")

    hot_count = sum(1 for j in classified if j.get("tier") == "hot")
    warm_count = sum(1 for j in classified if j.get("tier") == "warm")
    park_count = sum(1 for j in classified if j.get("tier") == "park")
    discard_count = len(jobs) - len(classified)
    logger.info(f"Qualified: {hot_count} hot, {warm_count} warm, {park_count} park, {discard_count} discarded")
    return classified


# ═══════════════════════════════════════════════════════════
# WRITE TO SUPABASE
# ═══════════════════════════════════════════════════════════

def upsert_company(company_name, domain=None):
    """Find or create company, return company_id."""
    # Check if exists
    existing = supabase_request("GET", "company", params={
        "name": f"ilike.{company_name}",
        "select": "id",
        "limit": "1",
    })
    if existing and len(existing) > 0:
        return existing[0]["id"]

    # Create new
    result = supabase_request("POST", "company", data={
        "name": company_name,
        "domain": domain,
        "status": "lead",
        "enrichment_status": "pending",
    })
    if result and len(result) > 0:
        logger.info(f"  New company created: {company_name}")
        return result[0]["id"]
    return None


def write_roles(jobs):
    """Write classified roles to Supabase and trigger company upsert for hot roles."""
    if not jobs:
        logger.info("No roles to write")
        return 0

    written = 0
    now = datetime.now(timezone.utc).isoformat()

    for j in jobs:
        company_id = upsert_company(j["company"])
        if not company_id:
            continue

        tier = j.get("tier", "warm")
        score = j.get("qualification_score", 0)

        record = {
            "company_id": company_id,
            "title": j["title"][:500],
            "description": (j.get("description") or "")[:5000],
            "location": j.get("location", ""),
            "is_remote": j.get("is_remote", False),
            "source": j.get("source", "unknown"),
            "source_url": j.get("url", ""),
            "posted_at": j.get("posted") or None,
            "tier": tier,
            "is_hot": j.get("is_hot", False),
            "classification_reason": j.get("classification_reason", ""),
            "engagement_type": j.get("engagement_type", "Full-time"),
            "role_function": j.get("role_function", "Other"),
            "role_level": j.get("role_level", "Other"),
            "qualification_score": score,
            "score_breakdown": json.dumps(j.get("score_breakdown", {})),
            "final_score": score,
            "status": "active",
            "first_seen_at": now,
        }

        result = supabase_request("POST", "role", data=record)
        if result:
            written += 1

            # Hot role → set company enrichment_status to pending
            if j.get("is_hot"):
                supabase_request("PATCH", f"company?id=eq.{company_id}", data={
                    "enrichment_status": "pending",
                    "pipeline_type": "role",
                })
        else:
            logger.warning(f"Failed to write role: {j['title'][:60]} at {j['company']}")

    logger.info(f"Wrote {written}/{len(jobs)} roles to Supabase")
    return written


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("A-Line Role Scraper — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Step 1: Scrape all sources
    jsearch_jobs = scrape_jsearch()
    arbeitnow_jobs = scrape_arbeitnow()

    all_jobs = jsearch_jobs + arbeitnow_jobs
    logger.info(f"Total scraped: {len(all_jobs)} jobs")

    if not all_jobs:
        logger.info("No jobs found — done")
        return

    # Step 2: Dedup
    new_jobs = dedup_jobs(all_jobs)

    if not new_jobs:
        logger.info("No new jobs after dedup — done")
        return

    # Step 3: Claude classification (Hot / Warm / Cold)
    classified = classify_roles(new_jobs)

    if not classified:
        logger.info("No roles classified as hot or warm — done")
        return

    # Step 4: Write to DB
    written = write_roles(classified)

    # Summary
    hot_count = sum(1 for j in classified if j.get("tier") == "hot")
    warm_count = sum(1 for j in classified if j.get("tier") == "warm")
    park_count = sum(1 for j in classified if j.get("tier") == "park")

    logger.info("=" * 60)
    logger.info("ROLE SCRAPER SUMMARY")
    logger.info(f"  JSearch jobs:      {len(jsearch_jobs)}")
    logger.info(f"  Arbeitnow jobs:    {len(arbeitnow_jobs)}")
    logger.info(f"  After dedup:       {len(new_jobs)}")
    logger.info(f"  Hot roles:         {hot_count}")
    logger.info(f"  Warm roles:        {warm_count}")
    logger.info(f"  Park roles:        {park_count}")
    logger.info(f"  Written to DB:     {written}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
