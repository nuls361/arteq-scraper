#!/usr/bin/env python3
"""
A-Line Research Agent — Match Hot Roles to Candidates

For each hot role (is_hot=true, research_status='pending', status='active'):
  1. Claude extracts structured requirements from role title + description
  2. Search candidate DB by function + location + tier
  3. If <5 DB matches → PDL expansion (new candidates into candidate table)
  4. If still <5 → Apollo People Search expansion
  5. Claude scores each candidate against the specific role (0-100)
  6. Save matches with score ≥ 40 to role_candidate_match
  7. Set role.research_status = 'complete'

Usage: PYTHONPATH=. python -m pipeline.research_agent
"""

import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("research_agent")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PDL_API_KEY = os.getenv("PDL_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

# Function mappings (from candidate_pipeline.py)
FUNCTION_MAPPINGS = [
    (["cfo", "chief financial", "finance director", "head of finance"], "cfo"),
    (["cto", "chief technology", "chief technical", "head of engineering", "head of technology", "vp engineering"], "cto"),
    (["coo", "chief operating", "head of operations"], "coo"),
    (["chro", "chief human", "head of people", "head of hr", "vp people", "vp hr"], "chro"),
    (["cpo", "chief product", "head of product", "vp product"], "cpo"),
    (["cmo", "chief marketing", "head of marketing", "vp marketing"], "cmo"),
    (["managing director", "geschäftsführer", "general manager", "ceo", "chief executive"], "md"),
]

# Location mappings for matching
DACH_COUNTRIES = {
    "germany": "germany", "deutschland": "germany", "de": "germany",
    "austria": "austria", "österreich": "austria", "at": "austria",
    "switzerland": "switzerland", "schweiz": "switzerland", "ch": "switzerland",
}

# Self-employment signals
SELF_EMPLOYED_SIGNALS = [
    "interim", "fractional", "freelance", "independent", "selbstständig",
    "self-employed", "consultant", "advisory", "beratung", "interims",
    "on-demand", "contract", "freiberuflich", "freiberufler",
]


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
    """Make a request to Claude Haiku API."""
    if not ANTHROPIC_KEY:
        return None
    try:
        body = {
            "model": "claude-haiku-4-5-20251001",
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
    match = re.search(r"linkedin\.com/in/([a-z0-9\-]+)", url)
    if match:
        return f"https://www.linkedin.com/in/{match.group(1)}"
    return url


def classify_function(title):
    """Map a title to a function enum."""
    if not title:
        return "other"
    t = title.lower()
    for keywords, func in FUNCTION_MAPPINGS:
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

    if "interim" in title or "fractional" in title:
        score += 30
    if candidate.get("linkedin_url"):
        score += 20
    if candidate.get("email"):
        score += 20
    country = (candidate.get("location_country") or "").lower()
    if country in DACH_COUNTRIES:
        score += 15
    source = (candidate.get("source") or "").lower()
    if source in ("substack", "medium", "linkedin"):
        score += 10
    if source in ("comatch", "expertlead", "malt"):
        score += 10
    skills = candidate.get("skills") or []
    clevel_skills = ["strategy", "leadership", "transformation", "restructuring",
                     "m&a", "fundraising", "scaling", "digital transformation",
                     "change management", "board", "p&l", "investor relations"]
    if any(s.lower() in clevel_skills for s in skills if s):
        score += 5

    score = min(score, 100)
    if score >= 70:
        tier = "available"
    elif score >= 40:
        tier = "passive"
    else:
        tier = "research"

    return score, tier


def is_self_employed(title, employment_type=None):
    """Check if profile indicates self-employment."""
    if employment_type and employment_type.lower() in ("self_employed", "contract", "freelance"):
        return True
    if not title:
        return False
    title_lower = title.lower()
    return any(signal in title_lower for signal in SELF_EMPLOYED_SIGNALS)


# ═══════════════════════════════════════════════════════════
# STEP 1: LOAD HOT ROLES
# ═══════════════════════════════════════════════════════════

def load_hot_roles():
    """Load hot roles that need research."""
    roles = supabase_request("GET", "role", params={
        "select": "id,title,description,location,engagement_type,company_id",
        "tier": "eq.hot",
        "research_status": "eq.pending",
        "status": "eq.new",
        "limit": "10",
        "order": "created_at.desc",
    })
    return roles or []


# ═══════════════════════════════════════════════════════════
# STEP 2: EXTRACT REQUIREMENTS (Claude Haiku)
# ═══════════════════════════════════════════════════════════

def extract_role_requirements(role):
    """Use Claude Haiku to extract structured requirements from role."""
    title = role.get("title", "")
    description = (role.get("description") or "")[:3000]
    location = role.get("location", "")
    engagement = role.get("engagement_type", "")

    prompt = f"""Analyze this job role and extract structured requirements for candidate matching.

Title: {title}
Description: {description}
Location: {location}
Engagement type: {engagement}

Return ONLY a JSON object with these fields:
{{
  "required_function": "<cfo|cto|coo|chro|cpo|cmo|md|other>",
  "required_skills": ["skill1", "skill2", ...],
  "seniority": "<C-Level|VP|Director|Head of|Senior|Other>",
  "industry_preference": "<industry or 'Any'>",
  "location_requirement": "<country or region>",
  "engagement_type": "<Interim|Fractional|Advisory|Full-time|Contract>",
  "key_challenges": ["challenge1", "challenge2"]
}}

Be specific about skills. Infer from context if not explicitly stated."""

    response = claude_request(prompt, max_tokens=800)
    # Infer function from title as fallback
    inferred_function = classify_function(title)

    if not response:
        return {
            "required_function": inferred_function,
            "required_skills": [],
            "seniority": "C-Level",
            "industry_preference": "Any",
            "location_requirement": location or "Germany",
            "engagement_type": engagement or "Interim",
            "key_challenges": [],
        }

    try:
        cleaned = clean_json_response(response)
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse requirements: {e}")
        return {
            "required_function": inferred_function,
            "required_skills": [],
            "seniority": "C-Level",
            "industry_preference": "Any",
            "location_requirement": location or "Germany",
            "engagement_type": engagement or "Interim",
            "key_challenges": [],
        }


# ═══════════════════════════════════════════════════════════
# STEP 3: SEARCH CANDIDATE DB
# ═══════════════════════════════════════════════════════════

def search_candidates_db(requirements):
    """Search existing candidate database for matches."""
    func = requirements.get("required_function", "").lower()
    location = requirements.get("location_requirement", "").lower()

    # Map location to country filter
    country_filter = None
    for key, country in DACH_COUNTRIES.items():
        if key in location:
            country_filter = country
            break

    # Build query params
    params = {
        "select": "id,full_name,email,phone,linkedin_url,current_title,function,employment_type,location_city,location_country,skills,score,tier,notes",
        "tier": "in.(available,passive)",
        "order": "score.desc",
        "limit": "20",
    }

    # Filter by function if specific (not "other")
    if func and func != "other":
        params["function"] = f"eq.{func}"

    # Filter by country if identified
    if country_filter:
        params["location_country"] = f"ilike.*{country_filter}*"

    candidates = supabase_request("GET", "candidate", params=params)
    if not candidates:
        # Retry without location filter
        if country_filter:
            del params["location_country"]
            candidates = supabase_request("GET", "candidate", params=params)

    return candidates or []


# ═══════════════════════════════════════════════════════════
# STEP 4: PDL EXPANSION
# ═══════════════════════════════════════════════════════════

def search_candidates_pdl(requirements):
    """Search PDL for additional candidates matching role requirements."""
    if not PDL_API_KEY:
        logger.warning("PDL_API_KEY not set — skipping PDL expansion")
        return []

    func = requirements.get("required_function", "other")
    location = requirements.get("location_requirement", "Germany")
    engagement = requirements.get("engagement_type", "Interim")
    skills = requirements.get("required_skills", [])

    # Map function to title terms
    func_titles = {
        "cfo": ["CFO", "Chief Financial Officer", "Interim CFO", "Fractional CFO", "Head of Finance"],
        "cto": ["CTO", "Chief Technology Officer", "Interim CTO", "VP Engineering", "Head of Engineering"],
        "coo": ["COO", "Chief Operating Officer", "Interim COO", "Head of Operations"],
        "chro": ["CHRO", "Chief HR Officer", "Interim CHRO", "Head of People", "Head of HR"],
        "cpo": ["CPO", "Chief Product Officer", "Interim CPO", "Head of Product", "VP Product"],
        "cmo": ["CMO", "Chief Marketing Officer", "Interim CMO", "Head of Marketing"],
        "md": ["Managing Director", "Geschäftsführer", "CEO", "Interim CEO", "General Manager"],
    }
    titles = func_titles.get(func, ["Interim Manager", "Fractional Executive"])

    title_should = [{"match_phrase": {"job_title": t}} for t in titles]

    # Map location to PDL country
    pdl_country = "germany"
    for key, country in DACH_COUNTRIES.items():
        if key in location.lower():
            pdl_country = country
            break

    query = {
        "query": {
            "bool": {
                "must": [
                    {"terms": {"job_employment_type": ["self_employed", "contract", "freelance"]}},
                    {"terms": {"location_country": [pdl_country]}},
                    {"bool": {"should": title_should, "minimum_should_match": 1}},
                ],
            }
        }
    }

    candidates = []
    try:
        resp = requests.post(
            "https://api.peopledatalabs.com/v5/person/search",
            json=query,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": PDL_API_KEY,
            },
            params={"size": 10, "pretty": "true", "dataset": "all"},
            timeout=30,
        )

        if resp.status_code != 200:
            logger.error(f"PDL search failed: {resp.status_code} — {resp.text[:200]}")
            return []

        data = resp.json()
        for person in data.get("data", []):
            title = person.get("job_title", "")
            if not is_self_employed(title, person.get("job_employment_type")):
                continue

            # Extract email
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

            # Location
            location_name = person.get("location_name", "")
            location_country = person.get("location_country", "")
            location_city = ""
            if location_name:
                parts = location_name.split(",")
                location_city = parts[0].strip() if parts else ""

            # Skills
            p_skills = person.get("skills", []) or []
            if isinstance(p_skills, list) and p_skills and isinstance(p_skills[0], dict):
                p_skills = [s.get("name", "") for s in p_skills]

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
                "location_country": location_country or pdl_country,
                "source": "pdl",
                "source_url": person.get("linkedin_url"),
                "skills": p_skills[:20] if p_skills else [],
                "notes": f"PDL research agent — {func} role match",
            }
            candidates.append(candidate)

    except Exception as e:
        logger.error(f"PDL search error: {e}")

    logger.info(f"PDL expansion: found {len(candidates)} candidates")
    return candidates


