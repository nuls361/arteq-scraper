# Arteq Job Signal Scraper

## Was ist das?

Automatisierte B2B-Prospecting-Pipeline für Arteq. Findet Fractional/Interim Executive Hiring-Signale bei DACH-Startups und Scale-ups, scored Leads (0-100), dedupliziert, enriched mit Kontaktdaten und führt agentic Outreach durch (SDR + AE).

Ziel: Niels bekommt jeden Morgen qualifizierte Leads — vollautomatisch, €0/Monat.

## Architektur

```
Datenquellen (JSearch, JobSpy, Wellfound, RSS)
    ↓
Scraper (quick_run.py, signal_scraper.py, company_discovery.py)
    ↓
Scoring & Dedup (scorer.py, dedup.py, config.py)
    ↓
Supabase (PostgreSQL)
    ↓
Orchestrator (orchestrator.py) → SDR Agent → AE Agent
    ↓
E-Mail-Outreach (Resend) + Daily Brief an Niels
```

## Wichtige Dateien

| Datei | Zweck |
|-------|-------|
| `orchestrator.py` | Master-Orchestrator, Phasen 0-5 |
| `quick_run.py` | Multi-Source Scraper Pipeline |
| `sdr_agent.py` | Cold Outreach & Follow-ups |
| `ae_agent.py` | Account Executive — Meetings & Proposals |
| `company_discovery.py` | Neue Firmen finden (RSS + Funding) |
| `signal_scraper.py` | Hot Companies monitoren |
| `healthcheck.py` | System-Health (4x täglich) |
| `scorer.py` | Scoring-Engine (0-100) |
| `config.py` | Keywords, Scoring-Weights, Settings |
| `dedup.py` | Deduplizierung |
| `agent_soul.md` | Core Agent Persona (DE) |
| `agent_soul_sdr.md` | SDR-Persona |
| `agent_soul_ae.md` | AE-Persona |
| `arteq-dashboard.jsx` | React Dashboard UI |

## Tech Stack

- **Sprache:** Python 3
- **DB:** Supabase (PostgreSQL)
- **AI:** Anthropic Claude API (Scoring, Outreach-Texte, Entscheidungen)
- **E-Mail:** Resend
- **Enrichment:** Apollo API (Kontaktdaten)
- **Scraping:** requests + BeautifulSoup4 + feedparser
- **Automation:** GitHub Actions (täglich 07:00 CET)
- **Frontend:** React (arteq-dashboard.jsx)

## Env-Variablen

Siehe `.env.example`. Kritisch:
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
- **Alle Scripts standalone lauffähig** — `python script.py`
- **Supabase-Calls:** Direkt via `requests` gegen REST API (kein Python SDK)
- **Claude API:** Direkt via `requests` (kein Anthropic SDK)

## Scoring-Logik

| Signal | Punkte |
|--------|--------|
| Explizit "Fractional"/"Interim" im Titel | +40 |
| Fractional-Signal im Body | +25 |
| Frisches Funding | +15 |
| Company Size 10-200 | +10 |
| DACH bestätigt | +5 |
| C-Level Titel | +5 |

Tiers: >70 = Hot, 40-70 = Warm, <40 = Parked

## DB-Schema (Supabase)

**Core:** `company`, `contact`, `role`, `signal`, `company_dossier`
**Agentic:** `agent_config`, `agent_log`, `outreach`, `apollo_credit_ledger`
**Pipeline:** `meeting_prep`, `proposal_draft`

Migrationen in `migrations/001-005*.sql`.

## GitHub Actions

| Workflow | Wann | Was |
|----------|------|-----|
| `daily_scrape.yml` | 07:00 CET | JSearch + Wellfound |
| `company_discovery.yml` | 07:00 CET | Neue Firmen (RSS) |
| `signal_scrape.yml` | 07:00 CET | Signale monitoren |
| `orchestrator.yml` | 07:15 CET | Alle Phasen + Outreach |
| `healthcheck.yml` | Alle 6h | System-Health |

## Häufige Aufgaben

```bash
# Lokaler Scraper-Lauf
python quick_run.py

# Orchestrator testen
python orchestrator.py

# Healthcheck
python healthcheck.py

# Neue Scraper-Quelle hinzufügen
# → Neues File in scrapers/ anlegen, in quick_run.py integrieren
```
