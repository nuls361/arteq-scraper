#!/usr/bin/env python3
"""
Arteq Company Discovery — Proactively find promising companies.

Sources:
  1. Funding RSS feeds (deutsche-startups.de, eu-startups.com, TechCrunch)
  2. Apollo Headcount Tracking (growth signals for existing companies)
  3. Tech-Stack Analysis via Wappalyzer (modern stack = good fit)

Creates new companies in Supabase with status='lead' and logs discovery signals.

Usage: python company_discovery.py
Requires: SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
Optional: APOLLO_API_KEY (for headcount tracking)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import feedparser
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("company_discovery")

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

FUNDING_RSS_FEEDS = {
    "rss_deutsche_startups": "https://www.deutsche-startups.de/feed/",
    "rss_eu_startups": "https://www.eu-startups.com/feed/",
    "rss_techcrunch_funding": "https://techcrunch.com/category/venture/feed/",
}

# DACH filter keywords — we only care about DACH-region companies
DACH_KEYWORDS = [
    "germany", "german", "deutschland", "deutsch", "berlin", "munich", "münchen",
    "hamburg", "frankfurt", "cologne", "köln", "düsseldorf", "stuttgart", "vienna",
    "wien", "austria", "österreich", "swiss", "switzerland", "schweiz", "zürich",
    "zurich", "basel", "bern", "dach", "gmbh", "ag", "dach-region",
    "seed", "series a", "series b", "series c",  # funding keywords
]

# Technologies that indicate a modern, tech-forward company
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
        "FrontPage", "Flash",
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
        else:
            return None

        if resp.status_code in (200, 201):
            return resp.json()
        else:
            logger.error(f"  Supabase {method} {table}: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"  Supabase error: {e}")
        return None


def strip_html(text):
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def clean_json_response(text):
    """Strip markdown code fences from Claude JSON response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════
# STEP 1: FUNDING RSS FEED SCANNER
# ═══════════════════════════════════════════════════════════

def scan_funding_feeds():
    """Scan funding-focused RSS feeds for DACH startup news."""
    logger.info("\n📡 SCANNING FUNDING RSS FEEDS...")
    articles = []

    for source, url in FUNDING_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            feed_articles = feed.get("entries", [])
            logger.info(f"  {source}: {len(feed_articles)} articles")

            for entry in feed_articles[:30]:  # Last 30 articles per feed
                title = strip_html(entry.get("title", ""))
                summary = strip_html(entry.get("summary", "") or entry.get("description", ""))
                link = entry.get("link", "")
                published = entry.get("published", "")

                # Quick DACH relevance check on title + summary
                text_lower = f"{title} {summary}".lower()
                is_dach = any(kw in text_lower for kw in DACH_KEYWORDS)

                # Also check for funding-specific content
                is_funding = any(kw in text_lower for kw in [
                    "funding", "raised", "series", "seed", "investment",
                    "million", "finanzierung", "kapital", "runde",
                    "raises", "secures", "closes",
                ])

                if is_dach or (is_funding and source == "rss_deutsche_startups"):
                    articles.append({
                        "title": title[:300],
                        "summary": summary[:1000],
                        "url": link,
                        "source": source,
                        "published": published,
                    })

        except Exception as e:
            logger.error(f"  {source} error: {e}")

    logger.info(f"  → {len(articles)} DACH-relevant funding articles found")
    return articles