# ═══════════════════════════════════════════════════════════
# STEP 5: APOLLO EXPANSION
# ═══════════════════════════════════════════════════════════

def search_candidates_apollo(requirements):
    """Search Apollo People Search for additional candidates."""
    if not APOLLO_API_KEY:
        logger.warning("APOLLO_API_KEY not set — skipping Apollo expansion")
        return []

    func = requirements.get("required_function", "other")
    location = requirements.get("location_requirement", "Germany")
    engagement = requirements.get("engagement_type", "Interim")

    # Build title search terms
    func_title_map = {
        "cfo": ["CFO", "Chief Financial Officer", "Interim CFO"],
        "cto": ["CTO", "Chief Technology Officer", "Interim CTO"],
        "coo": ["COO", "Chief Operating Officer", "Interim COO"],
        "chro": ["CHRO", "Chief HR Officer", "Interim CHRO", "Head of People"],
        "cpo": ["CPO", "Chief Product Officer", "Interim CPO"],
        "cmo": ["CMO", "Chief Marketing Officer", "Interim CMO"],
        "md": ["Managing Director", "Geschäftsführer", "Interim CEO"],
    }
    person_titles = func_title_map.get(func, ["Interim Manager", "Fractional Executive"])

    # Map location for Apollo
    apollo_locations = []
    loc_lower = location.lower()
    if "germany" in loc_lower or "deutsch" in loc_lower:
        apollo_locations = ["Germany"]
    elif "austria" in loc_lower or "österreich" in loc_lower:
        apollo_locations = ["Austria"]
    elif "switzerland" in loc_lower or "schweiz" in loc_lower:
        apollo_locations = ["Switzerland"]
    else:
        apollo_locations = ["Germany", "Austria", "Switzerland"]

    candidates = []
    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_API_KEY,
            },
            json={
                "person_titles": person_titles,
                "person_locations": apollo_locations,
                "page": 1,
                "per_page": 15,
            },
            timeout=15,
        )

        if resp.status_code != 200:
            logger.error(f"Apollo search failed: {resp.status_code}")
            return []

        people = resp.json().get("people", [])
        for p in people:
            name = p.get("name", "")
            if not name or len(name) < 2:
                continue

            title = p.get("title", "")

            # Filter for self-employment signals
            if not is_self_employed(title):
                # Still include if title matches the function well
                if func != "other" and classify_function(title) != func:
                    continue

            candidate = {
                "full_name": name,
                "email": p.get("email"),
                "email_status": "verified" if p.get("email") else "missing",
                "phone": None,
                "linkedin_url": p.get("linkedin_url"),
                "current_title": title,
                "function": classify_function(title),
                "employment_type": classify_employment_type(title),
                "location_city": p.get("city", ""),
                "location_country": (p.get("country") or apollo_locations[0] if apollo_locations else "Germany"),
                "source": "apollo",
                "source_url": p.get("linkedin_url"),
                "skills": [],
                "notes": f"Apollo research agent — {func} role match",
            }
            candidates.append(candidate)

    except Exception as e:
        logger.error(f"Apollo search error: {e}")

    logger.info(f"Apollo expansion: found {len(candidates)} candidates")
    return candidates


