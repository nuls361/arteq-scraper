# Arteq Job Signal Scraper

## Was ist das?

Automatisierte B2B-Prospecting-Pipeline für Arteq. Zwei Daten-Streams (Roles + Signals) füttern zwei separate Pipelines (Role Pipeline + Company Pipeline). Claude-basierte Klassifizierung statt Rule-based Scoring. Deep Enrichment via Apollo + Claude.

Ziel: Niels bekommt jeden Morgen qualifizierte Leads — vollautomatisch, €0/Monat.

## Architektur

```
Scraping Layer (GitHub Actions, vor Orchestrator)
├── scrapers/role_scraper.py     → JSearch + Arbeitnow → Claude Hot/Warm/Cold
└── scrapers/signal_scraper.py   → RSS + DuckDuckGo → Claude Hot/Warm/Irrelevant
    ↓
Supabase (PostgreSQL)
    ↓
Orchestrator (orchestrator.py) — nach Scrapers:
├── enrichment/company_enricher.py  → Apollo Org + People + Tech Stack + Claude Synthesis
├── enrichment/contact_enricher.py  → Apollo Match + DDG Thought Leadership + Claude DM Score
├── pipeline/role_pipeline.py       → Hot Roles → Opportunities
├── pipeline/company_pipeline.py    → Hot Signals → Opportunities
├── pipeline/sdr_agent.py           → Cold Outreach + Reply Handling + Handoff
├── pipeline/ae_agent.py            → Qualified Response + Meeting Prep + Proposals
└── Daily Brief an Niels
```

## Dateistruktur

```
arteq-scraper/
├── scrapers/
│   ├── role_scraper.py          # Multi-Source Scraper (JSearch + Arbeitnow)
│   ├── signal_scraper.py        # Business Signal Monitor (RSS + DDG)
│   ├── jsearch.py               # JSearch API module (legacy, used by role_scraper)
│   └── wellfound.py             # Wellfound scraper (may deprecate)
├── enrichment/
│   ├── company_enricher.py      # Deep company enrichment (Apollo + Claude)
│   └── contact_enricher.py      # Contact enrichment (Apollo + DDG + Claude)
├── pipeline/
│   ├── role_pipeline.py         # Hot Roles → Opportunities
│   ├── company_pipeline.py      # Hot Signals → Opportunities
│   ├── sdr_agent.py             # SDR: Cold outreach, follow-ups, handoff
│   └── ae_agent.py              # AE: Qualified leads, meetings, proposals
├── orchestrator.py              # Simplified orchestrator (calls enrichers + pipelines + agents)
├── config.py                    # Keywords, Scoring-Weights, Settings
├── dedup.py                     # Deduplizierung
├── healthcheck.py               # System-Health (4x täglich)
├── enrich_single.py             # Single-Company Enrichment (via Dashboard)
├── agent_soul.md                # Core Agent Persona (DE)
├── agent_soul_sdr.md            # SDR-Persona
├── agent_soul_ae.md             # AE-Persona
├── migrations/                  # 001-006 SQL migrations
└── .github/workflows/           # GitHub Actions
```

## Pipeline-Modell

Zwei getrennte Pipelines, beide münden in `opportunity` Table:

| Pipeline | Trigger | Messaging |
|----------|---------|-----------|
| **Role Pipeline** | Hot Role (Interim/Fractional in Titel, C-Level Startup) | "Wir haben gesehen, dass ihr [Role] sucht..." |
| **Company Pipeline** | Hot Signal (Funding, C-Level Departure, Restructuring) | "Wir haben von [Signal] gelesen..." |

Opportunity Stages: `new → enriching → ready_for_outreach → sdr_contacted → replied → qualified → meeting → proposal → closed_won / closed_lost`

## DB-Schema (Supabase)

**Core:** `company`, `contact`, `role`, `signal`, `company_dossier`, `company_contact`
**Pipeline:** `opportunity` (pipeline_type: 'role' | 'company'), `meeting_prep`, `proposal_draft`
**Agentic:** `agent_config`, `agent_log`, `outreach`, `apollo_credit_ledger`

Migrationen in `migrations/001-006*.sql`.

## GitHub Actions

| Workflow | Wann | Was |
|----------|------|-----|
| `role_scraper.yml` | 07:00 CET | `python -m scrapers.role_scraper` |
| `signal_scraper.yml` | 07:15 CET | `python -m scrapers.signal_scraper` |
| `orchestrator.yml` | 07:30 CET | `python orchestrator.py` |
| `healthcheck.yml` | Alle 6h | `python healthcheck.py` |
| `enrich_company.yml` | On-Demand | `python enrich_single.py --company-id <uuid>` |

Alle Module nutzen Package-Imports. `PYTHONPATH=.` in Workflows gesetzt.

## Tech Stack

- **Sprache:** Python 3
- **DB:** Supabase (PostgreSQL)
- **AI:** Anthropic Claude API (Klassifizierung, Scoring, Outreach, Enrichment)
- **E-Mail:** Resend
- **Enrichment:** Apollo API (Org + People Search + Match)
- **Scraping:** requests + feedparser + duckduckgo-search
- **Automation:** GitHub Actions
- **Frontend:** React + Vite (dashboard/)
- **Hosting:** Vercel

## Env-Variablen

- `JSEARCH_API_KEY` — RapidAPI JSearch
- `ANTHROPIC_API_KEY` — Claude
- `SUPABASE_URL` + `SUPABASE_KEY` — Datenbank
- `APOLLO_API_KEY` — Decision-Maker-Enrichment
- `RESEND_API_KEY` — E-Mail-Versand
- `ALERT_EMAIL` — Monitoring-Alerts (niels@arteq.app)

## Konventionen

- **Sprache im Code:** Englisch (Variablen, Funktionen, Kommentare)
- **Sprache für Outreach/Persona:** Deutsch (agent_soul*.md, E-Mail-Templates)
- **Commits:** `feat:`, `fix:`, `refactor:` Prefixes
- **Keine Tests vorhanden** — Code wird durch Healthchecks + Logs überwacht
- **Kein Package Manager** — plain `pip install -r requirements.txt`
- **Supabase-Calls:** Direkt via `requests` gegen REST API (kein Python SDK)
- **Claude API:** Direkt via `requests` (kein Anthropic SDK)
- **Package Imports:** `from scrapers.role_scraper import ...`, `python -m scrapers.role_scraper`

## Häufige Aufgaben

```bash
# Role Scraper (ersetzt quick_run.py)
PYTHONPATH=. python -m scrapers.role_scraper

# Signal Scraper
PYTHONPATH=. python -m scrapers.signal_scraper

# Orchestrator (enrichment + pipelines + agents)
PYTHONPATH=. python orchestrator.py

# Healthcheck
python healthcheck.py

# Einzelne Company enrichen
PYTHONPATH=. python enrich_single.py --company-id <uuid>
```

## Legacy-Dateien (nach Migration löschbar)

`quick_run.py`, root `signal_scraper.py`, root `sdr_agent.py`, root `ae_agent.py`, `company_discovery.py`, `enrich_contacts.py`, `scorer.py`, `daily_scrape.yml`, `signal_scrape.yml`, `company_discovery.yml`