def extract_companies_from_articles(articles):
    """Use Claude to extract company names, funding details, and fit assessment from articles."""
    if not ANTHROPIC_KEY or not articles:
        return []

    logger.info(f"\n🤖 EXTRACTING COMPANIES from {len(articles)} articles...")
    discoveries = []

    # Process in batches of 5
    for i in range(0, len(articles), 5):
        batch = articles[i:i+5]
        articles_text = ""
        for idx, art in enumerate(batch):
            articles_text += f"\n--- Article {idx+1} ---\nTitle: {art['title']}\nSummary: {art['summary'][:600]}\nURL: {art['url']}\nSource: {art['source']}\n"

        prompt = f"""Analysiere diese Startup/Funding-News-Artikel und extrahiere Company-Informationen.

Wir suchen DACH-Companies (Deutschland, Österreich, Schweiz) die:
- Gerade Funding bekommen haben (Seed, Series A/B/C)
- Schnell wachsen
- Potenzielle Kunden für Fractional/Interim Executives sein könnten

{articles_text}

Für JEDEN Artikel wo eine DACH-Company identifizierbar ist, extrahiere:
- company_name: Exakter Name der Company
- domain: Website-Domain falls im Artikel erkennbar (sonst null)
- industry: Branche (1-2 Wörter)
- funding_stage: seed/series_a/series_b/series_c/growth/unknown
- funding_amount: Betrag falls genannt (z.B. "€10M"), sonst null
- investors: Investoren falls genannt, sonst null
- hq_city: Standort falls erkennbar, sonst null
- country: DE/AT/CH falls erkennbar
- summary: 1 Satz warum die Company für Arteq interessant sein könnte
- arteq_fit: high/medium/low — wie wahrscheinlich brauchen sie Interim/Fractional Executives?
  (high = gerade Funding bekommen + wachsen schnell, medium = interessant aber unklar, low = zu früh/zu groß/nicht passend)
- article_url: URL des Artikels
- article_title: Titel des Artikels

Antworte NUR in validem JSON als Array. Wenn kein Artikel eine DACH-Company enthält, antworte mit [].
Keine Markdown-Backticks.

[{{"company_name": "...", "domain": "...", ...}}]"""

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45,
            )

            if resp.status_code != 200:
                logger.error(f"  Claude API {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

            if not text.strip():
                continue

            results = json.loads(clean_json_response(text))
            if isinstance(results, list):
                for r in results:
                    if r.get("company_name"):
                        discoveries.append(r)
                        logger.info(f"  → Discovered: {r['company_name']} ({r.get('funding_stage', '?')}) — {r.get('arteq_fit', '?')} fit")

        except json.JSONDecodeError as e:
            logger.error(f"  JSON parse error: {e}")
        except Exception as e:
            logger.error(f"  Claude error: {e}")

        time.sleep(1)

    logger.info(f"  → {len(discoveries)} companies extracted")
    return discoveries


# ═══════════════════════════════════════════════════════════
# STEP 2: APOLLO HEADCOUNT TRACKING
# ═══════════════════════════════════════════════════════════

def track_headcount_growth():
    """Check headcount for existing companies via Apollo and detect growth."""
    if not APOLLO_API_KEY or not SUPABASE_URL:
        logger.info("\n📊 HEADCOUNT TRACKING: Skipped (no Apollo API key or Supabase)")
        return []

    logger.info("\n📊 TRACKING HEADCOUNT GROWTH via Apollo...")

    # Get companies with a domain
    companies = supabase_request("GET", "company", params={
        "select": "id,name,domain,headcount",
        "domain": "not.is.null",
        "limit": "100",
        "order": "created_at.desc",
    })

    if not companies:
        logger.info("  No companies with domains found")
        return []

    growth_signals = []
    checked = 0

    for company in companies:
        domain = (company.get("domain") or "").strip()
        if not domain:
            continue

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
                continue

            org = resp.json().get("organization", {})
            if not org:
                continue

            new_headcount = org.get("estimated_num_employees")
            if not new_headcount:
                continue

            old_headcount = company.get("headcount")
            old_count = int(old_headcount) if old_headcount and str(old_headcount).isdigit() else None

            # Update headcount in DB
            supabase_request("PATCH", f"company?id=eq.{company['id']}", data={
                "headcount": str(new_headcount),
            })

            # Detect growth
            if old_count and new_headcount > old_count:
                growth_pct = round(((new_headcount - old_count) / old_count) * 100)
                if growth_pct >= 10:  # Only report 10%+ growth
                    signal = {
                        "company_id": company["id"],
                        "company_name": company["name"],
                        "old_headcount": old_count,
                        "new_headcount": new_headcount,
                        "growth_pct": growth_pct,
                    }
                    growth_signals.append(signal)
                    logger.info(f"  → 📈 {company['name']}: {old_count} → {new_headcount} (+{growth_pct}%)")

            checked += 1
            time.sleep(1)  # Rate limit

        except Exception as e:
            logger.debug(f"  Apollo org error for {company['name']}: {e}")

    logger.info(f"  Checked {checked} companies, {len(growth_signals)} growth signals")
    return growth_signals


# ═══════════════════════════════════════════════════════════
# STEP 3: TECH STACK ANALYSIS
# ═══════════════════════════════════════════════════════════

def analyze_tech_stack(domain):
    """Analyze a company's tech stack by checking HTTP headers and common patterns."""
    if not domain:
        return None

    url = f"https://{domain}" if not domain.startswith("http") else domain
    tech_detected = []

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ArteqBot/1.0)",
        }, allow_redirects=True)

        html = resp.text[:50000].lower()
        headers_str = str(resp.headers).lower()

        # Check for common tech indicators in HTML + headers
        tech_checks = {
            "React": ["react", "reactdom", "__next", "/_next/"],
            "Next.js": ["__next", "/_next/", "nextjs"],
            "Vue.js": ["vue.js", "vuejs", "__vue", "nuxt"],
            "Angular": ["ng-version", "angular", "ng-app"],
            "TypeScript": [],  # Can't reliably detect from HTML
            "WordPress": ["wp-content", "wp-includes", "wordpress"],
            "Shopify": ["shopify", "cdn.shopify"],
            "HubSpot": ["hubspot", "hs-scripts", "hbspt"],
            "Intercom": ["intercom", "intercomcdn"],
            "Segment": ["segment.com/analytics", "analytics.js", "cdn.segment"],
            "Stripe": ["stripe.com", "js.stripe"],
            "Google Analytics": ["google-analytics", "gtag", "googletagmanager"],
            "Mixpanel": ["mixpanel"],
            "Hotjar": ["hotjar"],
            "Salesforce": ["salesforce", "pardot"],
            "Zendesk": ["zendesk", "zdassets"],
            "Drift": ["drift.com", "driftt"],
            "Cloudflare": ["cloudflare"],
            "AWS": ["amazonaws.com"],
            "Google Cloud": ["googleapis.com", "gstatic"],
            "Datadog": ["datadoghq"],
            "Sentry": ["sentry.io", "sentry-trace"],
        }

        for tech, patterns in tech_checks.items():
            for pattern in patterns:
                if pattern in html or pattern in headers_str:
                    tech_detected.append(tech)
                    break

        # Also check common meta generators
        generator_match = re.search(r'<meta[^>]*name=["\']generator["\'][^>]*content=["\']([^"\']+)', html)
        if generator_match:
            tech_detected.append(f"Generator: {generator_match.group(1)[:50]}")

    except Exception as e:
        logger.debug(f"  Tech stack check failed for {domain}: {e}")
        return None

    if not tech_detected:
        return None

    # Score the tech stack
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
        "high_fit_tech": high_fit,
        "low_fit_tech": low_fit,
        "tech_fit": tech_fit,
    }