# ═══════════════════════════════════════════════════════════
# CANDIDATE DEDUP + INSERT
# ═══════════════════════════════════════════════════════════

def load_existing_candidates():
    """Load existing linkedin_urls and name+title combos for dedup."""
    linkedin_urls = set()
    name_keys = set()

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
    li_url = normalize_linkedin_url(candidate.get("linkedin_url"))
    if li_url and li_url in existing_linkedin:
        return True
    name_key = normalize_text(candidate.get("full_name", "")) + "|" + normalize_text(candidate.get("current_title", ""))
    if name_key != "|" and name_key in existing_names:
        return True
    return False


def insert_new_candidates(candidates, existing_linkedin, existing_names):
    """Insert new candidates into DB, dedup, score, and return inserted records with IDs."""
    inserted = []
    now = datetime.now(timezone.utc).isoformat()

    for c in candidates:
        if is_duplicate(c, existing_linkedin, existing_names):
            continue

        # Score and tier
        s, tier = score_candidate(c)
        c["score"] = s
        c["tier"] = tier

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
            "score": s,
            "tier": tier,
            "notes": c.get("notes"),
            "last_seen_at": now,
        }

        result = supabase_request("POST", "candidate", data=record)
        if result and isinstance(result, list) and len(result) > 0:
            inserted_record = result[0]
            inserted_record["skills"] = c.get("skills", [])
            inserted.append(inserted_record)

            # Mark as seen for dedup
            li_url = normalize_linkedin_url(c.get("linkedin_url"))
            if li_url:
                existing_linkedin.add(li_url)
            name_key = normalize_text(c.get("full_name", "")) + "|" + normalize_text(c.get("current_title", ""))
            if name_key != "|":
                existing_names.add(name_key)

    logger.info(f"Inserted {len(inserted)} new candidates")
    return inserted


