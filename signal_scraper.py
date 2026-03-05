#!/usr/bin/env python3
"""
Arteq Signal Scraper — Monitor hot companies for business signals.

Sources: TechCrunch RSS, Handelsblatt RSS, Gruenderszene RSS, DuckDuckGo News
Writes classified signals to the Supabase `signal` table.

Usage: python signal_scraper.py
Requires: SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import feedparser
import requests
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("signal_scraper")

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

RSS_FEEDS = {
    "rss_techcrunch": "https://techcrunch.com/feed/",
    "rss_handelsblatt": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
    "rss_gruenderszene": "https://www.gruenderszene.de/feed",
}

SIGNAL_KEYWORDS = [
    # Funding
    "funding", "series a", "series b", "series c", "seed round", "raised",
    "investment round", "finanzierung", "finanzierungsrunde",
    "kapitalerhöhung", "investition",
    # M&A
    "acquisition", "acquired", "merger", "übernahme", "akquisition", "fusion",
    # Leadership
    "appointed", "steps down", "departure", "leaves company", "resigned",
    "neuer geschäftsführer", "neuer vorstand", "verlässt",
    # Layoffs / restructuring
    "layoff", "laid off", "job cuts", "restructuring",
    "entlassungen", "stellenabbau", "restrukturierung", "kurzarbeit",
    # Expansion
    "expansion", "expands", "new office", "new headquarter",
    "expandiert", "neuer standort",
    # IPO
    "ipo", "going public", "public offering", "börsengang",
    # Distress
    "pivot", "bankruptcy", "insolvency", "insolvenz",
    # Hiring surge
    "hiring spree", "hiring surge", "mass hiring",
]

# Company name suffixes to strip (from dedup.py)
COMPANY_SUFFIXES = [
    "gmbh", "ag", "ug", "se", "ltd", "inc", "corp", "co.",
    "haftungsbeschränkt", "limited", "corporation", "company",
    "& co", "& co.", "kg", "ohg", "gbr", "e.v.", "sarl", "sas",
]


# ═══════════════════════════════════════════════════════════
# HELPERS (reused patterns from quick_run.py / dedup.py)
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
    # Find first { or [
    if t and t[0] not in ('{', '['):
        idx_obj = t.find('{')
        idx_arr = t.find('[')
        if idx_obj >= 0 and (idx_arr < 0 or idx_obj < idx_arr):
            t = t[idx_obj:]
        elif idx_arr >= 0:
            t = t[idx_arr:]
    # Match braces/brackets to find end
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


def normalize_company_name(name):
    """Normalize company name for matching (from dedup.py)."""
    name = name.lower().strip()
    for suffix in COMPANY_SUFFIXES:
        name = re.sub(rf'\b{re.escape(suffix)}\b', '', name)
    name = re.sub(r'[^a-z0-9]', '', name)
    return name


# ═══════════════════════════════════════════════════════════
# STEP 1: GET HOT COMPANIES FROM SUPABASE
# ═══════════════════════════════════════════════════════════

def get_hot_companies():
    """Fetch companies that have hot-tier roles."""
    roles = supabase_request("GET", "role", params={
        "select": "company_id",
        "tier": "eq.hot",
        "status": "neq.expired",
    })
    if not roles:
        logger.warning("No hot roles found")
        return []

    company_ids = list(set(r["company_id"] for r in roles if r.get("company_id")))
    if not company_ids:
        return []

    logger.info(f"Found {len(company_ids)} companies with hot roles")

    # Fetch company details in batches of 20
    companies = []
    for i in range(0, len(company_ids), 20):
        batch = company_ids[i:i + 20]
        id_filter = ",".join(batch)
        result = supabase_request("GET", "company", params={
            "select": "id,name,domain",
            "id": f"in.({id_filter})",
        })
        if result:
            companies.extend(result)

    logger.info(f"Fetched {len(companies)} company details")
    return companies


# ═══════════════════════════════════════════════════════════
# STEP 2: SCAN RSS FEEDS
# ═══════════════════════════════════════════════════════════

def scan_rss_feeds(companies):
    """Parse RSS feeds and match articles against company names."""
    # Build lookup: multiple forms per company for fuzzy matching
    company_lookup = {}
    for c in companies:
        original = c["name"].lower()
        normalized = normalize_company_name(c["name"])
        # Skip very short normalized names to avoid false matches
        if len(normalized) >= 3:
            company_lookup[normalized] = c
        if len(original) >= 3:
            company_lookup[original] = c

    articles = []

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            logger.info(f"RSS {source}: {len(feed.entries)} entries")

            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")
                published = entry.get("published", "")

                text_lower = f"{title} {summary}".lower()

                for name_form, company in company_lookup.items():
                    if name_form in text_lower:
                        articles.append({
                            "company_id": company["id"],
                            "company_name": company["name"],
                            "title": title[:500],
                            "summary": re.sub(r'<[^>]+>', '', summary)[:500],
                            "source_url": link,
                            "source": source,
                            "published": published,
                        })
                        break

        except Exception as e:
            logger.error(f"RSS {source} error: {e}")

    logger.info(f"RSS: {len(articles)} articles matched to hot companies")
    return articles


# ═══════════════════════════════════════════════════════════
# STEP 3: DUCKDUCKGO NEWS SEARCH
# ═══════════════════════════════════════════════════════════

def search_duckduckgo_news(companies):
    """Search DuckDuckGo News for each hot company (EN + DE queries)."""
    articles = []

    for company in companies:
        name = company["name"]

        queries = [
            f'"{name}" funding OR layoffs OR CEO OR acquisition OR restructuring',
            f'"{name}" Finanzierung OR Entlassungen OR Geschäftsführer OR Übernahme OR Restrukturierung',
        ]

        for query in queries:
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.news(query, max_results=5, timelimit="w"))

                for r in results:
                    articles.append({
                        "company_id": company["id"],
                        "company_name": name,
                        "title": r.get("title", "")[:500],
                        "summary": r.get("body", "")[:500],
                        "source_url": r.get("url", ""),
                        "source": "web_search",
                        "published": r.get("date", ""),
                    })

                time.sleep(1.5)

            except Exception as e:
                logger.warning(f"DDG search error for '{name}': {e}")
                time.sleep(3)

    logger.info(f"DDG: {len(articles)} articles found for {len(companies)} companies")
    return articles


# ═══════════════════════════════════════════════════════════
# STEP 4: KEYWORD PRE-FILTER
# ═══════════════════════════════════════════════════════════

def keyword_filter(articles):
    """Keep only articles whose title/summary matches signal keywords."""
    filtered = []
    for a in articles:
        text = f"{a['title']} {a['summary']}".lower()
        if any(kw in text for kw in SIGNAL_KEYWORDS):
            filtered.append(a)

    logger.info(f"Keyword filter: {len(filtered)}/{len(articles)} articles passed")
    return filtered


# ═══════════════════════════════════════════════════════════
# STEP 5: DEDUP AGAINST EXISTING SIGNALS
# ═══════════════════════════════════════════════════════════

def dedup_signals(articles, companies):
    """Remove articles already in the signal table (by source_url)."""
    if not articles:
        return []

    # Dedup within batch first
    seen_urls = set()
    unique = []
    for a in articles:
        url = a.get("source_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(a)

    # Fetch existing signal URLs for these companies
    company_ids = list(set(c["id"] for c in companies))
    existing_urls = set()

    for i in range(0, len(company_ids), 20):
        batch = company_ids[i:i + 20]
        id_filter = ",".join(batch)
        result = supabase_request("GET", "signal", params={
            "select": "source_url",
            "company_id": f"in.({id_filter})",
        })
        if result:
            existing_urls.update(r["source_url"] for r in result if r.get("source_url"))

    new_articles = [a for a in unique if a.get("source_url") not in existing_urls]
    dupes = len(articles) - len(new_articles)
    logger.info(f"Dedup: {len(new_articles)} new articles ({dupes} duplicates removed)")
    return new_articles


# ═══════════════════════════════════════════════════════════
# STEP 6: CLAUDE BATCH CLASSIFICATION
# ═══════════════════════════════════════════════════════════

def classify_signals(articles):
    """Use Claude to classify articles into signal types with relevance scoring."""
    if not ANTHROPIC_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping classification")
        return []

    if not articles:
        return []

    classified = []

    # Process in batches of 4
    for i in range(0, len(articles), 4):
        batch = articles[i:i + 4]

        articles_text = ""
        for idx, a in enumerate(batch):
            articles_text += f"""
