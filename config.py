"""
A-Line Job Signal Scraper — Configuration
"""

# ============================================================
# API Keys (set as environment variables or GitHub Secrets)
# ============================================================
import os

JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")
GOOGLE_SHEETS_CREDS_JSON = os.getenv("GOOGLE_SHEETS_CREDS_JSON", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# ============================================================
# Geographic Scope
# ============================================================
LOCATIONS = [
    {"country": "Germany", "code": "de", "lang": "de"},
    {"country": "Germany", "code": "de", "lang": "en"},
    {"country": "Austria", "code": "at", "lang": "de"},
    {"country": "Switzerland", "code": "ch", "lang": "de"},
]

# ============================================================
# Keywords — Tier 1: Explicit Fractional/Interim
# ============================================================
ENGAGEMENT_KEYWORDS = [
    "Fractional",
    "Interim",
    "Part-time",
    "Teilzeit",
    "Befristet",
    "On Demand",
    "Freelance",
]

# ============================================================
# Keywords — Executive Titles (all levels)
# ============================================================
TITLE_KEYWORDS_CLEVEL = [
    "CEO", "CFO", "COO", "CTO", "CRO", "CMO", "CHRO", "CPO",
    "Geschäftsführer", "Geschäftsleitung",
]

TITLE_KEYWORDS_VP = [
    "VP Finance", "VP Engineering", "VP Sales", "VP Marketing",
    "VP Operations", "VP People", "VP Product", "VP Growth",
    "Vice President Finance", "Vice President Engineering",
]

TITLE_KEYWORDS_HEAD = [
    "Head of Finance", "Head of Engineering", "Head of People",
    "Head of HR", "Head of Operations", "Head of Product",
    "Head of Sales", "Head of Marketing", "Head of Growth",
    "Director of Finance", "Director of Engineering",
    "Director of People", "Director of Operations",
    "Kaufmännischer Leiter", "Personalleiter", "Technischer Leiter",
    "Leiter Finanzen", "Leiter Personal", "Leiter Vertrieb",
    "Leiter Marketing", "Leiter Technik",
]

# ============================================================
# Tier 1 Queries: Engagement keyword + Title
# These get highest priority in free tier budget
# ============================================================
TIER1_QUERIES = []
for eng in ["Fractional", "Interim"]:
    for title in ["CFO", "COO", "CTO", "CHRO", "CPO",
                   "Head of Finance", "Head of People",
                   "Head of Engineering", "Head of Operations",
                   "Geschäftsführer"]:
        TIER1_QUERIES.append(f"{eng} {title}")

# ============================================================
# Tier 2 Queries: C-Level titles at startups/scale-ups
# ============================================================
TIER2_QUERIES = [
    "CFO Startup",
    "CTO Startup",
    "COO Startup",
    "Head of Finance Startup",
    "Head of Finance Scale-up",
    "Head of Engineering Startup",
    "VP Finance Startup",
    "Head of People Startup",
    "Kaufmännischer Leiter Startup",
]

# ============================================================
# Body Text Signals (for scoring postings as Hot)
# ============================================================
FRACTIONAL_BODY_SIGNALS = [
    "part-time", "teilzeit", "3 days", "2 days", "4 days",
    "3 tage", "2 tage", "4 tage", "days per week", "tage pro woche",
    "freelance", "contract", "befristet", "initially part",
    "übergangsweise", "interimsweise", "on demand",
    "contract-to-hire", "fractional", "interim",
    "6-month", "6 month", "6 monate", "12-month", "12 month",
    "maternity cover", "elternzeitvertretung",
]

# ============================================================
# Exclusion Filters
# ============================================================
EXCLUDED_COMPANIES = [
    # Staffing agencies / recruiters
    "hays", "robert half", "michael page", "page group",
    "kienbaum", "spencer stuart", "randstad", "adecco",
    "manpower", "manpowergroup", "brunel", "gulp",
    "experteer", "kforce", "kelly services", "modis",
    "amadeus fire", "dis ag", "progressive",
    # Big consulting
    "mckinsey", "bcg", "bain", "deloitte", "pwc", "kpmg", "ey",
    "ernst & young", "accenture",
]

EXCLUDED_TITLE_WORDS = [
    "intern ", "internship", "praktikum", "werkstudent",
    "working student", "junior", "assistant",
]

# ============================================================
# Scoring Weights
# ============================================================
SCORING = {
    "explicit_fractional_interim_title": 40,
    "fractional_signal_body": 25,
    "recent_funding": 15,
    "company_size_sweet_spot": 10,  # 10-200 employees
    "dach_confirmed": 5,
    "clevel_title": 5,
}

# ============================================================
# Role Function Mapping
# ============================================================
FUNCTION_MAP = {
    "Finance": ["cfo", "finance", "finanzen", "kaufmännisch", "controller", "accounting", "treasury"],
    "Engineering": ["cto", "engineering", "technik", "technisch", "development", "software"],
    "People": ["chro", "people", "hr", "human resources", "personal", "talent"],
    "Operations": ["coo", "operations", "betrieb"],
    "Sales": ["cro", "sales", "vertrieb", "revenue", "business development"],
    "Marketing": ["cmo", "marketing"],
    "Product": ["cpo", "product", "produkt"],
    "General Management": ["ceo", "geschäftsführ", "geschäftsleitung", "managing director"],
}

# ============================================================
# Google Sheets Tab Names
# ============================================================
SHEET_TAB_HOT = "Hot Leads"
SHEET_TAB_WARM = "Warm Leads"
SHEET_TAB_PARKED = "Parked"
SHEET_TAB_LOG = "Scraper Log"

SHEET_HEADERS = [
    "Company", "Role", "Signal Tier", "Fractional Signals",
    "Location", "Posted", "Source", "URL",
    "Company Size", "Funding", "Decision Maker",
    "Score", "Status", "Notes", "Function", "Level",
    "Dedup Key", "First Seen", "Last Updated",
]
