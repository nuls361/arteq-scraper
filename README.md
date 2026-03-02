# Arteq Job Signal Scraper

Automated pipeline that finds fractional and interim executive hiring signals across DACH startups and scale-ups.

## What it does

1. **Scrapes** job postings from JSearch (Google Jobs aggregator) and Wellfound (startup jobs)
2. **Scores** each lead (0–100) based on engagement type, fractional signals, company profile
3. **Deduplicates** across sources to prevent double-outreach
4. **Writes** results to Google Sheets (or CSV fallback), sorted into Hot / Warm / Parked tabs

## Quick Start (5 minutes)

### 1. Get a JSearch API Key (free)

- Go to [rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
- Sign up (free), subscribe to JSearch Free plan (200 requests/month)
- Copy your `X-RapidAPI-Key`

### 2. Run locally

```bash
# Clone and install
git clone <your-repo-url>
cd arteq-scraper
pip install -r requirements.txt

# Set your API key
export JSEARCH_API_KEY="your-rapidapi-key-here"

# Dry run — see results in terminal without writing anywhere
python main.py --dry-run

# Run only Wellfound (no API key needed)
python main.py --source wellfound --dry-run
```

### 3. Set up Google Sheets output (optional)

1. Create a [Google Cloud project](https://console.cloud.google.com/)
2. Enable the **Google Sheets API**
3. Create a **Service Account** → download JSON key file
4. Create a Google Sheet → share it with the service account email (Editor)
5. Set environment variables:
   ```bash
   export GOOGLE_SHEETS_CREDS_JSON='{"type":"service_account","project_id":...}'
   export GOOGLE_SHEET_ID="your-spreadsheet-id-from-url"
   ```
6. Run: `python main.py`

Without Google Sheets configured, results are saved as CSV in `output/`.

### 4. Automate with GitHub Actions (free)

1. Push this repo to GitHub (private repo works)
2. Go to Settings → Secrets → Actions, add:
   - `JSEARCH_API_KEY`
   - `GOOGLE_SHEETS_CREDS_JSON` (entire JSON key as string)
   - `GOOGLE_SHEET_ID`
3. The workflow runs daily at 07:00 CET automatically
4. You can also trigger manually from Actions → Daily Job Signal Scrape → Run workflow

## Free Tier Budget Management

| Resource | Free Limit | Daily Usage | Monthly Usage |
|---|---|---|---|
| JSearch (RapidAPI) | 200 req/month | ~6 queries/day | ~180/month |
| Wellfound | Unlimited | ~8 pages/day | ~240/month |
| Google Sheets API | 60 req/min | ~5 writes/day | ~150/month |
| GitHub Actions | 2,000 min/month | ~3 min/day | ~90 min/month |

Total monthly cost: **€0**

## Scoring Logic

| Signal | Points | Example |
|---|---|---|
| Fractional/Interim in title | +40 | "Fractional CFO" |
| Fractional signal in body | +25 | "3 days per week" in description |
| Recent funding | +15 | Company raised Series B |
| Company size 10–200 | +10 | Sweet spot for fractional need |
| DACH location | +5 | Berlin, Munich, Vienna, Zurich |
| C-Level title | +5 | CFO vs Head of Finance |

**Score > 70** → Hot Lead (daily review)
**Score 40–70** → Warm Lead (weekly review)
**Score < 40** → Parked

## Project Structure

```
arteq-scraper/
├── main.py                  # Orchestration & CLI
├── config.py                # Keywords, scoring weights, settings
├── scorer.py                # Scoring engine
├── dedup.py                 # Deduplication logic
├── sheets_writer.py         # Google Sheets + CSV output
├── scrapers/
│   ├── jsearch.py           # JSearch API (RapidAPI)
│   └── wellfound.py         # Wellfound web scraper
├── .github/
│   └── workflows/
│       └── daily_scrape.yml # GitHub Actions daily cron
├── requirements.txt
└── README.md
```

## CLI Options

```bash
python main.py                           # Full run
python main.py --dry-run                  # Print only, no output
python main.py --source jsearch           # JSearch only
python main.py --source wellfound         # Wellfound only (free, no API key)
python main.py --max-queries 10           # Use more API budget
```

## Adding New Sources (Phase 2)

The architecture is modular. To add a new source:

1. Create `scrapers/newsource.py` with a `run_newsource_scraper()` function
2. Return list of dicts matching the schema in `config.py`
3. Import and add to the pipeline in `main.py`

Planned sources: VC portfolio pages, Welcome to the Jungle, Crunchbase funding events.
