#!/usr/bin/env python3
"""
Arteq Candidate Pipeline — Supply Side

Builds a database of self-employed Interim Managers, Fractional Executives,
Freelance Advisors and Independent Consultants in DACH.

Four sources (sequential):
  1. PDL (People Data Labs) — structured person search
  2. Comatch / Expertlead / Malt — public marketplace listings
  3. Substack / LinkedIn / Medium — thought leader discovery
  4. Apollo — enrichment layer (email/phone for high-priority candidates)

Usage: python candidate_pipeline.py
"""

import csv
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# Support both ddgs (new) and duckduckgo_search (old)
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("candidate_pipeline")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
PDL_API_KEY = os.getenv("PDL_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

# Target functions
TARGET_TITLES = [
    "interim", "fractional", "advisor", "freelance", "independent", "consultant",
]
TARGET_FUNCTIONS = [
    "cfo", "cto", "coo", "chro", "cpo", "cmo",
    "managing director", "geschäftsführer",
    "head of finance", "head of engineering", "head of operations",
    "head of people", "head of hr", "head of technology",
    "chief financial officer", "chief technology officer",
    "chief operating officer", "chief human resources officer",
    "chief product officer", "chief marketing officer",
]

# Self-employment signals
SELF_EMPLOYED_SIGNALS = [
    "interim", "fractional", "freelance", "independent", "selbstständig",
    "self-employed", "consultant", "advisory", "beratung", "interims",
    "on-demand", "contract", "freiberuflich", "freiberufler",
]

# Web scraping headers
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


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


def normalize_text(text):
    """Normalize text for dedup: lowercase, strip accents, remove special chars."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9 ]", "", text.lower())
    return text.strip()


def normalize_linkedin_url(url):
    """Normalize LinkedIn URL for dedup."""
    if not url:
        return None
    url = url.rstrip("/").lower()
    # Extract the path part
    match = re.search(r"linkedin\.com/in/([a-z0-9\-]+)", url)
    if match:
        return f"https://www.linkedin.com/in/{match.group(1)}"
    return url


def is_self_employed(title, employment_type=None):
    """Check if profile indicates self-employment."""
    if employment_type and employment_type.lower() in ("self_employed", "contract", "freelance"):
        return True
    if not title:
        return False
    title_lower = title.lower()
    return any(signal in title_lower for signal in SELF_EMPLOYED_SIGNALS)


def classify_function(title):
    """Map a title to a function enum."""
    if not title:
        return "other"
    t = title.lower()
    mappings = [
        (["cfo", "chief financial", "finance director", "head of finance"], "cfo"),
        (["cto", "chief technology", "chief technical", "head of engineering", "head of technology", "vp engineering"], "cto"),
        (["coo", "chief operating", "head of operations"], "coo"),
        (["chro", "chief human", "head of people", "head of hr", "vp people", "vp hr"], "chro"),
        (["cpo", "chief product", "head of product", "vp product"], "cpo"),
        (["cmo", "chief marketing", "head of marketing", "vp marketing"], "cmo"),
        (["managing director", "geschäftsführer", "general manager", "ceo", "chief executive"], "md"),
    ]
    for keywords, func in mappings:
        if any(k in t for k in keywords):
            return func
    return "other"


def classify_employment_type(title):
    """Classify employment type from title."""
    if not title:
        return "freelance"
    t = title.lower()
    if "interim" in t or "interims" in t:
        return "interim"
    if "fractional" in t:
        return "fractional"
    if "advisor" in t or "berater" in t or "beratung" in t or "advisory" in t:
        return "advisor"
    return "freelance"


def score_candidate(candidate):
    """Score a candidate 0-100 and assign tier."""
    score = 0
    title = (candidate.get("current_title") or "").lower()

    # +30 Title explicitly contains "interim" or "fractional"
    if "interim" in title or "fractional" in title:
        score += 30

    # +20 LinkedIn profile present
    if candidate.get("linkedin_url"):
        score += 20

    # +20 Verified email present
    if candidate.get("email"):
        score += 20

    # +15 DACH location confirmed
    country = (candidate.get("location_country") or "").lower()
    if country in ("germany", "austria", "switzerland", "de", "at", "ch", "deutschland", "österreich", "schweiz"):
        score += 15

    # +10 Substack / newsletter (actively self-marketing)
    source = (candidate.get("source") or "").lower()
    if source in ("substack", "medium", "linkedin"):
        score += 10

    # +10 Malt / Comatch profile (actively listed on marketplace)
    if source in ("comatch", "expertlead", "malt"):
        score += 10

    # +5 Skills match C-level profile
    skills = candidate.get("skills") or []
    clevel_skills = ["strategy", "leadership", "transformation", "restructuring",
                     "m&a", "fundraising", "scaling", "digital transformation",
                     "change management", "board", "p&l", "investor relations"]
    if any(s.lower() in clevel_skills for s in skills if s):
        score += 5

    # Cap at 100
    score = min(score, 100)

    # Tier assignment
    if score >= 70:
        tier = "available"
    elif score >= 40:
        tier = "passive"
    else:
        tier = "research"

    return score, tier


def get_user_agent():
    """Get a rotating user agent."""
    import random
    return random.choice(USER_AGENTS)


def check_candidate_table():
    """Verify candidate table exists. Returns True if OK."""
    result = supabase_request("GET", "candidate", params={"limit": "1"})
    return result is not None


# ═══════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════

def load_existing_candidates():
    """Load existing linkedin_urls and name+company combos from Supabase."""
    linkedin_urls = set()
    name_keys = set()

    # Fetch all existing candidates (linkedin_url + full_name + current_title)
    offset = 0
    batch_size = 1000
    while True:
        result = supabase_request("GET", "candidate", params={
            "select": "linkedin_url,full_name,current_title",
            "limit": str(batch_size),
            "offset": str(offset),
        })
        if not result:
            break
        for c in result:
            if c.get("linkedin_url"):
                normalized = normalize_linkedin_url(c["linkedin_url"])
                if normalized:
                    linkedin_urls.add(normalized)
            name_key = normalize_text(c.get("full_name", "")) + "|" + normalize_text(c.get("current_title", ""))
            if name_key != "|":
                name_keys.add(name_key)
        if len(result) < batch_size:
            break
        offset += batch_size

    return linkedin_urls, name_keys


def is_duplicate(candidate, existing_linkedin, existing_names):
    """Check if candidate already exists."""
    # Primary: linkedin_url
    li_url = normalize_linkedin_url(candidate.get("linkedin_url"))
    if li_url and li_url in existing_linkedin:
        return True

    # Fallback: name + title
    name_key = normalize_text(candidate.get("full_name", "")) + "|" + normalize_text(candidate.get("current_title", ""))
    if name_key != "|" and name_key in existing_names:
        return True

    return False


def mark_seen(candidate, existing_linkedin, existing_names):
    """Add candidate to dedup sets."""
    li_url = normalize_linkedin_url(candidate.get("linkedin_url"))
    if li_url:
        existing_linkedin.add(li_url)
    name_key = normalize_text(candidate.get("full_name", "")) + "|" + normalize_text(candidate.get("current_title", ""))
    if name_key != "|":
        existing_names.add(name_key)


# ═══════════════════════════════════════════════════════════
# SOURCE 1: PDL (People Data Labs)
# ═══════════════════════════════════════════════════════════

def search_pdl():
    """Search PDL for self-employed executives in DACH."""
    if not PDL_API_KEY:
        logger.warning("PDL_API_KEY not set — skipping PDL source")
        return []

    logger.info("SOURCE 1: PDL — searching for self-employed executives in DACH...")

    # Build Elasticsearch query
    title_should = [{"match_phrase": {"job_title": t}} for t in TARGET_TITLES]
    function_should = [{"match_phrase": {"job_title": f}} for f in TARGET_FUNCTIONS]

    query = {
        "query": {
            "bool": {
                "must": [
                    # Self-employed or contract
                    {"terms": {"job_employment_type": ["self_employed", "contract", "freelance"]}},
                    # DACH location
                    {"terms": {"location_country": ["germany", "austria", "switzerland"]}},
                    # Title must contain self-employment signal
                    {"bool": {"should": title_should, "minimum_should_match": 1}},
                ],
                "should": function_should,
            }
        }
    }

    candidates = []
    scroll_token = None

    try:
        for page in range(10):  # Max 10 pages of 10 = 100 profiles
            params = {
                "size": 10,
                "pretty": "true",
                "dataset": "all",
            }
            if scroll_token:
                params["scroll_token"] = scroll_token

            headers = {
                "Content-Type": "application/json",
                "X-Api-Key": PDL_API_KEY,
            }

            resp = requests.post(
                "https://api.peopledatalabs.com/v5/person/search",
                json=query,
                headers=headers,
                params=params,
                timeout=30,
            )

            if resp.status_code != 200:
                logger.error(f"PDL search failed: {resp.status_code} — {resp.text[:200]}")
                break

            data = resp.json()
            results = data.get("data", [])
            if not results:
                break

            for person in results:
                # Double-check self-employment
                title = person.get("job_title", "")
                if not is_self_employed(title, person.get("job_employment_type")):
                    continue

                # Extract emails — prefer work email
                emails = person.get("emails", [])
                email = None
                for e in (emails or []):
                    if isinstance(e, dict):
                        email = e.get("address")
                        break
                    elif isinstance(e, str):
                        email = e
                        break

                # Extract phone
                phones = person.get("phone_numbers", [])
                phone = phones[0] if phones else None
                if isinstance(phone, dict):
                    phone = phone.get("number")

                # Build location
                location_name = person.get("location_name", "")
                location_country = person.get("location_country", "")
                location_city = ""
                if location_name:
                    parts = location_name.split(",")
                    location_city = parts[0].strip() if parts else ""

                # Skills
                skills = person.get("skills", []) or []
                if isinstance(skills, list) and skills and isinstance(skills[0], dict):
                    skills = [s.get("name", "") for s in skills]

                candidate = {
                    "full_name": person.get("full_name", ""),
                    "email": email,
                    "email_status": "verified" if email else "missing",
                    "phone": phone,
                    "linkedin_url": person.get("linkedin_url"),
                    "current_title": title,
                    "function": classify_function(title),
                    "employment_type": classify_employment_type(title),
                    "location_city": location_city,
                    "location_country": location_country or "germany",
                    "source": "pdl",
                    "source_url": person.get("linkedin_url"),
                    "skills": skills[:20] if skills else [],
                    "notes": f"PDL experience: {len(person.get('experience', []))} roles",
                }

                candidates.append(candidate)

            scroll_token = data.get("scroll_token")
            if not scroll_token or len(candidates) >= 100:
                break

            time.sleep(0.5)

    except Exception as e:
        logger.error(f"PDL search error: {e}")

    logger.info(f"PDL: found {len(candidates)} self-employed profiles")
    return candidates


# ═══════════════════════════════════════════════════════════
# SOURCE 2: Comatch / Expertlead / Malt
# ═══════════════════════════════════════════════════════════

def scrape_comatch():
    """Scrape Comatch public expert listings."""
    logger.info("Scraping Comatch...")
    candidates = []

    try:
        for page in range(1, 4):  # Max 3 pages
            url = f"https://www.comatch.com/de/experten/?page={page}"
            headers = {"User-Agent": get_user_agent()}
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"Comatch page {page}: {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for expert cards / profile listings
            profiles = soup.find_all("div", class_=re.compile(r"expert|profile|card|consultant", re.I))
            if not profiles:
                profiles = soup.find_all("article")
            if not profiles:
                # Try generic link-based extraction
                profiles = soup.find_all("a", href=re.compile(r"/experten/|/expert/|/consultant/"))

            for prof in profiles:
                name_el = prof.find(["h2", "h3", "h4", "span"], class_=re.compile(r"name|title", re.I))
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    # Try first heading
                    heading = prof.find(["h2", "h3", "h4"])
                    name = heading.get_text(strip=True) if heading else ""

                title_el = prof.find(["p", "span", "div"], class_=re.compile(r"role|function|position|subtitle", re.I))
                title = title_el.get_text(strip=True) if title_el else ""

                if not name:
                    continue

                # Extract profile URL
                link = prof.find("a", href=True)
                profile_url = ""
                if link:
                    href = link["href"]
                    if href.startswith("/"):
                        profile_url = f"https://www.comatch.com{href}"
                    elif href.startswith("http"):
                        profile_url = href

                # Extract skills
                skill_els = prof.find_all(["span", "li"], class_=re.compile(r"skill|tag|competenc", re.I))
                skills = [s.get_text(strip=True) for s in skill_els if s.get_text(strip=True)]

                candidate = {
                    "full_name": name,
                    "current_title": title or "Management Consultant",
                    "function": classify_function(title),
                    "employment_type": classify_employment_type(title) if title else "freelance",
                    "source": "comatch",
                    "source_url": profile_url,
                    "skills": skills[:10],
                    "availability_signal": "Comatch profile active",
                    "location_country": "germany",
                }
                candidates.append(candidate)

            time.sleep(2)  # Rate limiting

    except Exception as e:
        logger.error(f"Comatch scraping error: {e}")

    logger.info(f"Comatch: found {len(candidates)} profiles")
    return candidates


def scrape_expertlead():
    """Scrape Expertlead public freelancer listings."""
    logger.info("Scraping Expertlead...")
    candidates = []

    try:
        for page in range(1, 4):  # Max 3 pages
            url = f"https://expertlead.com/de/freelancer/?page={page}"
            headers = {"User-Agent": get_user_agent()}
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"Expertlead page {page}: {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            profiles = soup.find_all("div", class_=re.compile(r"freelancer|profile|card|expert", re.I))
            if not profiles:
                profiles = soup.find_all("article")

            for prof in profiles:
                name_el = prof.find(["h2", "h3", "h4", "span"], class_=re.compile(r"name|title", re.I))
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    heading = prof.find(["h2", "h3", "h4"])
                    name = heading.get_text(strip=True) if heading else ""

                title_el = prof.find(["p", "span", "div"], class_=re.compile(r"role|function|position|subtitle", re.I))
                title = title_el.get_text(strip=True) if title_el else ""

                if not name:
                    continue

                link = prof.find("a", href=True)
                profile_url = ""
                if link:
                    href = link["href"]
                    if href.startswith("/"):
                        profile_url = f"https://expertlead.com{href}"
                    elif href.startswith("http"):
                        profile_url = href

                skill_els = prof.find_all(["span", "li"], class_=re.compile(r"skill|tag|tech", re.I))
                skills = [s.get_text(strip=True) for s in skill_els if s.get_text(strip=True)]

                candidate = {
                    "full_name": name,
                    "current_title": title or "Freelance Expert",
                    "function": classify_function(title),
                    "employment_type": "freelance",
                    "source": "expertlead",
                    "source_url": profile_url,
                    "skills": skills[:10],
                    "availability_signal": "Expertlead profile active",
                    "location_country": "germany",
                }
                candidates.append(candidate)

            time.sleep(2)

    except Exception as e:
        logger.error(f"Expertlead scraping error: {e}")

    logger.info(f"Expertlead: found {len(candidates)} profiles")
    return candidates


def scrape_malt():
    """Scrape Malt public freelancer listings for management/leadership."""
    logger.info("Scraping Malt...")
    candidates = []

    categories = [
        "management-beratung", "business-strategy", "cfo", "cto",
        "interim-management", "unternehmensberatung",
    ]

    try:
        for cat in categories:
            url = f"https://www.malt.de/s?q={cat}"
            headers = {"User-Agent": get_user_agent()}
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"Malt category {cat}: {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            profiles = soup.find_all("div", class_=re.compile(r"freelancer|profile|card|result", re.I))
            if not profiles:
                profiles = soup.find_all("article")
            if not profiles:
                profiles = soup.find_all("a", href=re.compile(r"/profile/"))

            for prof in profiles:
                name_el = prof.find(["h2", "h3", "h4", "span"], class_=re.compile(r"name", re.I))
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    heading = prof.find(["h2", "h3"])
                    name = heading.get_text(strip=True) if heading else ""

                title_el = prof.find(["p", "span", "div"], class_=re.compile(r"title|headline|position|tagline", re.I))
                title = title_el.get_text(strip=True) if title_el else ""

                # Extract rate if visible
                rate_el = prof.find(["span", "div"], class_=re.compile(r"rate|price|day", re.I))
                rate = rate_el.get_text(strip=True) if rate_el else ""

                if not name:
                    continue

                link = prof.find("a", href=True)
                profile_url = ""
                if link:
                    href = link["href"]
                    if href.startswith("/"):
                        profile_url = f"https://www.malt.de{href}"
                    elif href.startswith("http"):
                        profile_url = href

                skill_els = prof.find_all(["span", "li"], class_=re.compile(r"skill|tag|comp", re.I))
                skills = [s.get_text(strip=True) for s in skill_els if s.get_text(strip=True)]

                notes = f"Malt category: {cat}"
                if rate:
                    notes += f", rate: {rate}"

                candidate = {
                    "full_name": name,
                    "current_title": title or f"Freelance {cat.replace('-', ' ').title()}",
                    "function": classify_function(title),
                    "employment_type": "freelance",
                    "source": "malt",
                    "source_url": profile_url,
                    "skills": skills[:10],
                    "availability_signal": "Malt profile active",
                    "location_country": "germany",
                    "notes": notes,
                }
                candidates.append(candidate)

            time.sleep(2)

    except Exception as e:
        logger.error(f"Malt scraping error: {e}")

    logger.info(f"Malt: found {len(candidates)} profiles")
    return candidates


def scrape_marketplaces():
    """Aggregate all marketplace sources."""
    candidates = []

    try:
        candidates.extend(scrape_comatch())
    except Exception as e:
        logger.error(f"Comatch failed: {e}")

    try:
        candidates.extend(scrape_expertlead())
    except Exception as e:
        logger.error(f"Expertlead failed: {e}")

    try:
        candidates.extend(scrape_malt())
    except Exception as e:
        logger.error(f"Malt failed: {e}")

    return candidates


# ═══════════════════════════════════════════════════════════
# SOURCE 3: Substack / LinkedIn / Medium (Thought Leaders)
# ═══════════════════════════════════════════════════════════

def search_via_ddgs(query, max_results=20):
    """Search using DDG with fallback."""
    if DDGS is None:
        logger.warning("No DDG search library available")
        return []

    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return results or []
    except Exception as e:
        logger.warning(f"DDG search failed: {e}")
        return []


def search_via_bing(query, max_results=10):
    """Direct Bing web search as DDG fallback."""
    results = []
    try:
        headers = {"User-Agent": get_user_agent()}
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": str(max_results)},
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for li in soup.find_all("li", class_="b_algo"):
            link = li.find("a", href=True)
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link["href"]
            snippet_el = li.find("p") or li.find("div", class_="b_caption")
            body = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append({"title": title, "href": href, "body": body})

        time.sleep(1)
    except Exception as e:
        logger.warning(f"Bing search failed: {e}")

    return results


def web_search(query, max_results=20):
    """Try DDG first, fall back to direct Bing scraping."""
    results = search_via_ddgs(query, max_results)
    if results:
        return results
    logger.info("DDG returned 0 results — falling back to Bing")
    return search_via_bing(query, min(max_results, 10))


def search_thought_leaders():
    """Find self-employed executives who publish content."""
    logger.info("SOURCE 3: Searching for thought leaders (Substack, LinkedIn, Medium)...")
    candidates = []

    # Search queries targeting self-employed exec content
    queries = [
        # Substack
        'site:substack.com "interim CFO" OR "interim CTO" OR "fractional" germany',
        'site:substack.com "interim management" DACH OR Deutschland',
        # LinkedIn articles/newsletters
        'site:linkedin.com/pulse "interim" OR "fractional" "CFO" OR "CTO" "Deutschland" OR "Germany"',
        'site:linkedin.com/pulse "interim management" OR "fractional executive" DACH',
        # Medium
        'site:medium.com "interim management" OR "fractional leadership" germany OR DACH',
        'site:medium.com "interim CFO" OR "interim CTO" OR "fractional CMO"',
    ]

    try:
        for query in queries:
            results = web_search(query, max_results=20)

            for r in (results or []):
                url = r.get("href", "") or r.get("link", "")
                title = r.get("title", "")
                body = r.get("body", "") or r.get("snippet", "")

                # Determine source platform
                source = "substack"
                if "linkedin.com" in url:
                    source = "linkedin"
                elif "medium.com" in url:
                    source = "medium"

                # Extract author name from title/body
                # Substack: "Author Name | Substack" or "Title by Author Name"
                # LinkedIn: "Author Name on LinkedIn"
                # Medium: "Author Name | Medium"
                author = extract_author_name(title, body, url, source)
                if not author:
                    continue

                # Extract LinkedIn URL from content if available
                linkedin_url = None
                if source == "linkedin" and "/pulse/" in url:
                    # Try to get author's LinkedIn profile from the pulse URL
                    match = re.search(r"linkedin\.com/pulse/[^/]+/([a-z0-9\-]+)", url)
                    if match:
                        linkedin_url = f"https://www.linkedin.com/in/{match.group(1)}"

                # Determine topic/niche
                niche = extract_niche(title, body)

                candidate = {
                    "full_name": author,
                    "linkedin_url": linkedin_url,
                    "current_title": niche or "Executive Thought Leader",
                    "function": classify_function(niche or title),
                    "employment_type": classify_employment_type(niche or title),
                    "source": source,
                    "source_url": url,
                    "availability_signal": f"{source.title()}: publishes content on {niche or 'leadership'}",
                    "location_country": "germany",
                    "notes": f"Content: {title[:100]}",
                }
                candidates.append(candidate)

    except Exception as e:
        logger.error(f"Thought leader search error: {e}")

    # Dedup within thought leaders (same author from multiple articles)
    seen_authors = {}
    unique = []
    for c in candidates:
        key = normalize_text(c["full_name"])
        if key and key not in seen_authors:
            seen_authors[key] = True
            unique.append(c)

    logger.info(f"Thought leaders: found {len(unique)} unique authors (from {len(candidates)} results)")
    return unique


def extract_author_name(title, body, url, source):
    """Extract author name from content metadata."""
    name = ""

    if source == "substack":
        # "Title | Author Name" or "Title - Author Name" (common Bing format)
        match = re.search(r"[\|–—-]\s*([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)\s*$", title)
        if match:
            candidate = match.group(1).strip()
            if candidate.lower() not in ("by substack", "on substack"):
                name = candidate
        # "by Author Name"
        if not name:
            match = re.search(r"\bby\s+([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)", title)
            if match:
                name = match.group(1)
        if not name:
            match = re.search(r"\bby\s+([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)", body)
            if match:
                name = match.group(1)
        # "Author Name's Newsletter"
        if not name:
            match = re.search(r"([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)'s", title)
            if match:
                name = match.group(1)
        # URL pattern: authorname.substack.com
        if not name:
            match = re.search(r"https?://([a-z\-]+)\.substack\.com", url)
            if match:
                raw = match.group(1).replace("-", " ").title()
                if len(raw.split()) >= 2:
                    name = raw

    elif source == "linkedin":
        # "Author Name on LinkedIn" or "Author Name | LinkedIn"
        match = re.search(r"([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)\s+(?:on|[\|–—-])\s*LinkedIn", title)
        if match:
            name = match.group(1)
        # "by Author Name" in body
        if not name:
            match = re.search(r"\bby\s+([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)", body)
            if match:
                name = match.group(1)
        # LinkedIn pulse URL: extract author from slug
        # New format: /pulse/title-slug/firstname-lastname-XXXXX
        # Old format: /pulse/title-slug-firstname-lastname-XXXXX
        # The last 5 chars are a random ID
        if not name:
            match = re.search(r"linkedin\.com/pulse/.+-([a-z]+-[a-z]+(?:-[a-z]+)?)-[a-z0-9]{5}/?$", url)
            if match:
                raw = match.group(1).replace("-", " ").title()
                name = raw
        # Old format without ID suffix (rare)
        if not name:
            match = re.search(r"linkedin\.com/pulse/.+-([a-z]+-[a-z]+(?:-[a-z]+)?)/?$", url)
            if match:
                raw = match.group(1).replace("-", " ").title()
                name = raw

    elif source == "medium":
        # Medium: "@authorname" in URL
        match = re.search(r"medium\.com/@([a-zA-Z0-9\-_.]+)", url)
        if match:
            raw = match.group(1).replace("-", " ").replace("_", " ").replace(".", " ").title()
            if len(raw.split()) >= 2:
                name = raw
        # "by Author Name"
        if not name:
            match = re.search(r"\bby\s+([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)", title + " " + body)
            if match:
                name = match.group(1)
        # "Author Name | Medium" or "Author Name – Medium"
        if not name:
            match = re.search(r"([A-Z][a-zA-Zäöüß\-']+ [A-Z][a-zA-Zäöüß\-']+)\s*[\|–—-]\s*Medium", title)
            if match:
                name = match.group(1)

    # Validate: must look like a real person name
    if name:
        name = name.strip()
        parts = name.split()
        if len(parts) < 2:
            return ""

        # Filter out generic non-name words
        generic = {"the", "and", "for", "with", "about", "from", "this", "that",
                   "your", "how", "what", "why", "when", "our", "all", "new",
                   "get", "top", "best", "key", "big", "part", "safe"}
        if parts[0].lower() in generic or parts[1].lower() in generic:
            return ""

        # Filter out platform/brand names
        platform_names = {"substack", "medium", "linkedin", "newsletter", "blog",
                          "article", "news", "group", "consulting", "solutions"}
        if any(p.lower() in platform_names for p in parts):
            return ""

        # Filter out business/industry terms that aren't person names
        non_names = {
            "interim", "fractional", "management", "executive", "manager",
            "talent", "demand", "strategy", "strategies", "leadership",
            "business", "company", "corporate", "digital", "growth",
            "time", "work", "role", "hire", "team", "chief", "board",
            "service", "services", "partner", "partners", "capital",
            "global", "human", "resources", "financial", "advisory",
            "experts", "executives", "consultants", "professionals",
        }
        if any(p.lower() in non_names for p in parts):
            return ""

        # Each name part must be at least 2 chars and only letters/hyphens/apostrophes
        for p in parts:
            if len(p) < 2:
                return ""
            if not re.match(r"^[A-Za-zÀ-ÿ\-']+$", p):
                return ""

    return name


def extract_niche(title, body):
    """Extract topic/niche from article title and body."""
    text = f"{title} {body}".lower()

    niches = [
        ("interim cfo", "Interim CFO"),
        ("interim cto", "Interim CTO"),
        ("interim coo", "Interim COO"),
        ("fractional cfo", "Fractional CFO"),
        ("fractional cto", "Fractional CTO"),
        ("fractional cmo", "Fractional CMO"),
        ("interim management", "Interim Management"),
        ("fractional executive", "Fractional Executive"),
        ("startup finance", "Startup Finance"),
        ("scale-up", "Scale-up Leadership"),
        ("digital transformation", "Digital Transformation"),
        ("restructuring", "Restructuring"),
    ]

    for keyword, label in niches:
        if keyword in text:
            return label

    return ""


# ═══════════════════════════════════════════════════════════
# SOURCE 4: Apollo (Enrichment Layer)
# ═══════════════════════════════════════════════════════════

def enrich_via_apollo(candidates):
    """Enrich candidates missing emails via Apollo."""
    if not APOLLO_API_KEY:
        logger.warning("APOLLO_API_KEY not set — skipping Apollo enrichment")
        return 0

    logger.info("SOURCE 4: Apollo enrichment for candidates missing email...")
    enriched_count = 0
    email_found = 0

    # Only enrich candidates without email, limit to 20 per run
    to_enrich = [c for c in candidates if not c.get("email") and c.get("full_name")][:20]

    for candidate in to_enrich:
        name = candidate["full_name"]
        name_parts = name.split()
        if len(name_parts) < 2:
            continue

        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:])

        try:
            # Apollo People Search (free — no credits)
            resp = requests.post(
                "https://api.apollo.io/v1/mixed_people/search",
                json={
                    "api_key": APOLLO_API_KEY,
                    "person_titles": [candidate.get("current_title", "")],
                    "person_locations": ["Germany", "Austria", "Switzerland"],
                    "q_keywords": f"{first_name} {last_name}",
                    "page": 1,
                    "per_page": 3,
                },
                timeout=15,
            )

            if resp.status_code != 200:
                continue

            people = resp.json().get("people", [])
            if not people:
                continue

            # Find best match
            for person in people:
                p_name = (person.get("name") or "").lower()
                if normalize_text(first_name) in normalize_text(p_name):
                    email = person.get("email")
                    if email:
                        candidate["email"] = email
                        candidate["email_status"] = "verified"
                        email_found += 1

                    phone = person.get("phone") or (person.get("phone_numbers") or [None])[0]
                    if phone and not candidate.get("phone"):
                        candidate["phone"] = phone if isinstance(phone, str) else phone.get("number", "")

                    if person.get("linkedin_url") and not candidate.get("linkedin_url"):
                        candidate["linkedin_url"] = person["linkedin_url"]

                    enriched_count += 1
                    break

            time.sleep(0.5)

        except Exception as e:
            logger.warning(f"Apollo enrichment failed for {name}: {e}")

    logger.info(f"Apollo: enriched {enriched_count} candidates ({email_found} with email)")
    return enriched_count


# ═══════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════

def write_to_supabase(candidates):
    """Write candidates to Supabase."""
    written = 0
    for c in candidates:
        # Prepare record
        record = {
            "full_name": c.get("full_name", ""),
            "email": c.get("email"),
            "email_status": c.get("email_status", "missing"),
            "phone": c.get("phone"),
            "linkedin_url": c.get("linkedin_url"),
            "current_title": c.get("current_title"),
            "function": c.get("function", "other"),
            "employment_type": c.get("employment_type", "freelance"),
            "location_city": c.get("location_city"),
            "location_country": c.get("location_country"),
            "availability_signal": c.get("availability_signal"),
            "source": c.get("source", ""),
            "source_url": c.get("source_url"),
            "skills": c.get("skills", []),
            "score": c.get("score", 0),
            "tier": c.get("tier", "research"),
            "notes": c.get("notes"),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }

        result = supabase_request("POST", "candidate", data=record)
        if result:
            written += 1

    logger.info(f"Supabase: wrote {written}/{len(candidates)} candidates")
    return written


def write_csv_backup(candidates):
    """Write CSV backup."""
    now = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"candidates_{now}.csv"

    fieldnames = [
        "full_name", "email", "phone", "linkedin_url", "current_title",
        "function", "employment_type", "location_city", "location_country",
        "source", "source_url", "score", "tier", "availability_signal",
        "skills", "notes",
    ]

    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for c in candidates:
                row = dict(c)
                if isinstance(row.get("skills"), list):
                    row["skills"] = ", ".join(row["skills"])
                writer.writerow(row)
        logger.info(f"CSV backup: {filename} ({len(candidates)} candidates)")
    except Exception as e:
        logger.error(f"CSV write error: {e}")

    return filename


def print_summary(stats):
    """Print formatted summary."""
    now = datetime.now().strftime("%d.%m.%Y")
    print(f"\nCANDIDATE PIPELINE — {now}")
    print("━" * 40)
    print(f"PDL:          {stats.get('pdl_found', 0):>3} profiles found | {stats.get('pdl_new', 0)} new | {stats.get('pdl_dupes', 0)} dupes")
    print(f"Comatch:      {stats.get('comatch_found', 0):>3} profiles | {stats.get('comatch_new', 0)} new")
    print(f"Expertlead:   {stats.get('expertlead_found', 0):>3} profiles | {stats.get('expertlead_new', 0)} new")
    print(f"Malt:         {stats.get('malt_found', 0):>3} profiles | {stats.get('malt_new', 0)} new")
    print(f"Thought Ldrs: {stats.get('thought_found', 0):>3} authors  | {stats.get('thought_new', 0)} new")
    print(f"Apollo:       {stats.get('apollo_enriched', 0):>3} enriched ({stats.get('apollo_emails', 0)} with email)")
    print()

    tiers = stats.get("tiers", {})
    funcs = stats.get("functions", {})
    print(f"Tiers:  {tiers.get('available', 0)} available | {tiers.get('passive', 0)} passive | {tiers.get('research', 0)} research")

    func_parts = []
    for f in ["cfo", "cto", "coo", "chro", "cpo", "cmo", "md", "other"]:
        count = funcs.get(f, 0)
        if count > 0:
            func_parts.append(f"{count} {f.upper()}")
    print(f"Functions: {' | '.join(func_parts)}")
    print()


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    logger.info("=== Arteq Candidate Pipeline — Supply Side ===")

    stats = {}
    all_candidates = []

    # Check if Supabase candidate table exists
    table_ok = check_candidate_table()
    if not table_ok:
        logger.warning("Candidate table not found — will write CSV only")

    # Load existing candidates for dedup
    existing_linkedin = set()
    existing_names = set()
    if table_ok:
        existing_linkedin, existing_names = load_existing_candidates()
        logger.info(f"Loaded {len(existing_linkedin)} existing LinkedIn URLs + {len(existing_names)} name keys for dedup")

    # ─── Source 1: PDL ───
    try:
        pdl_candidates = search_pdl()
        stats["pdl_found"] = len(pdl_candidates)

        pdl_new = []
        pdl_dupes = 0
        for c in pdl_candidates:
            if is_duplicate(c, existing_linkedin, existing_names):
                pdl_dupes += 1
            else:
                pdl_new.append(c)
                mark_seen(c, existing_linkedin, existing_names)
        stats["pdl_new"] = len(pdl_new)
        stats["pdl_dupes"] = pdl_dupes
        all_candidates.extend(pdl_new)
    except Exception as e:
        logger.error(f"PDL source failed: {e}")
        stats["pdl_found"] = 0
        stats["pdl_new"] = 0
        stats["pdl_dupes"] = 0

    # ─── Source 2: Marketplaces ───
    try:
        marketplace_candidates = scrape_marketplaces()

        for source_name in ["comatch", "expertlead", "malt"]:
            source_cands = [c for c in marketplace_candidates if c.get("source") == source_name]
            stats[f"{source_name}_found"] = len(source_cands)

            new_count = 0
            for c in source_cands:
                if not is_duplicate(c, existing_linkedin, existing_names):
                    all_candidates.append(c)
                    mark_seen(c, existing_linkedin, existing_names)
                    new_count += 1
            stats[f"{source_name}_new"] = new_count

    except Exception as e:
        logger.error(f"Marketplace source failed: {e}")
        for s in ["comatch", "expertlead", "malt"]:
            stats.setdefault(f"{s}_found", 0)
            stats.setdefault(f"{s}_new", 0)

    # ─── Source 3: Thought Leaders ───
    try:
        thought_candidates = search_thought_leaders()
        stats["thought_found"] = len(thought_candidates)

        thought_new = 0
        for c in thought_candidates:
            if not is_duplicate(c, existing_linkedin, existing_names):
                all_candidates.append(c)
                mark_seen(c, existing_linkedin, existing_names)
                thought_new += 1
        stats["thought_new"] = thought_new

    except Exception as e:
        logger.error(f"Thought leader source failed: {e}")
        stats["thought_found"] = 0
        stats["thought_new"] = 0

    # ─── Source 4: Apollo Enrichment ───
    try:
        enriched = enrich_via_apollo(all_candidates)
        stats["apollo_enriched"] = enriched
        stats["apollo_emails"] = sum(1 for c in all_candidates if c.get("email"))
    except Exception as e:
        logger.error(f"Apollo enrichment failed: {e}")
        stats["apollo_enriched"] = 0
        stats["apollo_emails"] = 0

    # ─── Score all candidates ───
    tiers = {"available": 0, "passive": 0, "research": 0}
    functions = {}
    for c in all_candidates:
        score, tier = score_candidate(c)
        c["score"] = score
        c["tier"] = tier
        tiers[tier] = tiers.get(tier, 0) + 1
        func = c.get("function", "other")
        functions[func] = functions.get(func, 0) + 1

    stats["tiers"] = tiers
    stats["functions"] = functions

    # ─── Output ───
    if table_ok and all_candidates:
        write_to_supabase(all_candidates)

    if all_candidates:
        write_csv_backup(all_candidates)

    print_summary(stats)
    logger.info(f"=== Done: {len(all_candidates)} new candidates processed ===")


if __name__ == "__main__":
    main()