--- Article {idx + 1} ---
Company: {a['company_name']}
Title: {a['title']}
Summary: {a['summary']}
Source: {a['source']}
"""

        prompt = f"""You are a business signal analyst for Arteq, a DACH fractional/interim executive placement firm.

Classify each article for signals indicating a company might need interim/fractional executives (CFO, COO, CTO, CHRO, etc.).

{articles_text}

For EACH article, respond in this JSON format:
{{
  "articles": [
    {{
      "index": 1,
      "signal_type": "funding_round | leadership_change | layoff | expansion | acquisition | ipo | restructuring | product_launch | regulatory | hiring_surge | other",
      "relevance_score": 0-100,
      "urgency": "high | medium | low",
      "description": "1-2 sentences: what happened and why it matters for interim/fractional placement",
      "skip": false
    }}
  ]
}}

SCORING GUIDE:
- 80-100: Direct trigger (CFO/COO departure, Series B+ funding, restructuring, PE acquisition)
- 50-79: Strong indirect signal (expansion into new market, hiring surge for leadership, pivot)
- 20-49: Weak signal (product launch, general news mention)
- 0-19: Not relevant → set skip=true

Set skip=true for marketing fluff, product reviews, or non-actionable news."""

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
                    "max_tokens": 800,
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

            for cls in result.get("articles", []):
                idx = cls.get("index", 0) - 1
                if 0 <= idx < len(batch) and not cls.get("skip"):
                    article = batch[idx]
                    article["signal_type"] = cls.get("signal_type", "other")
                    article["relevance_score"] = cls.get("relevance_score", 50)
                    article["urgency"] = cls.get("urgency", "medium")
                    article["ai_description"] = cls.get("description", "")
                    classified.append(article)

            time.sleep(0.5)

        except json.JSONDecodeError as e:
            logger.error(f"Claude JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Claude error: {type(e).__name__}: {e}")

    logger.info(f"Claude: {len(classified)}/{len(articles)} articles classified as relevant signals")
    return classified


# ═══════════════════════════════════════════════════════════
# STEP 7: WRITE TO SUPABASE
# ═══════════════════════════════════════════════════════════

def write_dossier_entry(company_id, entry_type, title, content, source, source_url=None, signal_id=None):
    """Write a single entry to the company_dossier table."""
    record = {
        "company_id": company_id,
        "entry_type": entry_type,
        "title": title[:500] if title else None,
        "content": (content or "")[:5000],
        "source": source,
        "source_url": source_url,
        "signal_id": signal_id,
    }
    result = supabase_request("POST", "company_dossier", data=record)
    if not result:
        logger.warning(f"Failed to write dossier entry: {title[:60] if title else '(no title)'}")
    return result


def write_signals(signals):
    """Write classified signals to Supabase signal table + company dossier."""
    if not signals:
        logger.info("No signals to write")
        return 0

    written = 0
    now = datetime.now(timezone.utc).isoformat()

    for s in signals:
        record = {
            "company_id": s["company_id"],
            "company_name_raw": s["company_name"],
            "type": s.get("signal_type", "other"),
            "source": s["source"],
            "source_url": s["source_url"],
            "title": s["title"][:500],
            "description": s.get("ai_description", s.get("summary", ""))[:2000],
            "relevance_score": s.get("relevance_score", 50),
            "urgency": s.get("urgency", "medium"),
            "detected_at": now,
            "processed": False,
        }

        result = supabase_request("POST", "signal", data=record)
        if result:
            written += 1
            # Also write to company dossier for the living intelligence feed
            signal_id = result[0]["id"] if isinstance(result, list) and result else None
            signal_type = s.get("signal_type", "other")
            urgency = s.get("urgency", "medium")
            score = s.get("relevance_score", 50)
            dossier_content = s.get("ai_description", s.get("summary", ""))
            dossier_content += f"\n\n[Signal: {signal_type} | Relevance: {score}/100 | Urgency: {urgency}]"
            write_dossier_entry(
                company_id=s["company_id"],
                entry_type="signal",
                title=s["title"][:500],
                content=dossier_content,
                source=s["source"],
                source_url=s["source_url"],
                signal_id=signal_id,
            )
        else:
            logger.warning(f"Failed to write signal: {s['title'][:60]}")

    logger.info(f"Wrote {written}/{len(signals)} signals to Supabase")
    return written


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("Arteq Signal Scraper — Starting")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    # Step 1: Get hot companies
    companies = get_hot_companies()
    if not companies:
        logger.info("No hot companies found — nothing to do")
        return

    # Step 2: Scan RSS feeds
    rss_articles = scan_rss_feeds(companies)

    # Step 3: DuckDuckGo news search
    ddg_articles = search_duckduckgo_news(companies)

    # Combine
    all_articles = rss_articles + ddg_articles
    logger.info(f"Total articles collected: {len(all_articles)}")

    # Step 4: Keyword pre-filter
    filtered = keyword_filter(all_articles)

    # Step 5: Dedup against existing signals
    new_articles = dedup_signals(filtered, companies)

    if not new_articles:
        logger.info("No new articles after dedup — done")
        return

    # Step 6: Claude classification
    classified = classify_signals(new_articles)

    # Step 7: Write to Supabase
    written = write_signals(classified)

    logger.info("=" * 60)
    logger.info(f"Signal Scraper complete — {written} new signals written")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
