#!/usr/bin/env python3
"""
Arteq Quick Run v6 — Multi-Source Pipeline
Sources: JSearch, Arbeitnow, Welcome to the Jungle
Usage: python quick_run.py
"""

import requests
import time
import logging
import os
import csv
import json
import re
from datetime import datetime
from urllib.parse import quote

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("arteq")

API_KEY = os.getenv("JSEARCH_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Google Sheets Config ────────────────────────────────────
SHEET_ID = "1gI7MQd9nn6l14f3Pm4_Weftbv_BTVQIFN65s5c7GZbc"
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

# ── Static blacklists ───────────────────────────────────────
EXCLUDED_COMPANIES = [
    # Big staffing / recruitment
    "hays", "robert half", "michael page", "page group",
    "kienbaum", "spencer stuart", "randstad", "adecco",
    "manpower", "brunel", "gulp", "amadeus fire", "dis ag",
    "jobot", "insight global", "robert joseph", "b2bcfo",
    "malloy industries", "robert walters",
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


# ═══════════════════════════════════════════════════════════
# SOURCE 1: JSearch (Google for Jobs)
# ═══════════════════════════════════════════════════════════
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


def scrape_jsearch():
    """JSearch API — Google for Jobs wrapper."""
    if not API_KEY:
        logger.warning("JSearch: No API key, skipping")
        return []

    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    jobs = []
    for query in JSEARCH_QUERIES:
        try:
            resp = requests.get(
                "https://jsearch.p.rapidapi.com/search",
                headers=headers,
                params={"query": query, "page": "1", "num_pages": "1",
                        "date_posted": "month", "country": "de"},
                timeout=20,
            )
            resp.raise_for_status()
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
                    "source": "JSearch",
                })
        except Exception as e:
            logger.error(f"JSearch error for '{query}': {e}")
        time.sleep(1)

    logger.info(f"JSearch: {len(jobs)} DACH jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# SOURCE 2: Arbeitnow (Free API, no key needed)
# ═══════════════════════════════════════════════════════════
ARBEITNOW_KEYWORDS = [
    "cfo", "cto", "coo", "interim", "fractional",
    "head of finance", "head of people", "head of operations",
    "vp finance", "geschäftsführer", "finance director",
    "chief financial", "chief technology", "chief operating",
]


def scrape_arbeitnow():
    """Arbeitnow Free API — DACH startup jobs from ATS systems."""
    jobs = []
    page = 1
    max_pages = 5  # Safety limit
    seen_slugs = set()

    # Use a session with full browser-like headers to avoid Cloudflare 403
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

    # First hit the main page to get cookies
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
                # Fallback: direct request
                resp = requests.get(url, timeout=20, headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                })
                if resp.status_code == 403:
                    logger.error(f"Arbeitnow blocked (Cloudflare?) — skipping")
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

                # Check if this job matches our keywords
                t_lower = title.lower()
                d_lower = description.lower()
                tag_str = " ".join(t.lower() for t in tags)
                combined = f"{t_lower} {d_lower} {tag_str}"

                if not any(kw in combined for kw in ARBEITNOW_KEYWORDS):
                    continue

                # DACH filter
                if not is_dach(location) and not any(c in location.lower() for c in ["de", "at", "ch"]):
                    # Arbeitnow is mostly Germany, but double-check
                    if "remote" not in location.lower():
                        continue

                if remote:
                    location += " (Remote)" if location else "Remote"

                # Clean HTML from description
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
                    "source": "Arbeitnow",
                })

            # Check if there are more pages
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
# SOURCE 3: Jobicy (Free API, no key, Germany filter)
# ═══════════════════════════════════════════════════════════
JOBICY_TAGS = [
    "cfo", "cto", "coo", "finance", "operations",
    "head of", "director", "vp", "chief",
]