# ═══════════════════════════════════════════════════════════
# STEP 6: CLAUDE SCORING
# ═══════════════════════════════════════════════════════════

def score_candidates_for_role(requirements, candidates):
    """Score candidates against role requirements using Claude Haiku (batches of 5)."""
    scored = []
    batch_size = 5

    req_summary = json.dumps(requirements, indent=2, ensure_ascii=False)

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]

        # Build candidate summaries
        candidate_list = []
        for idx, c in enumerate(batch):
            skills = c.get("skills", [])
            skill_str = ", ".join(skills[:10]) if skills else "not specified"
            candidate_list.append(
                f"Candidate {idx + 1} (ID: {c.get('id', 'unknown')}):\n"
                f"  Name: {c.get('full_name', 'N/A')}\n"
                f"  Title: {c.get('current_title', 'N/A')}\n"
                f"  Function: {c.get('function', 'N/A')}\n"
                f"  Location: {c.get('location_city', '')} {c.get('location_country', '')}\n"
                f"  Employment: {c.get('employment_type', 'N/A')}\n"
                f"  Skills: {skill_str}\n"
                f"  Score: {c.get('score', 0)} | Tier: {c.get('tier', 'N/A')}"
            )

        candidates_text = "\n\n".join(candidate_list)

        prompt = f"""Score these candidates against the role requirements. Be strict but fair.

ROLE REQUIREMENTS:
{req_summary}

CANDIDATES:
{candidates_text}

For each candidate, return a JSON array with objects:
[
  {{
    "candidate_id": "<id>",
    "match_score": <0-100>,
    "reasoning": "<1-2 sentences why this score>",
    "function_match": <true/false>,
    "location_match": <true/false>,
    "skills_overlap": ["matching skill 1", "matching skill 2"]
  }}
]

Scoring guidelines:
- 80-100: Perfect match — right function, location, skills, availability
- 60-79: Strong match — most criteria met, minor gaps
- 40-59: Decent match — function matches but location/skills gaps
- 20-39: Weak match — only partial overlap
- 0-19: Poor match — wrong function or no relevant experience

Return ONLY the JSON array."""

        response = claude_request(prompt, max_tokens=2000)
        if not response:
            # Fallback: assign based on function match
            for c in batch:
                func_match = c.get("function", "") == requirements.get("required_function", "")
                scored.append({
                    "candidate_id": c.get("id"),
                    "match_score": 50 if func_match else 20,
                    "reasoning": "Fallback score — Claude unavailable",
                    "function_match": func_match,
                    "location_match": False,
                    "skills_overlap": [],
                })
            continue

        try:
            cleaned = clean_json_response(response)
            results = json.loads(cleaned)
            if isinstance(results, list):
                scored.extend(results)
            elif isinstance(results, dict):
                scored.append(results)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse scoring response: {e}")
            # Fallback scoring
            for c in batch:
                func_match = c.get("function", "") == requirements.get("required_function", "")
                scored.append({
                    "candidate_id": c.get("id"),
                    "match_score": 50 if func_match else 20,
                    "reasoning": "Fallback score — parse error",
                    "function_match": func_match,
                    "location_match": False,
                    "skills_overlap": [],
                })

        time.sleep(0.5)  # Rate limiting

    return scored


