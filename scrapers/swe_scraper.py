#!/usr/bin/env python3
"""
A-Line SWE Scraper — Standalone CSV-output scraper for SWE roles in low talent density DACH cities.

Sources: JSearch (Google for Jobs), Arbeitnow
Flow: Scrape → City Filter → In-Memory Dedup → Claude Scoring (0-100) → CSV Output

Usage: python -m scrapers.swe_scraper
"""

import csv
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("swe_scraper")

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

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
    "head of", "vp ", "vice president", "director of", "cto", "cpo", "ceo", "cfo",
    # Non-engineering roles that currently pass the filter
    "technischer redakteur", "technical writer",
    "bauleiter", "bau- und", "glasreinigung", "reinigung",
    "personalberater", "personalberatung",
    "steuerfachangestellter", "steuerfachwirt", "bilanzbuchhalter",
    "projektleiter elektrotechnik", "projektleiter fertigung",
    "sachbearbeiter", "versicherung",
    # IT Ops / Sysadmin — not SWE, not placeable as freelance dev
    "it-systemadministrator", "systemadministrator",
    "fachinformatiker systemintegration",
    "it administrator", "it-administrator",
    "system engineer client", "it spezialist",
    # Apprenticeships — "ausbildung" alone misses compound forms
    "ausbildung zum", "ausbildung zur",
    # Inhouse consulting — not good for fractional
    "inhouse berater", "inhouse consultant",
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

# ── SWE Queries ──

SWE_JSEARCH_QUERIES = [
    "Software Engineer in Augsburg",
    "Software Developer in Bielefeld",
    "Software Engineer in Dortmund",
    "Backend Developer in Hannover",
    "Full Stack Developer in Nürnberg",
    "Software Engineer in Bremen",
    "Senior Developer in Mannheim",
    "Software Engineer in Karlsruhe",
    "Backend Engineer in Münster",
    "Software Developer in Bochum",
    "Full Stack Engineer in Wiesbaden",
    "Software Engineer in Graz",
    "Software Developer in Linz",
    "Senior Software Engineer in Innsbruck",
    "Software Engineer in Bern",
    "Backend Developer in St. Gallen",
    "Software Engineer in Bonn",
    "Senior Developer in Aachen",
    "Software Developer in Freiburg",
    "Full Stack Developer in Regensburg",
    "Softwareentwickler in Augsburg",
    "Softwareentwickler in Hannover",
    "Softwareentwickler in Nürnberg",
    "Softwareentwickler in Dortmund",
]

SWE_ARBEITNOW_KEYWORDS = [
    # English titles
    "software engineer", "software developer", "software architect",
    "backend developer", "backend engineer",
    "frontend developer", "frontend engineer",
    "full stack", "fullstack", "full-stack",
    "web developer", "web engineer",
    "mobile developer", "mobile engineer",
    "ios developer", "android developer",
    "cloud engineer", "cloud architect",
    "devops engineer", "devops", "site reliability", "sre",
    "platform engineer", "infrastructure engineer",
    "data engineer", "data platform",
    "ml engineer", "machine learning engineer", "ai engineer",
    "embedded engineer", "embedded developer", "embedded software",
    "systems engineer", "systems developer",
    "security engineer", "appsec",
    "qa engineer", "test engineer", "sdet", "quality engineer",
    "release engineer", "build engineer",
    "developer", "engineer", "programmer", "coder",
    "senior developer", "senior engineer", "lead developer", "lead engineer",
    "staff engineer", "principal engineer",
    # Language/framework-specific
    "python developer", "python engineer",
    "java developer", "java engineer",
    "typescript developer", "javascript developer",
    ".net developer", "c# developer", "c++ developer",
    "golang developer", "go developer", "rust developer",
    "ruby developer", "rails developer",
    "php developer", "laravel developer",
    "react developer", "angular developer", "vue developer",
    "node developer", "nodejs",
    "kotlin developer", "swift developer", "flutter developer",
    # German titles
    "softwareentwickler", "softwareentwicklung",
    "webentwickler", "webentwicklung",
    "entwickler", "programmierer",
    "systemingenieur", "informatiker",
    "it-entwickler", "anwendungsentwickler",
    "fachinformatiker",
]

# ── City Filters ──