def scrape_jobicy():
    """Jobicy Free API — remote jobs with geo filter."""
    jobs = []
    tags_to_search = ["cfo", "cto", "coo", "finance director", "head of finance",
                      "head of operations", "vp finance", "chief"]

    for tag in tags_to_search:
        try:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=50&geo=germany&tag={quote(tag)}"
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Accept": "application/json",
            })
            if resp.status_code != 200:
                logger.debug(f"Jobicy {resp.status_code} for '{tag}'")
                continue

            data = resp.json()
            for raw in data.get("jobs", []):
                company = safe(raw.get("companyName"), "Unknown")
                title = safe(raw.get("jobTitle"), "Unknown")

                if is_excluded(company, title):
                    continue

                # Check relevance
                t_lower = title.lower()
                desc = safe(raw.get("jobDescription") or raw.get("jobExcerpt", ""))
                clean_desc = re.sub(r'<[^>]+>', ' ', desc)
                clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

                geo = safe(raw.get("jobGeo"), "")
                job_type = safe(raw.get("jobType"), "")
                level = safe(raw.get("jobLevel"), "")

                location = geo if geo else "Remote"

                pub_date = safe(raw.get("pubDate"), "")[:10]

                jobs.append({
                    "company": company,
                    "title": title,
                    "location": location,
                    "is_remote": True,
                    "description": clean_desc[:5000],
                    "url": safe(raw.get("url"), ""),
                    "posted": pub_date,
                    "source": "Jobicy",
                })

        except Exception as e:
            logger.debug(f"Jobicy error for '{tag}': {e}")
        time.sleep(0.5)

    logger.info(f"Jobicy: {len(jobs)} relevant jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# SOURCE 4: RemoteOK (Free JSON API, no key)
# ═══════════════════════════════════════════════════════════
def scrape_remoteok():
    """RemoteOK JSON feed — free, no API key needed."""
    jobs = []

    try:
        resp = requests.get("https://remoteok.com/api", timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        if resp.status_code != 200:
            logger.warning(f"RemoteOK: {resp.status_code}")
            return jobs

        data = resp.json()
        # First element is metadata, skip it
        listings = data[1:] if len(data) > 1 else []

        for raw in listings:
            company = safe(raw.get("company"), "Unknown")
            title = safe(raw.get("position"), "Unknown")

            if is_excluded(company, title):
                continue

            # Filter for C-level / leadership roles relevant to Arteq
            # STRICT: Match on TITLE only — description matching catches too much noise
            t_lower = title.lower()

            title_must_match = [
                "cfo", "cto", "coo", "cro", "cmo", "chro", "cpo",
                "chief financial", "chief technology", "chief operating",
                "chief revenue", "chief marketing", "chief people",
                "head of finance", "head of people", "head of operations",
                "head of engineering", "head of hr", "head of product",
                "vp finance", "vp operations", "vp engineering", "vp people",
                "finance director", "director of finance", "director of operations",
                "interim", "fractional",
                "geschäftsführer", "managing director",
            ]
            if not any(kw in t_lower for kw in title_must_match):
                continue

            location = safe(raw.get("location"), "Remote")
            tags = raw.get("tags", []) or []

            # Check if DACH-related (or worldwide remote which is also relevant)
            loc_lower = location.lower()
            tag_str = " ".join(t.lower() for t in tags) if tags else ""

            desc = safe(raw.get("description", ""))
            clean_desc = re.sub(r'<[^>]+>', ' ', desc)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

            pub_date = safe(raw.get("date"), "")[:10]
            job_url = safe(raw.get("url"), "")
            if job_url and not job_url.startswith("http"):
                job_url = f"https://remoteok.com{job_url}"

            jobs.append({
                "company": company,
                "title": title,
                "location": location if location else "Remote",
                "is_remote": True,
                "description": clean_desc[:5000],
                "url": job_url,
                "posted": pub_date,
                "source": "RemoteOK",
            })

    except Exception as e:
        logger.error(f"RemoteOK error: {e}")

    logger.info(f"RemoteOK: {len(jobs)} relevant leadership jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# SCORING & AI ANALYSIS
# ═══════════════════════════════════════════════════════════
def rule_score(title, description, location, is_remote):
    t = safe(title).lower()
    d = safe(description).lower()
    score, signals = 0, []

    # Tier 1: Explicit fractional/interim → very high
    if "fractional" in t or "interim" in t:
        score += 45
        signals.append("fractional/interim in title")

    # Tier 2: C-Level title → high base
    clevel = ["ceo", "cfo", "coo", "cto", "cro", "cmo", "chro", "cpo",
              "geschäftsführer", "managing director"]
    if any(c in t for c in clevel):
        score += 30
        signals.append("C-Level")

    # Tier 3: Head/VP/Director
    leadership = ["head of", "vp ", "vice president", "director of",
                  "finance director", "leiter"]
    if any(l in t for l in leadership):
        score += 20
        signals.append("leadership")

    # Bonus: Flexibility signals in description
    flex_kw = ["part-time", "teilzeit", "3 days", "2 days", "4 days",
               "3 tage", "2 tage", "freelance", "contract", "befristet",
               "6-month", "6 monate", "elternzeitvertretung", "maternity cover",
               "days per week", "tage pro woche", "projekt", "project-based"]
    found = [kw for kw in flex_kw if kw in d]
    if found:
        score += 20
        signals.extend(found[:2])

    # Bonus: DACH location
    if is_dach(location):
        score += 10
        signals.append("DACH")

    # Bonus: Startup signals
    startup_kw = ["startup", "scale-up", "scaleup", "series a", "series b",
                  "series c", "seed", "venture", "funded", "pre-ipo"]
    if any(s in d for s in startup_kw):
        score += 10
        signals.append("startup")

    return score, signals


def claude_analyze(job):
    """Claude AI analysis with agency detection."""
    if not ANTHROPIC_KEY:
        return None

    prompt = f"""Du bist Lead-Qualification-Agent für Arteq, eine DACH-Fractional/Interim-Executive-Vermittlung.

WICHTIG: Arteq ist selbst eine Vermittlung. Wir suchen DIREKTE Mandanten (Firmen die selbst einen Interim/Fractional Executive brauchen), NICHT andere Personalberatungen oder Interim-Management-Agenturen.

Analysiere dieses Jobposting:

Firma: {safe(job.get('company'))}
Titel: {safe(job.get('title'))}
Standort: {safe(job.get('location'))}
Remote: {safe(job.get('is_remote'), False)}
Quelle: {safe(job.get('source'))}

Jobbeschreibung:
{safe(job.get('description'))[:3000]}

Antworte NUR in validem JSON (kein Markdown, keine Backticks):
{{
  "is_agency": true/false,
  "agency_reason": "Falls is_agency=true: Warum? Sonst leer",
  "actual_client": "Falls is_agency=true und erkennbar: Kundenname. Sonst 'unbekannt'",
  "engagement_type": "fractional" | "interim" | "full-time" | "convertible",
  "engagement_reasoning": "Ein Satz",
  "lead_score": 0-100,
  "tier": "hot" | "warm" | "parked",
  "requirements_summary": "3-5 wichtigste Anforderungen kurz",
  "outreach_angle": "Ein konkreter Satz für erste Kontaktaufnahme",
  "decision_maker_guess": "Wahrscheinlicher Hiring Manager Titel",
  "company_stage_guess": "startup | scaleup | growth | established | unknown"
}}

SCORING-REGELN:
- Personalberatung/Interim-Agentur/Headhunter → is_agency=true, lead_score MAX 10, tier="parked"
- Typische Agentur-Signale: "Im Auftrag unseres Kunden", "für unseren Mandanten", "wir suchen für", Firmenname mit "Consulting/Partners/Executive Search/Personalberatung"
- Direkte Firma sucht selbst → normaler Score"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"  Claude API {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if not text.strip():
            return None

        analysis = json.loads(text.strip())

        if analysis.get("is_agency"):
            analysis["lead_score"] = min(analysis.get("lead_score", 0), 10)
            analysis["tier"] = "parked"
            logger.info(f"  → AGENCY: {analysis.get('agency_reason', '')[:50]}")
        else:
            logger.info(f"  → AI: {analysis.get('tier','?')} ({analysis.get('lead_score','?')}) | {analysis.get('engagement_type','?')}")

        return analysis
    except json.JSONDecodeError as e:
        logger.error(f"  Claude JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"  Claude error: {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# COMPANY ENRICHMENT (Agentic Deep Dive)
# ═══════════════════════════════════════════════════════════
def guess_company_domain(company_name, job_url=""):
    """Try to derive company website from job URL or name."""
    # Try to extract domain from job URL
    if job_url:
        # JSearch URLs often contain the company domain
        # Jobicy/RemoteOK link to their own site, less useful
        from urllib.parse import urlparse
        parsed = urlparse(job_url)
        host = parsed.hostname or ""
        # Skip job board domains
        job_boards = ["remoteok.com", "jobicy.com", "arbeitnow.com", "linkedin.com",
                      "indeed.com", "google.com", "glassdoor.com", "welcometothejungle.com",
                      "greenhouse.io", "lever.co", "smartrecruiters.com", "join.com",
                      "recruitee.com", "workable.com", "breezy.hr", "jobs.lever.co",
                      "boards.greenhouse.io", "apply.workable.com"]
        if host and not any(jb in host for jb in job_boards):
            return f"https://{host}"

        # Some job URLs contain company subdomain: jobs.COMPANY.com
        if "greenhouse.io" in host or "lever.co" in host:
            # boards.greenhouse.io/companyname or jobs.lever.co/companyname
            path_parts = parsed.path.strip("/").split("/")
            if path_parts:
                slug = path_parts[0].lower()
                return f"https://www.{slug}.com"

    # Fallback: construct from company name
    clean = company_name.lower().strip()
    clean = re.sub(r'\s*(gmbh|ag|se|inc|ltd|co|corp|ug|sarl|bv|srl)\s*\.?$', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'[^a-z0-9]', '', clean)
    if clean:
        return f"https://www.{clean}.com"
    return ""


def fetch_website_text(url, max_chars=8000):
    """Fetch a website and extract readable text."""
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html",
        }, allow_redirects=True)
        if resp.status_code != 200:
            return None

        html = resp.text
        # Strip scripts, styles, nav
        html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        # Strip all remaining tags
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        logger.debug(f"  Website fetch failed for {url}: {e}")
        return None


def enrich_company(job):
    """Agentic company enrichment — fetch website + Claude deep analysis."""
    if not ANTHROPIC_KEY:
        return None

    company = job.get("company", "Unknown")
    job_url = job.get("url", "")

    # Step 1: Find company website
    domain = guess_company_domain(company, job_url)
    logger.info(f"  🔍 Enriching {company} → {domain}")

    website_text = ""
    actual_url = domain
    if domain:
        website_text = fetch_website_text(domain) or ""
        if not website_text:
            # Try without www
            alt = domain.replace("://www.", "://")
            website_text = fetch_website_text(alt) or ""
            if website_text:
                actual_url = alt

        # Also try /about page
        about_text = ""
        if website_text:
            for about_path in ["/about", "/about-us", "/ueber-uns", "/company"]:
                about_text = fetch_website_text(f"{actual_url.rstrip('/')}{about_path}") or ""
                if about_text and len(about_text) > 200:
                    break

    # Step 2: Claude enrichment
    prompt = f"""Du bist Company-Research-Agent für Arteq, eine DACH-Fractional/Interim-Executive-Vermittlung.

Analysiere diese Firma und extrahiere alle verfügbaren Informationen.

Firma: {company}
Job-Titel der offenen Stelle: {safe(job.get('title'))}
Standort: {safe(job.get('location'))}
Job-Beschreibung: {safe(job.get('description'))[:2000]}

{"Website-Text (Homepage): " + website_text[:4000] if website_text else "Website konnte nicht geladen werden."}

{"About-Seite: " + about_text[:2000] if about_text else ""}

Antworte NUR in validem JSON (kein Markdown, keine Backticks):
{{
  "company_website": "{actual_url}",
  "industry": "Branche der Firma (1-3 Wörter)",
  "company_description": "Was macht die Firma? (1-2 Sätze)",
  "funding_stage": "bootstrapped | pre-seed | seed | series_a | series_b | series_c | late_stage | public | private_equity | unknown",
  "funding_amount": "Falls bekannt: Gesamtfunding in EUR/USD. Sonst 'unknown'",
  "investors": "Bekannte Investoren, komma-getrennt. Sonst 'unknown'",
  "headcount_estimate": "Geschätzte Mitarbeiterzahl (Zahl oder Range wie '50-100')",
  "founded_year": "Gründungsjahr falls erkennbar. Sonst 'unknown'",
  "tech_stack": "Erkennbare Technologien/Produkte, komma-getrennt",
  "hiring_signal": "Warum sucht diese Firma JETZT diesen Executive? Was ist das Problem/die Situation? (1-2 Sätze, konkret!)",
  "urgency": "high | medium | low",
  "urgency_reason": "Warum diese Einschätzung? (1 Satz)",
  "arteq_fit": "high | medium | low",
  "arteq_fit_reason": "Ist das ein guter Arteq-Mandant? Warum? (1 Satz)",
  "decision_maker_title": "Wahrscheinlicher Ansprechpartner-Titel (z.B. CEO, Head of HR, VP People)",
  "key_facts": ["Fakt 1", "Fakt 2", "Fakt 3"]
}}

REGELN:
- Wenn Infos nicht verfügbar → "unknown" statt raten
- Hiring Signal sollte KONKRET sein: "Schnelles Wachstum nach Series B braucht erfahrenen CFO für IPO-Vorbereitung" > "Firma sucht CFO"
- Arteq-Fit = high wenn: Startup/Scaleup, DACH, C-Level/Leadership, kein Big Corp
- Urgency = high wenn: Interim/Fractional in Titel, Elternzeitvertretung, "sofort", funded startup"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"  Enrichment API {resp.status_code}")
            return None

        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if not text.strip():
            return None

        enrichment = json.loads(text.strip())
        logger.info(f"  ✅ {company}: {enrichment.get('industry', '?')} | {enrichment.get('funding_stage', '?')} | ~{enrichment.get('headcount_estimate', '?')} ppl | fit={enrichment.get('arteq_fit', '?')}")
        return enrichment

    except json.JSONDecodeError as e:
        logger.error(f"  Enrichment JSON error: {e}")
        return None
    except Exception as e:
        logger.error(f"  Enrichment error: {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# GOOGLE SHEETS WRITER
# ═══════════════════════════════════════════════════════════
def write_to_sheets(jobs):
    """Write jobs to Google Sheets, sorted into Hot/Warm/Parked tabs."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("gspread not installed. Run: pip install gspread google-auth")
        return False

    if not os.path.exists(CREDENTIALS_FILE):
        logger.error(f"Credentials not found: {CREDENTIALS_FILE}")
        return False

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                   "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(SHEET_ID)
        logger.info("Google Sheets connected ✓")
    except Exception as e:
        logger.error(f"Sheets connection failed: {e}")
        return False

    header = [
        "Score", "Company", "Role", "Location", "Source", "Signals",
        "Agency?", "Requirements", "Engagement Type", "Reasoning",
        "Decision Maker", "Company Stage",
        "Industry", "Funding", "Headcount", "Investors", "Hiring Signal",
        "Arteq Fit", "Company Website",
        "URL", "Posted", "Scraped"
    ]

    scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    tiers = {"Hot": [], "Warm": [], "Parked": []}
    for job in jobs:
        tier = job.get("tier", "Park")
        if tier == "HOT":
            tiers["Hot"].append(job)
        elif tier == "WARM":
            tiers["Warm"].append(job)
        else:
            tiers["Parked"].append(job)

    for tab_name, tab_jobs in tiers.items():
        try:
            try:
                ws = sheet.worksheet(tab_name)
            except Exception:
                ws = sheet.add_worksheet(title=tab_name, rows=500, cols=25)

            existing = ws.get_all_values()
            existing_keys = set()
            if len(existing) > 1:
                for row in existing[1:]:
                    if len(row) >= 3:
                        key = f"{row[1].lower().strip()}_{row[2].lower().strip()[:30]}"
                        existing_keys.add(key)

            # Always ensure header
            if not existing or existing[0] != header:
                if not existing:
                    ws.update('A1', [header])
                elif existing[0][0] != "Score":
                    ws.insert_row(header, 1)
                try:
                    ws.format('A1:V1', {'textFormat': {'bold': True}})
                except Exception:
                    pass

            new_rows = []
            for job in tab_jobs:
                key = f"{job['company'].lower().strip()}_{job['title'].lower().strip()[:30]}"
                if key in existing_keys:
                    continue

                ai = job.get("ai_analysis") or {}
                enr = job.get("enrichment") or {}
                agency_label = f"⚠️ AGENCY: {ai.get('agency_reason', '')[:40]}" if ai.get("is_agency") else ("✅ Direct" if ai else "")

                row = [
                    job["score"], job["company"], job["title"], job["location"],
                    job.get("source", ""), "; ".join(job.get("signals", [])),
                    agency_label,
                    ai.get("requirements_summary", ""),
                    ai.get("engagement_type", ""),
                    ai.get("engagement_reasoning", ""),
                    ai.get("decision_maker_guess", "") or enr.get("decision_maker_title", ""),
                    ai.get("company_stage_guess", "") or enr.get("funding_stage", ""),
                    enr.get("industry", ""),
                    enr.get("funding_amount", "") or enr.get("funding_stage", ""),
                    enr.get("headcount_estimate", ""),
                    enr.get("investors", ""),
                    enr.get("hiring_signal", ""),
                    enr.get("arteq_fit", "") + (f": {enr.get('arteq_fit_reason', '')}" if enr.get("arteq_fit_reason") else ""),
                    enr.get("company_website", ""),
                    job.get("url", ""), job.get("posted", ""),
                    scraped_date,
                ]
                new_rows.append(row)

            if new_rows:
                existing_after = ws.get_all_values()
                start_row = len(existing_after) + 1
                ws.update(f'A{start_row}', new_rows)
                logger.info(f"  {tab_name}: +{len(new_rows)} new leads")
            else:
                logger.info(f"  {tab_name}: No new leads (all duplicates)")

        except Exception as e:
            logger.error(f"  Error writing {tab_name}: {e}")

    return True


# ═══════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════
def main():
    use_ai = bool(ANTHROPIC_KEY)

    print("\n" + "=" * 95)
    print("  ARTEQ JOB SIGNAL SCRAPER v6 — Multi-Source Pipeline")
    print(f"  Sources: JSearch{'✓' if API_KEY else '✗'} | Arbeitnow ✓ | Jobicy ✓ | RemoteOK ✓")
    print(f"  AI Scoring: {'ON ✓' if use_ai else 'OFF'}")
    print(f"  Google Sheets: {'ON ✓' if os.path.exists(CREDENTIALS_FILE) else 'OFF'}")
    print("=" * 95)

    # ── Test Claude ─────────────────────────────────────────
    if use_ai:
        logger.info("Testing Claude API...")
        try:
            test = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Say OK"}]},
                timeout=10,
            )
            if test.status_code == 200:
                logger.info("Claude API: OK ✓")
            else:
                logger.error(f"Claude API {test.status_code} — falling back to rule-based")
                use_ai = False
        except Exception as e:
            logger.error(f"Claude API failed: {e} — falling back to rule-based")
            use_ai = False

    # ── Scrape all sources ──────────────────────────────────
    all_raw = []

    logger.info("\n── SOURCE 1: JSearch ──")
    all_raw.extend(scrape_jsearch())

    logger.info("\n── SOURCE 2: Arbeitnow ──")
    all_raw.extend(scrape_arbeitnow())

    logger.info("\n── SOURCE 3: Jobicy ──")
    all_raw.extend(scrape_jobicy())

    logger.info("\n── SOURCE 4: RemoteOK ──")
    all_raw.extend(scrape_remoteok())

    logger.info(f"\nTotal raw jobs across all sources: {len(all_raw)}")

    if not all_raw:
        print("\n  No results from any source.\n")
        return

    # ── Dedup across sources ────────────────────────────────
    seen = set()
    unique = []
    for job in all_raw:
        key = f"{job['company'].lower().strip()}_{job['title'].lower().strip()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(job)

    logger.info(f"After cross-source dedup: {len(unique)} unique jobs")

    # ── Score all jobs ──────────────────────────────────────
    for job in unique:
        score, signals = rule_score(job["title"], job["description"], job["location"], job["is_remote"])
        job["score"] = score
        job["signals"] = signals
        job["tier"] = "HOT" if score >= 55 else "WARM" if score >= 30 else "Park"
        job["ai_analysis"] = None

    unique.sort(key=lambda x: x["score"], reverse=True)

    # ── AI Analysis ─────────────────────────────────────────
    if use_ai:
        ai_candidates = [j for j in unique if j["score"] >= 20]
        logger.info(f"\nRunning Claude analysis on {len(ai_candidates)} leads...")
        ai_count = 0
        agency_count = 0

        for job in ai_candidates:
            logger.info(f"Analyzing: {job['company']} — {job['title']} [{job['source']}]")
            analysis = claude_analyze(job)
            if analysis:
                job["ai_analysis"] = analysis
                job["score"] = analysis.get("lead_score", job["score"])
                ai_tier = safe(analysis.get("tier")).lower()
                job["tier"] = "HOT" if ai_tier == "hot" else "WARM" if ai_tier == "warm" else "Park"
                ai_count += 1
                if analysis.get("is_agency"):
                    agency_count += 1
            time.sleep(0.5)

        logger.info(f"AI done: {ai_count} analyzed | {agency_count} agencies detected")
        unique.sort(key=lambda x: x["score"], reverse=True)

    # ── Company Enrichment (Agentic) ────────────────────────
    if use_ai:
        # Enrich Hot leads + Warm C-Level leads
        enrich_candidates = [
            j for j in unique
            if not (j.get("ai_analysis") or {}).get("is_agency")
            and (j["tier"] == "HOT" or (j["tier"] == "WARM" and j["score"] >= 40))
        ]
        # Deduplicate by company name (don't enrich same company twice)
        enriched_companies = set()
        enrich_queue = []
        for j in enrich_candidates:
            c = j["company"].lower().strip()
            if c not in enriched_companies:
                enriched_companies.add(c)
                enrich_queue.append(j)

        if enrich_queue:
            logger.info(f"\n🔍 ENRICHING {len(enrich_queue)} companies...")
            for job in enrich_queue:
                enrichment = enrich_company(job)
                if enrichment:
                    job["enrichment"] = enrichment
                    # Apply enrichment to all jobs from same company
                    for j2 in unique:
                        if j2["company"].lower().strip() == job["company"].lower().strip():
                            j2["enrichment"] = enrichment
                time.sleep(0.5)
            logger.info(f"Enrichment done: {sum(1 for j in enrich_queue if j.get('enrichment'))} companies enriched")

    # ── Display ─────────────────────────────────────────────
    real_leads = [j for j in unique if not (j.get("ai_analysis") or {}).get("is_agency")]
    agencies = [j for j in unique if (j.get("ai_analysis") or {}).get("is_agency")]

    # Source breakdown
    sources = {}
    for j in unique:
        s = j.get("source", "?")
        sources[s] = sources.get(s, 0) + 1

    print(f"\n  📊 Source breakdown: {' | '.join(f'{k}: {v}' for k, v in sources.items())}")
    print(f"  📊 Total: {len(unique)} unique | ✅ {len(real_leads)} direct | ⚠️ {len(agencies)} agencies")

    hot_count = len([j for j in real_leads if j["tier"] == "HOT"])
    warm_count = len([j for j in real_leads if j["tier"] == "WARM"])
    park_count = len([j for j in real_leads if j["tier"] == "Park"])
    print(f"  📊 Tiers: 🔴 {hot_count} Hot | 🟡 {warm_count} Warm | ⚪ {park_count} Parked")

    print(f"\n{'='*115}")
    print(f"  {'Tier':6} {'Score':>5}  {'Source':10} {'Company':22} {'Role':30} {'Location':18}")
    print(f"{'='*115}")

    for job in real_leads[:40]:
        tier_icon = {"HOT": "🔴", "WARM": "🟡", "Park": "⚪"}.get(job["tier"], "⚪")
        src = job.get("source", "?")[:8]
        print(f"  {tier_icon} {job['tier']:4} {job['score']:5d}  {src:10} {job['company'][:22]:22} {job['title'][:30]:30} {job['location'][:18]}")

        ai = job.get("ai_analysis")
        enr = job.get("enrichment")

        if enr:
            industry = enr.get("industry", "")
            funding = enr.get("funding_stage", "")
            headcount = enr.get("headcount_estimate", "")
            fit = enr.get("arteq_fit", "")
            print(f"  {'':24}  🏢 {industry} | {funding} | ~{headcount} ppl | fit={fit}")
            signal = enr.get("hiring_signal", "")
            if signal:
                print(f"  {'':24}  🎯 {signal[:90]}")
            investors = enr.get("investors", "")
            if investors and investors != "unknown":
                print(f"  {'':24}  💰 {investors[:70]}")

        if ai:
            req = ai.get("requirements_summary", "")
            if req:
                print(f"  {'':24}  📋 {req[:90]}")
            eng = ai.get("engagement_type", "")
            if eng:
                print(f"  {'':24}  🏷️  {eng}: {ai.get('engagement_reasoning', '')[:65]}")
        elif job["signals"]:
            print(f"  {'':24}  → {', '.join(job['signals'][:4])}")

        if job.get("url"):
            print(f"  {'':24}  🔗 {job['url'][:85]}")
        print()

    if agencies:
        print(f"\n  ⚠️  AGENCIES ({len(agencies)}):")
        for job in agencies[:8]:
            ai = job.get("ai_analysis", {})
            print(f"  ⚠️  {job['company'][:25]:25} {ai.get('agency_reason', '')[:50]}")

    print(f"\n{'='*115}")

    # ── Google Sheets ───────────────────────────────────────
    if os.path.exists(CREDENTIALS_FILE):
        logger.info("Writing to Google Sheets...")
        if write_to_sheets(unique):
            print(f"\n  📊 Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    else:
        logger.info("No credentials.json — skipping Sheets")

    # ── CSV backup ──────────────────────────────────────────
    filename = f"leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Tier", "Score", "Source", "Company", "Role", "Location", "Signals",
            "Agency?", "Agency Reason",
            "Requirements", "Engagement Type", "Reasoning",
            "Decision Maker", "Stage",
            "Industry", "Funding", "Headcount", "Investors",
            "Hiring Signal", "Arteq Fit", "Company Website",
            "URL", "Posted",
        ])
        for job in unique:
            ai = job.get("ai_analysis") or {}
            enr = job.get("enrichment") or {}
            w.writerow([
                job["tier"], job["score"], job.get("source", ""),
                job["company"], job["title"], job["location"],
                "; ".join(job.get("signals", [])),
                "AGENCY" if ai.get("is_agency") else "Direct" if ai else "",
                ai.get("agency_reason", ""),
                ai.get("requirements_summary", ""),
                ai.get("engagement_type", ""), ai.get("engagement_reasoning", ""),
                ai.get("decision_maker_guess", "") or enr.get("decision_maker_title", ""),
                ai.get("company_stage_guess", "") or enr.get("funding_stage", ""),
                enr.get("industry", ""), enr.get("funding_amount", ""),
                enr.get("headcount_estimate", ""), enr.get("investors", ""),
                enr.get("hiring_signal", ""), enr.get("arteq_fit", ""),
                enr.get("company_website", ""),
                job.get("url", ""), job.get("posted", ""),
            ])
    print(f"  💾 CSV: {filename}\n")


if __name__ == "__main__":
    main()