def check_tech_stacks_for_new_companies(discoveries):
    """Run tech stack analysis on newly discovered companies with domains."""
    logger.info(f"\n🔧 CHECKING TECH STACKS for {len(discoveries)} discoveries...")
    checked = 0

    for disc in discoveries:
        domain = disc.get("domain")
        if not domain:
            continue

        result = analyze_tech_stack(domain)
        if result:
            disc["tech_stack"] = result
            logger.info(f"  {disc['company_name']}: {', '.join(result['technologies'][:5])} → {result['tech_fit']} fit")
            checked += 1

        time.sleep(0.5)

    logger.info(f"  Checked {checked}/{len(discoveries)} companies")


# ═══════════════════════════════════════════════════════════
# STEP 4: SAVE TO SUPABASE
# ═══════════════════════════════════════════════════════════

def save_discovered_companies(discoveries):
    """Save newly discovered companies to Supabase."""
    if not SUPABASE_URL or not discoveries:
        return

    logger.info(f"\n💾 SAVING {len(discoveries)} discovered companies to Supabase...")

    created = 0
    skipped = 0

    for disc in discoveries:
        company_name = disc.get("company_name", "").strip()
        if not company_name:
            continue

        # Check if company already exists (by name, case-insensitive)
        existing = supabase_request("GET", "company", params={
            "name": f"ilike.{company_name}",
            "select": "id,name",
            "limit": "1",
        })

        if existing and len(existing) > 0:
            company_id = existing[0]["id"]
            skipped += 1
            logger.debug(f"  {company_name} already exists — adding signal only")
        else:
            # Create new company
            company_data = {
                "name": company_name,
                "domain": disc.get("domain"),
                "industry": disc.get("industry"),
                "funding_stage": disc.get("funding_stage") if disc.get("funding_stage") != "unknown" else None,
                "funding_amount": disc.get("funding_amount"),
                "investors": disc.get("investors"),
                "hq_city": disc.get("hq_city"),
                "status": "lead",
                "arteq_fit": disc.get("arteq_fit", "unknown"),
                "source_detail": f"discovery:{disc.get('article_url', '')}",
            }
            # Add headcount if available from Apollo
            # Add tech fit if available
            tech = disc.get("tech_stack")
            if tech:
                company_data["tech_stack"] = ", ".join(tech.get("technologies", [])[:8])

            company_data = {k: v for k, v in company_data.items() if v is not None}

            result = supabase_request("POST", "company", data=company_data)
            if result and len(result) > 0:
                company_id = result[0]["id"]
                created += 1
                logger.info(f"  ✅ Created: {company_name} ({disc.get('funding_stage', '?')}, {disc.get('arteq_fit', '?')} fit)")
            else:
                continue

        # Add discovery signal to company dossier
        signal_content = disc.get("summary", "")
        if disc.get("funding_amount"):
            signal_content += f"\nFunding: {disc['funding_amount']}"
        if disc.get("investors"):
            signal_content += f"\nInvestoren: {disc['investors']}"
        tech = disc.get("tech_stack")
        if tech:
            signal_content += f"\nTech-Stack: {', '.join(tech.get('technologies', [])[:6])} ({tech.get('tech_fit', '?')} fit)"

        supabase_request("POST", "company_dossier", data={
            "company_id": company_id,
            "entry_type": "signal",
            "title": disc.get("article_title", f"Funding: {company_name}"),
            "content": signal_content[:2000],
            "source": disc.get("source", "rss_funding"),
            "source_url": disc.get("article_url", ""),
            "author": "Company Discovery Bot",
        })

    logger.info(f"  → {created} new companies created, {skipped} already existed")