# ═══════════════════════════════════════════════════════════
# STEP 7: SAVE MATCHES
# ═══════════════════════════════════════════════════════════

def save_matches(role_id, scored_candidates):
    """Save scored matches (score >= 40) to role_candidate_match table."""
    saved = 0
    now = datetime.now(timezone.utc).isoformat()

    for sc in scored_candidates:
        score = sc.get("match_score", 0)
        if score < 40:
            continue

        candidate_id = sc.get("candidate_id")
        if not candidate_id:
            continue

        record = {
            "role_id": role_id,
            "candidate_id": candidate_id,
            "match_score": score,
            "match_reasoning": sc.get("reasoning", ""),
            "function_match": sc.get("function_match", False),
            "location_match": sc.get("location_match", False),
            "skills_overlap": sc.get("skills_overlap", []),
            "status": "proposed",
            "updated_at": now,
        }

        result = supabase_request("POST", "role_candidate_match", data=record)
        if result:
            saved += 1

    logger.info(f"Saved {saved} matches for role {role_id}")
    return saved


# ═══════════════════════════════════════════════════════════
# MAIN FLOW
# ═══════════════════════════════════════════════════════════

def run():
    """Main research agent flow. Returns summary dict."""
    logger.info("=" * 60)
    logger.info("Research Agent — Matching hot roles to candidates")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return {"roles_researched": 0, "matches_found": 0}

    # Load hot roles needing research
    roles = load_hot_roles()
    if not roles:
        logger.info("No hot roles pending research")
        return {"roles_researched": 0, "matches_found": 0}

    logger.info(f"Found {len(roles)} hot roles to research")

    # Pre-load existing candidates for dedup (shared across roles)
    existing_linkedin, existing_names = load_existing_candidates()
    logger.info(f"Loaded {len(existing_linkedin)} existing LinkedIn URLs for dedup")

    total_matches = 0
    roles_researched = 0

    for role in roles:
        role_id = role["id"]
        title = role.get("title", "Unknown")
        logger.info(f"\n{'─' * 40}")
        logger.info(f"Researching: {title}")

        # Mark as researching
        supabase_request("PATCH", f"role?id=eq.{role_id}", data={
            "research_status": "researching",
        })

        try:
            # Step 2: Extract requirements
            requirements = extract_role_requirements(role)
            logger.info(f"Requirements: function={requirements.get('required_function')}, "
                        f"location={requirements.get('location_requirement')}, "
                        f"engagement={requirements.get('engagement_type')}")

            # Step 3: Search candidate DB
            db_candidates = search_candidates_db(requirements)
            logger.info(f"DB candidates: {len(db_candidates)}")

            all_candidates = list(db_candidates)

            # Step 4: PDL expansion if <5 DB matches
            if len(db_candidates) < 5:
                logger.info("< 5 DB matches — expanding via PDL...")
                pdl_candidates = search_candidates_pdl(requirements)
                if pdl_candidates:
                    inserted = insert_new_candidates(pdl_candidates, existing_linkedin, existing_names)
                    all_candidates.extend(inserted)
                    logger.info(f"PDL: {len(pdl_candidates)} found, {len(inserted)} new inserted")

            # Step 5: Apollo expansion if still <5
            if len(all_candidates) < 5:
                logger.info("Still < 5 matches — expanding via Apollo...")
                apollo_candidates = search_candidates_apollo(requirements)
                if apollo_candidates:
                    inserted = insert_new_candidates(apollo_candidates, existing_linkedin, existing_names)
                    all_candidates.extend(inserted)
                    logger.info(f"Apollo: {len(apollo_candidates)} found, {len(inserted)} new inserted")

            if not all_candidates:
                logger.info(f"No candidates found for role {title}")
                supabase_request("PATCH", f"role?id=eq.{role_id}", data={
                    "research_status": "complete",
                })
                roles_researched += 1
                continue

            # Step 6: Score candidates against role
            logger.info(f"Scoring {len(all_candidates)} candidates...")
            scored = score_candidates_for_role(requirements, all_candidates)

            # Step 7: Save matches (score >= 40)
            matches_saved = save_matches(role_id, scored)
            total_matches += matches_saved

            # Step 8: Mark role as complete
            supabase_request("PATCH", f"role?id=eq.{role_id}", data={
                "research_status": "complete",
            })
            roles_researched += 1

            logger.info(f"✓ {title}: {matches_saved} matches saved")

        except Exception as e:
            logger.error(f"Error researching role {title}: {e}")
            # Still mark as complete to avoid infinite retries
            supabase_request("PATCH", f"role?id=eq.{role_id}", data={
                "research_status": "complete",
            })
            roles_researched += 1

    logger.info(f"\n{'=' * 60}")
    logger.info(f"Research Agent complete: {roles_researched} roles, {total_matches} matches")
    logger.info(f"{'=' * 60}")

    return {"roles_researched": roles_researched, "matches_found": total_matches}


if __name__ == "__main__":
    run()