LOW_TALENT_DENSITY_CITIES = [
    # ── Deutschland ──────────────────────────────────────────
    # Ruhrgebiet (hohes Potential, niedrige SWE-Dichte)
    "bochum", "bottrop", "dortmund", "duisburg", "essen",
    "gelsenkirchen", "hagen", "hamm", "herne", "mülheim an der ruhr",
    "mülheim", "mulheim", "oberhausen", "recklinghausen",
    # NRW sonstige
    "aachen", "bergisch gladbach", "düren", "duren", "krefeld",
    "leverkusen", "mönchengladbach", "monchengladbach", "moers",
    "neuss", "paderborn", "remscheid", "siegen", "solingen",
    "wuppertal",
    # Niedersachsen / Bremen
    "braunschweig", "bremerhaven", "göttingen", "gottingen",
    "hannover", "oldenburg", "osnabrück", "osnabruck", "wolfsburg",
    "bremen",
    # Bayern sonstige
    "augsburg", "erlangen", "fürth", "furth", "ingolstadt",
    "nürnberg", "nuremberg", "regensburg", "würzburg", "wurzburg",
    # Baden-Württemberg sonstige
    "freiburg", "heidelberg", "heilbronn", "karlsruhe", "mainz",
    "mannheim", "reutlingen", "ulm",
    # Hessen sonstige
    "darmstadt", "giessen", "gießen", "kassel", "wiesbaden",
    # Mitteldeutschland
    "bernburg", "chemnitz", "cottbus", "erfurt", "halle", "jena",
    "magdeburg", "rostock",
    # Sonstige
    "bielefeld", "bonn", "kiel", "koblenz", "kaiserslautern",
    "lübeck", "lubeck", "münster", "munster", "saarbrücken",
    "saarbrucken", "trier",

    # ── Österreich (außerhalb Wien) ───────────────────────────
    "graz", "innsbruck", "klagenfurt", "linz", "salzburg",
    "steyr", "wels",

    # ── Schweiz (außerhalb Zürich / Basel / Genf) ────────────
    "bern", "biel", "bienne", "frauenfeld", "luzern",
    "schaffhausen", "solothurn", "st. gallen", "st gallen",
    "thun", "winterthur", "zug",
]

HIGH_TALENT_DENSITY_EXCLUDE = [
    "berlin", "münchen", "munich", "hamburg", "frankfurt",
    "köln", "cologne", "koln", "stuttgart", "zürich", "zurich",
    "basel", "wien", "vienna", "geneva", "genf",
    "potsdam",
]