def save_growth_signals(growth_signals):
    """Save headcount growth signals to company dossier."""
    if not SUPABASE_URL or not growth_signals:
        return

    logger.info(f"\n💾 SAVING {len(growth_signals)} growth signals...")

    for signal in growth_signals:
        supabase_request("POST", "company_dossier", data={
            "company_id": signal["company_id"],
            "entry_type": "signal",
            "title": f"Headcount Growth: {signal['old_headcount']} → {signal['new_headcount']} (+{signal['growth_pct']}%)",
            "content": f"{signal['company_name']} ist um {signal['growth_pct']}% gewachsen (von {signal['old_headcount']} auf {signal['new_headcount']} Mitarbeiter). Schnelles Wachstum = möglicher Bedarf an Interim/Fractional Leadership.",
            "source": "apollo_headcount",
            "author": "Company Discovery Bot",
        })

    logger.info(f"  → {len(growth_signals)} growth signals saved")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 80)
    print("  ARTEQ COMPANY DISCOVERY — Find Promising Companies")
    print(f"  Sources: Funding RSS ✓ | Apollo Headcount {'✓' if APOLLO_API_KEY else '✗'} | Tech Stack ✓")
    print(f"  AI: {'ON ✓' if ANTHROPIC_KEY else 'OFF'}")
    print(f"  Supabase: {'ON ✓' if SUPABASE_URL else 'OFF'}")
    print("=" * 80)

    # ── Step 1: Scan Funding RSS Feeds ──
    articles = scan_funding_feeds()

    # ── Step 2: Extract companies via Claude ──
    discoveries = extract_companies_from_articles(articles)

    # ── Step 3: Tech Stack Analysis on discovered companies ──
    if discoveries:
        check_tech_stacks_for_new_companies(discoveries)

    # ── Step 4: Apollo Headcount Tracking for existing companies ──
    growth_signals = track_headcount_growth()

    # ── Step 5: Save everything to Supabase ──
    if discoveries:
        save_discovered_companies(discoveries)
    if growth_signals:
        save_growth_signals(growth_signals)

    # ── Summary ──
    print(f"\n{'='*80}")
    print(f"  DISCOVERY COMPLETE")
    print(f"  Funding articles scanned: {len(articles)}")
    print(f"  Companies discovered: {len(discoveries)}")
    if discoveries:
        high_fit = [d for d in discoveries if d.get("arteq_fit") == "high"]
        print(f"  High fit: {len(high_fit)} | With tech data: {sum(1 for d in discoveries if d.get('tech_stack'))}")
    print(f"  Growth signals: {len(growth_signals)}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
