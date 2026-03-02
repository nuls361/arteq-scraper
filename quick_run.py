#!/usr/bin/env python3
"""
Arteq Quick Run v5 — DACH + AI Scoring + Agency Detection + Google Sheets
Usage: python quick_run.py
"""

import requests
import time
import logging
import os
import csv
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("arteq")

API_KEY = os.getenv("JSEARCH_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Google Sheets Config ────────────────────────────────────
SHEET_ID = "1gI7MQd9nn6l14f3Pm4_Weftbv_BTVQIFN65s5c7GZbc"
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

HEADERS = {
    "X-RapidAPI-Key": API_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}

QUERIES = [
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

# ── Static blacklists (first defense line) ──────────────────
# Staffing agencies, consultancies, and interim management providers
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
    # Generic agency signals in company name
    "personalberatung", "executive search", "interim management gmbh",
    "interim-management", "recruiting gmbh", "headhunter",
]

EXCLUDED_TITLES = [
    "intern ", "internship", "praktikum", "werkstudent",
    "junior", "assistant to",
]

DACH_SIGNALS = [
    "germany", "deutschland", "austria", "österreich", "switzerland", "schweiz",
    "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln",
    "düsseldorf", "stuttgart", "vienna", "wien", "zurich", "zürich",
    "leipzig", "dresden", "hannover", "nürnberg", "dortmund", "essen", "bremen",
    "graz", "salzburg", "bern", "basel", "magdeburg", "heidelberg", "potsdam",
    "lübeck", "aalen", "starnberg", "ludwigshafen", "bochum",
]


def safe(val, default=""):
    return val if val is not None else default


def search_jsearch(query):
    params = {"query": query, "page": "1", "num_pages": "1", "date_posted": "month", "country": "de"}
    try:
        resp = requests.get("https://jsearch.p.rapidapi.com/search", headers=HEADERS, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") or []
    except Exception as e:
        logger.error(f"JSearch error for '{query}': {e}")
        return []


def is_dach(location):
    loc = safe(location).lower()
    return any(s in loc for s in DACH_SIGNALS)


def rule_score(title, description, location, is_remote):
    t = safe(title).lower()
    d = safe(description).lower()
    score, signals = 0, []

    if "fractional" in t or "interim" in t:
        score += 40
        signals.append("fractional/interim in title")

    body_kw = ["part-time", "teilzeit", "3 days", "2 days", "4 days", "3 tage", "2 tage",
               "freelance", "contract", "befristet", "6-month", "6 monate",
               "elternzeitvertretung", "maternity cover", "days per week", "tage pro woche"]
    found = [kw for kw in body_kw if kw in d]
    if found and score < 40:
        score += 25
        signals.extend(found[:2])

    if is_dach(location):
        score += 5
        signals.append("DACH")

    clevel = ["ceo", "cfo", "coo", "cto", "cro", "cmo", "chro", "cpo", "geschäftsführer"]
    if any(c in t for c in clevel):
        score += 5
        signals.append("C-Level")

    if any(s in d for s in ["startup", "scale-up", "scaleup", "series a", "series b", "series c", "seed", "venture", "funded"]):
        score += 5
        signals.append("startup")

    return score, signals


def claude_analyze(job):
    """Claude AI analysis with agency detection."""
    if not ANTHROPIC_KEY:
        return None

    prompt = f"""Du bist Lead-Qualification-Agent für Arteq, eine DACH-Fractional/Interim-Executive-Vermittlung.

WICHTIG: Arteq ist selbst eine Vermittlung. Wir suchen DIREKTE Mandanten (Firmen die selbst einen Interim/Fractional Executive brauchen), NICHT andere Personalberatungen oder Interim-Management-Agenturen die Mandate für ihre Kunden ausschreiben.

Analysiere dieses Jobposting:

Firma: {safe(job.get('company'))}
Titel: {safe(job.get('title'))}
Standort: {safe(job.get('location'))}
Remote: {safe(job.get('is_remote'), False)}

Jobbeschreibung:
{safe(job.get('description'))[:3000]}

Antworte NUR in validem JSON (kein Markdown, keine Backticks):
{{
  "is_agency": true/false,
  "agency_reason": "Falls is_agency=true: Warum ist das eine Agentur/Personalberatung? Falls false: leer lassen",
  "actual_client": "Falls is_agency=true und der eigentliche Auftraggeber erkennbar ist, Name hier. Sonst 'unbekannt'",
  "engagement_type": "fractional" | "interim" | "full-time" | "convertible",
  "engagement_reasoning": "Ein Satz warum du so klassifiziert hast",
  "lead_score": 0-100,
  "tier": "hot" | "warm" | "parked",
  "requirements_summary": "Die 3-5 wichtigsten Anforderungen als kurze Liste, z.B.: 10+ Jahre Finance-Erfahrung, SaaS/Subscription-Metriken, Fundraising Series B+, fließend Deutsch",
  "outreach_angle": "Ein konkreter Satz für die erste Kontaktaufnahme mit der Firma",
  "decision_maker_guess": "Wahrscheinlicher Hiring Manager Titel",
  "company_stage_guess": "startup | scaleup | growth | established | unknown"
}}

SCORING-REGELN:
- Ist die ausschreibende Firma eine Personalberatung, Interim-Management-Agentur, Headhunter oder Recruiting-Firma → is_agency=true, lead_score MAXIMAL 10, tier="parked"
- Typische Agentur-Signale: "Im Auftrag unseres Kunden", "für unseren Mandanten", "wir suchen für", mehrere offene Mandate, Firmenname enthält "Consulting", "Partners", "Interim Management", "Executive Search", "Personalberatung"
- Direkte Firma sucht selbst → is_agency=false, normaler Score basierend auf Relevanz für Fractional/Interim-Vermittlung"""

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

        # Enforce agency penalty
        if analysis.get("is_agency"):
            analysis["lead_score"] = min(analysis.get("lead_score", 0), 10)
            analysis["tier"] = "parked"
            logger.info(f"  → AGENCY detected: {analysis.get('agency_reason', '')[:60]}")
        else:
            logger.info(f"  → AI: {analysis.get('tier','?')} ({analysis.get('lead_score','?')}) | {analysis.get('engagement_type','?')}")

        return analysis

    except Exception as e:
        logger.error(f"  Claude error: {type(e).__name__}: {e}")
        return None


# ── Google Sheets Writer ────────────────────────────────────
def write_to_sheets(jobs):
    """Write jobs to Google Sheets, sorted into Hot/Warm/Parked tabs."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("gspread not installed. Run: pip install gspread google-auth")
        return False

    if not os.path.exists(CREDENTIALS_FILE):
        logger.error(f"Credentials file not found: {CREDENTIALS_FILE}")
        return False

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(SHEET_ID)
        logger.info("Connected to Google Sheets ✓")
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {e}")
        return False

    # Header row
    header = [
        "Score", "Company", "Role", "Location", "Signals",
        "Agency?", "Requirements", "Engagement Type", "Reasoning",
        "Outreach Angle", "Decision Maker", "Company Stage",
        "URL", "Posted", "Scraped"
    ]

    scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Sort into tiers
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
            except gspread.WorksheetNotFound:
                ws = sheet.add_worksheet(title=tab_name, rows=500, cols=16)

            # Get existing data to avoid duplicates
            existing = ws.get_all_values()
            existing_keys = set()
            if len(existing) > 1:
                for row in existing[1:]:
                    if len(row) >= 3:
                        key = f"{row[1].lower().strip()}_{row[2].lower().strip()[:30]}"
                        existing_keys.add(key)

            # Write header if sheet is empty
            if not existing:
                ws.update('A1', [header])
                ws.format('A1:O1', {'textFormat': {'bold': True}})

            # Prepare new rows (skip duplicates)
            new_rows = []
            for job in tab_jobs:
                key = f"{job['company'].lower().strip()}_{job['title'].lower().strip()[:30]}"
                if key in existing_keys:
                    continue

                ai = job.get("ai_analysis") or {}

                # Agency label
                if ai.get("is_agency"):
                    agency_label = f"⚠️ AGENCY: {ai.get('agency_reason', '')[:50]}"
                else:
                    agency_label = "✅ Direct" if ai else ""

                row = [
                    job["score"],
                    job["company"],
                    job["title"],
                    job["location"],
                    "; ".join(job["signals"]),
                    agency_label,
                    ai.get("requirements_summary", ""),
                    ai.get("engagement_type", ""),
                    ai.get("engagement_reasoning", ""),
                    ai.get("outreach_angle", ""),
                    ai.get("decision_maker_guess", ""),
                    ai.get("company_stage_guess", ""),
                    job["url"],
                    job["posted"],
                    scraped_date,
                ]
                new_rows.append(row)

            if new_rows:
                start_row = len(existing) + 1 if existing else 2
                ws.update(f'A{start_row}', new_rows)
                logger.info(f"  {tab_name}: +{len(new_rows)} new leads (skipped {len(tab_jobs) - len(new_rows)} duplicates)")
            else:
                logger.info(f"  {tab_name}: No new leads (all duplicates)")

        except Exception as e:
            logger.error(f"  Error writing {tab_name} tab: {e}")

    return True


def main():
    if not API_KEY:
        print("\nERROR: Set JSEARCH_API_KEY first!")
        return

    use_ai = bool(ANTHROPIC_KEY)
    print("\n" + "=" * 90)
    print("  ARTEQ JOB SIGNAL SCRAPER v5 — DACH + AI + Agency Detection + Sheets")
    print(f"  AI Scoring: {'ON ✓' if use_ai else 'OFF (set ANTHROPIC_API_KEY to enable)'}")
    print(f"  Google Sheets: {'ON ✓' if os.path.exists(CREDENTIALS_FILE) else 'OFF (credentials.json missing)'}")
    print("=" * 90)

    # ── Test Claude ─────────────────────────────────────────
    if use_ai:
        logger.info("Testing Claude API...")
        try:
            test = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 10, "messages": [{"role": "user", "content": "Say OK"}]},
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

    # ── Scrape ──────────────────────────────────────────────
    all_jobs = []
    for query in QUERIES:
        logger.info(f"Searching: '{query}'")
        results = search_jsearch(query)

        for raw in results:
            company = safe(raw.get("employer_name"), "Unknown")
            title = safe(raw.get("job_title"), "Unknown")

            if any(ex in company.lower() for ex in EXCLUDED_COMPANIES):
                continue
            if any(ex in title.lower() for ex in EXCLUDED_TITLES):
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

            description = safe(raw.get("job_description"))
            score, signals = rule_score(title, description, loc, remote)
            tier = "HOT" if score > 70 else "WARM" if score >= 40 else "Park"

            job = {
                "tier": tier, "score": score, "company": company, "title": title,
                "location": loc, "is_remote": remote, "signals": signals,
                "url": safe(raw.get("job_apply_link")) or safe(raw.get("job_google_link")),
                "posted": safe(raw.get("job_posted_at_datetime_utc"))[:10] if raw.get("job_posted_at_datetime_utc") else "",
                "description": description, "ai_analysis": None,
            }
            all_jobs.append(job)

        time.sleep(1)

    # ── Dedup ───────────────────────────────────────────────
    seen = set()
    unique = []
    for job in all_jobs:
        key = f"{job['company'].lower().strip()}_{job['title'].lower().strip()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    unique.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"Found {len(unique)} unique DACH leads")

    if not unique:
        print("\n  No DACH results found.\n")
        return

    # ── AI Analysis ─────────────────────────────────────────
    if use_ai:
        ai_candidates = [j for j in unique if j["score"] >= 25]
        logger.info(f"Running Claude analysis on {len(ai_candidates)} leads (agency detection ON)...")
        ai_count = 0
        agency_count = 0
        for job in ai_candidates:
            logger.info(f"Analyzing: {job['company']} — {job['title']}")
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

        logger.info(f"AI analysis: {ai_count}/{len(ai_candidates)} successful | {agency_count} agencies detected and downgraded")
        unique.sort(key=lambda x: x["score"], reverse=True)

    # ── Display ─────────────────────────────────────────────
    # Split display: real leads first, then agencies
    real_leads = [j for j in unique if not (j.get("ai_analysis") or {}).get("is_agency")]
    agencies = [j for j in unique if (j.get("ai_analysis") or {}).get("is_agency")]

    print(f"\n  Total: {len(unique)} unique DACH leads")
    if agencies:
        print(f"  ⚠️  {len(agencies)} agencies detected and filtered to Parked")
    print(f"  ✅ {len(real_leads)} direct company leads")

    print(f"\n{'='*110}")
    print(f"  {'Tier':6} {'Score':>5}  {'Company':25} {'Role':32} {'Location':20}")
    print(f"{'='*110}")

    for job in real_leads[:35]:
        tier_icon = {"HOT": "🔴", "WARM": "🟡", "Park": "⚪"}.get(job["tier"], "⚪")
        print(f"  {tier_icon} {job['tier']:4} {job['score']:5d}  {job['company'][:25]:25} {job['title'][:32]:32} {job['location'][:20]}")

        ai = job.get("ai_analysis")
        if ai:
            req = ai.get("requirements_summary", "")
            if req:
                print(f"  {'':13}  📋 {req[:95]}")
            eng = ai.get("engagement_type", "")
            reasoning = ai.get("engagement_reasoning", "")
            if eng:
                print(f"  {'':13}  🏷️  {eng}: {reasoning[:70]}")
            outreach = ai.get("outreach_angle", "")
            if outreach:
                print(f"  {'':13}  💬 {outreach[:85]}")
        else:
            if job["signals"]:
                print(f"  {'':13}  → {', '.join(job['signals'][:4])}")

        if job["url"]:
            print(f"  {'':13}  🔗 {job['url'][:90]}")
        print()

    if agencies:
        print(f"\n  {'─'*60}")
        print(f"  ⚠️  AGENCIES DETECTED ({len(agencies)}) — moved to Parked:")
        print(f"  {'─'*60}")
        for job in agencies[:10]:
            ai = job.get("ai_analysis", {})
            reason = ai.get("agency_reason", "")[:50]
            client = ai.get("actual_client", "")
            client_info = f" → Client: {client}" if client and client != "unbekannt" else ""
            print(f"  ⚠️  {job['company'][:30]:30} {reason}{client_info}")

    print(f"\n{'='*110}")

    # ── Google Sheets ───────────────────────────────────────
    if os.path.exists(CREDENTIALS_FILE):
        logger.info("Writing to Google Sheets...")
        if write_to_sheets(unique):
            print(f"\n  📊 Google Sheet updated: https://docs.google.com/spreadsheets/d/{SHEET_ID}")
        else:
            logger.error("Google Sheets write failed — saving CSV as backup")
    else:
        logger.info("No credentials.json — skipping Google Sheets")

    # ── CSV backup ──────────────────────────────────────────
    filename = f"leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Tier", "Score", "Company", "Role", "Location", "Signals",
            "Agency?", "Agency Reason", "Actual Client",
            "Requirements", "Engagement Type", "Reasoning",
            "Outreach Angle", "Decision Maker", "Company Stage",
            "URL", "Posted",
        ])
        for job in unique:
            ai = job.get("ai_analysis") or {}
            w.writerow([
                job["tier"], job["score"], job["company"], job["title"],
                job["location"], "; ".join(job["signals"]),
                "AGENCY" if ai.get("is_agency") else "Direct" if ai else "",
                ai.get("agency_reason", ""),
                ai.get("actual_client", ""),
                ai.get("requirements_summary", ""),
                ai.get("engagement_type", ""),
                ai.get("engagement_reasoning", ""),
                ai.get("outreach_angle", ""),
                ai.get("decision_maker_guess", ""),
                ai.get("company_stage_guess", ""),
                job["url"], job["posted"],
            ])
    print(f"  💾 CSV backup: {filename}\n")


if __name__ == "__main__":
    main()