def is_low_talent_city(location: str) -> bool:
    loc = (location or "").lower()
    if any(c in loc for c in HIGH_TALENT_DENSITY_EXCLUDE):
        return False
    return any(c in loc for c in LOW_TALENT_DENSITY_CITIES)


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

    for query in SWE_JSEARCH_QUERIES:
        if consecutive_429s >= 3:
            logger.warning(f"JSearch: {consecutive_429s} consecutive 429s — quota exceeded, stopping")
            break

        for attempt in range(4):
            try:
                resp = requests.get(
                    "https://jsearch.p.rapidapi.com/search",
                    headers=headers,
                    params={"query": query, "page": "1", "num_pages": "1",
                            "date_posted": "month", "country": "de",
                            "employment_types": "FULLTIME"},
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

                    if not is_low_talent_city(loc):
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

    logger.info(f"JSearch: {len(jobs)} low-density city SWE jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# SOURCE 2: Arbeitnow (Free API)
# ═══════════════════════════════════════════════════════════

def scrape_arbeitnow():
    """Arbeitnow Free API — DACH startup jobs from ATS systems."""
    jobs = []
    page = 1
    max_pages = 50
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

    consecutive_429s = 0

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
            if resp.status_code == 429:
                consecutive_429s += 1
                if consecutive_429s >= 3:
                    logger.warning("Arbeitnow: 3 consecutive 429s — stopping")
                    break
                wait = 10 * (2 ** (consecutive_429s - 1))
                logger.warning(f"Arbeitnow 429 on page {page} — backing off {wait}s (retry {consecutive_429s}/3)")
                time.sleep(wait)
                continue  # retry same page
            resp.raise_for_status()
            consecutive_429s = 0
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

                if not any(kw in combined for kw in SWE_ARBEITNOW_KEYWORDS):
                    continue

                if not is_dach(location) and not any(c in location.lower() for c in ["de", "at", "ch"]):
                    if "remote" not in location.lower():
                        continue

                if not is_low_talent_city(location):
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
            time.sleep(2.5)

        except Exception as e:
            logger.error(f"Arbeitnow error page {page}: {e}")
            break

    logger.info(f"Arbeitnow: {len(jobs)} relevant low-density city SWE jobs found")
    return jobs


# ═══════════════════════════════════════════════════════════
# DEDUP (In-Memory)
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


def dedup_jobs(jobs):
    """In-memory dedup on URL and company+title key."""
    if not jobs:
        return []

    seen_urls = set()
    seen_keys = set()
    unique = []

    for job in jobs:
        url = job.get("url", "")
        if url and url in seen_urls:
            continue

        key = normalize_name(job["company"]) + "_" + normalize_name(job["title"])
        if key in seen_keys:
            continue

        if url:
            seen_urls.add(url)
        seen_keys.add(key)
        unique.append(job)

    dupes = len(jobs) - len(unique)
    logger.info(f"Dedup: {len(unique)} unique jobs ({dupes} duplicates removed)")
    return unique


# ═══════════════════════════════════════════════════════════
# SWE SCORING
# ═══════════════════════════════════════════════════════════

def score_to_tier(score):
    """Map a 0-100 score to a tier label."""
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    if score >= 5:
        return "park"
    return "disqualified"


def score_swe_roles(jobs):
    """
    Use Claude to score SWE roles on a 0-100 freelance-openness rubric.
    Extracts tech_stack, urgency_signals, company_size_signal, seniority_level.
    """
    if not ANTHROPIC_KEY or not jobs:
        return []

    scored = []

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

        prompt = f"""You score job postings for A-Line, a DACH platform that places
freelance/contractor software engineers and tech specialists at companies
that struggle to hire locally.

TARGET ROLES: Software engineers, backend/frontend/fullstack developers,
DevOps engineers, platform engineers, security engineers,
embedded/firmware engineers, data engineers, ML engineers.

NOT TARGET: IT sysadmins, IT infrastructure, technical writers, project
managers, business analysts, accounting, HR, construction, facilities.

Score 0-100 on how likely this company is OPEN to a freelance/contractor:

+30 pts: Role is in a low talent density city (not Berlin/Munich/Hamburg/
         Frankfurt/Zurich/Vienna/Potsdam)
+20 pts: Senior or specialist with niche/rare tech stack
+20 pts: Security engineer role — high freelance placement rate
+15 pts: Startup or scale-up context (fast growth, small team, Series A/B)
+15 pts: Urgency signals ("sofort", "ASAP", "immediately", "dringend",
         "schnellstmöglich", "nächstmöglichen Zeitpunkt", "ab sofort")
+10 pts: Small team context (<50 employees mentioned or implied)
+10 pts: Niche/rare tech stack very hard to find locally
+10 pts: Maritime, industrial, or embedded systems context — niche talent pool
-10 pts: "Inhouse" in title or description (inhouse roles rarely go fractional)
-10 pts: Defence/Verteidigung/military context — access and clearance barriers
-15 pts: IT infrastructure/ops role (sysadmin, network, endpoint management)
         rather than pure software development
-20 pts: Large enterprise/corporate (>2000 employees)
-30 pts: Staffing/recruitment agency posting

Disqualify (score=0, is_disqualified=true) if ANY of these:
- Staffing/recruitment agency is the actual employer (not just posting platform)
- Clearly junior/intern/apprenticeship (Ausbildung, Werkstudent, Praktikum)
- Role is outside DACH
- Role is non-technical: construction, cleaning, accounting, insurance,
  HR consulting, technical writing, project management without engineering
- IT sysadmin or IT support role (not software development)

DO NOT disqualify based on company name alone if the role itself is valid.
Example: "passport Business Engineering GmbH" sounds like an agency but posts
real engineering roles — check the actual role content, not just company name.

Also extract:
- tech_stack: comma-separated main technologies, or empty string
- urgency_signals: urgency phrases found, or empty string
- company_size_signal: "startup" | "scale-up" | "mid-market" | "enterprise" | "unknown"
- seniority_level: "junior" | "mid" | "senior" | "lead" | "unknown"
- role_type: "software_dev" | "security" | "embedded" | "devops" | "data" |
             "it_ops" | "non_engineering" | "unknown"
- requirements: key requirements summary (years of experience, degree, languages,
  certifications, domain knowledge) — max 1 sentence, or empty string

{roles_text}

Respond ONLY in JSON:
{{"roles": [
  {{
    "index": 1,
    "score": 65,
    "is_disqualified": false,
    "reason": "1 sentence explaining the score",
    "tech_stack": "Python, Django, PostgreSQL",
    "urgency_signals": "sofort, ASAP",
    "company_size_signal": "scale-up",
    "seniority_level": "senior",
    "role_type": "software_dev",
    "requirements": "5+ years Python, CS degree preferred, fluent German"
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

                    tier = "disqualified" if (is_disqualified or score < 5) else score_to_tier(score)
                    job["score"] = score
                    job["tier"] = tier
                    job["reason"] = cls.get("reason", "")
                    job["tech_stack"] = cls.get("tech_stack", "")
                    job["urgency_signals"] = cls.get("urgency_signals", "")
                    job["company_size_signal"] = cls.get("company_size_signal", "unknown")
                    job["seniority_level"] = cls.get("seniority_level", "unknown")
                    job["role_type"] = cls.get("role_type", "unknown")
                    job["requirements"] = cls.get("requirements", "")
                    scored.append(job)

            time.sleep(0.5)

        except json.JSONDecodeError as e:
            logger.error(f"Claude JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Claude error: {type(e).__name__}: {e}")

    hot_count = sum(1 for j in scored if j.get("tier") == "hot")
    warm_count = sum(1 for j in scored if j.get("tier") == "warm")
    park_count = sum(1 for j in scored if j.get("tier") == "park")
    discard_count = len(jobs) - len(scored)
    logger.info(f"Scored: {hot_count} hot, {warm_count} warm, {park_count} park, {discard_count} discarded")
    return scored


# ═══════════════════════════════════════════════════════════
# POST-SCORING FILTER
# ═══════════════════════════════════════════════════════════

def filter_by_role_type(jobs):
    """
    Drop roles that scored but are not target role types.
    it_ops and non_engineering should not appear in output
    even if they scored above 0 due to city/urgency bonuses.
    """
    excluded_types = {"it_ops", "non_engineering"}
    filtered = [j for j in jobs if j.get("role_type", "unknown") not in excluded_types]
    dropped = len(jobs) - len(filtered)
    if dropped:
        logger.info(f"Role type filter: removed {dropped} it_ops/non_engineering roles")
    return filtered


# ═══════════════════════════════════════════════════════════
# CSV OUTPUT
# ═══════════════════════════════════════════════════════════

CSV_COLUMNS = [
    "score", "company", "title", "seniority_level", "role_type",
    "location", "is_remote", "tech_stack", "requirements", "urgency_signals",
    "company_size_signal", "reason",
    "posted", "source", "url", "tier",
]


def write_csv(jobs, filename=None):
    """Write scored jobs to CSV."""
    if not jobs:
        logger.info("No jobs to write")
        return

    if not filename:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"swe_roles_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)

    # Write slim CSV with just title, seniority, requirements
    slim_filename = filename.replace(".csv", "_requirements.csv")
    slim_columns = ["title", "seniority_level", "requirements"]
    with open(slim_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=slim_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)

    logger.info(f"Wrote {len(jobs)} roles to {filename}")
    logger.info(f"Wrote {len(jobs)} roles to {slim_filename}")
    return filename


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("A-Line SWE Scraper — Starting")
    logger.info("=" * 60)

    # Step 1: Scrape all sources
    jsearch_jobs = scrape_jsearch()
    arbeitnow_jobs = scrape_arbeitnow()

    all_jobs = jsearch_jobs + arbeitnow_jobs
    logger.info(f"Total scraped: {len(all_jobs)} jobs")

    if not all_jobs:
        logger.info("No jobs found — done")
        return

    # Step 2: Dedup (in-memory)
    unique_jobs = dedup_jobs(all_jobs)

    if not unique_jobs:
        logger.info("No jobs after dedup — done")
        return

    # Step 3: Claude SWE scoring
    scored = score_swe_roles(unique_jobs)

    if not scored:
        logger.info("No roles scored above threshold — done")
        return

    # Step 4: (role_type filter disabled — outputting all for prompt training)
    # scored = filter_by_role_type(scored)

    # Step 5: Write CSV (sorted by score desc)
    scored.sort(key=lambda j: j.get("score", 0), reverse=True)
    output_file = write_csv(scored)

    # Summary
    hot_count = sum(1 for j in scored if j.get("tier") == "hot")
    warm_count = sum(1 for j in scored if j.get("tier") == "warm")
    park_count = sum(1 for j in scored if j.get("tier") == "park")

    logger.info("=" * 60)
    logger.info("SWE SCRAPER SUMMARY")
    logger.info(f"  JSearch jobs:      {len(jsearch_jobs)}")
    logger.info(f"  Arbeitnow jobs:    {len(arbeitnow_jobs)}")
    logger.info(f"  After dedup:       {len(unique_jobs)}")
    logger.info(f"  Hot roles:         {hot_count}")
    logger.info(f"  Warm roles:        {warm_count}")
    logger.info(f"  Park roles:        {park_count}")
    logger.info(f"  Output:            {output_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
