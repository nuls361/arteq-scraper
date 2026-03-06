# A-Line Scraper v10 — Bug Fix Briefing for Claude Code

## Repo
- **GitHub**: `nuls361/a-line-scraper`
- **File**: `quick_run.py` (main branch, ~2003 lines)
- **Runtime**: GitHub Actions, daily at 06:00 UTC

## Current Status
The scraper's first Supabase run failed with 5 bugs. Fixes were identified but manual edits in VS Code introduced Python syntax errors (unclosed try block near line 209, unclosed parens near line 277). The file needs a clean fix.

## IMPORTANT: Start from clean state
```bash
cd ~/a-line-scraper
git checkout quick_run.py   # revert broken manual edits
```

---

## 6 Fixes to Apply to `quick_run.py`

### Fix 1: Claude API model name (400 error)
**Problem**: Model `claude-sonnet-4-20250514` doesn't exist -> 400 on every AI enrichment call.
**Fix**: Replace all 3 occurrences:
```
OLD: "claude-sonnet-4-20250514"
NEW: "claude-sonnet-4-5-20250929"
```
Search for `claude-sonnet-4-20250514` — should appear exactly 3 times. Replace all.

### Fix 2: Claude API error logging
**Problem**: When Claude test fails, the error response body isn't logged.
**Fix**: In the Claude connectivity test section, find:
```python
logger.error(f"Claude API {test.status_code} — falling back to rule-based")
```
Replace with:
```python
logger.error(f"Claude API {test.status_code}: {test.text[:300]} — falling back to rule-based")
```

### Fix 3: JSearch rate limiting (429 errors)
**Problem**: `time.sleep(1)` between JSearch API pages -> 429 rate limit errors.
**Fix**: In `scrape_jsearch()`, find the sleep between page requests (right before the `logger.info(f"JSearch: {len(jobs)} DACH jobs found")` line):
```
OLD: time.sleep(1)
NEW: time.sleep(3)  # Respect rate limits
```
Only change the one inside the JSearch pagination loop.

### Fix 4: Urgency scoring query (broken filter)
**Problem**: Urgency scoring queries Supabase with `"status": "eq.open"` but the `role` table has no `status` column yet.
**Fix**: Find and remove the `"status": "eq.open",` line from the urgency scoring params dict. Keep everything else.

### Fix 5: Source enum values (Supabase constraint violations)
**Problem**: Code sends `"source": "JSearch"` etc., but Supabase `role_source` enum expects lowercase.
**Fix**: Replace these 4 source values:
```
"source": "JSearch"    ->  "source": "jsearch"
"source": "Arbeitnow"  ->  "source": "arbeitnow"
"source": "Jobicy"     ->  "source": "jobicy"
"source": "RemoteOK"   ->  "source": "remoteok"
```

### Fix 6: Company domain duplicate (409 unique constraint)
**Problem**: When two companies share a domain, POST to `company` fails with 409, and the role gets skipped.
**Fix**: In the Supabase insertion section (~line 1413), find:
```python
                result = supabase_request("POST", "company", data=company_data)
                if result and len(result) > 0:
                    company_id = result[0]["id"]
                    company_cache[name_lower] = company_id
                    companies_created += 1
                else:
                    continue
```
Replace the `else: continue` with a fallback domain lookup:
```python
                else:
                    # POST failed (likely 409 domain dupe) - try lookup by domain
                    if domain:
                        existing_by_domain = supabase_request("GET", "company", params={
                            "domain": f"eq.{domain}",
                            "select": "id",
                            "limit": "1",
                        })
                        if existing_by_domain and len(existing_by_domain) > 0:
                            company_id = existing_by_domain[0]["id"]
                            company_cache[name_lower] = company_id
                        else:
                            continue
                    else:
                        continue
```

---

## Supabase SQL Migration (run BEFORE the next scraper run)

Run this in Supabase SQL Editor (Dashboard -> SQL Editor -> New Query):

```sql
ALTER TYPE role_source ADD VALUE IF NOT EXISTS 'jsearch';
ALTER TYPE role_source ADD VALUE IF NOT EXISTS 'arbeitnow';
ALTER TYPE role_source ADD VALUE IF NOT EXISTS 'jobicy';
ALTER TYPE role_source ADD VALUE IF NOT EXISTS 'remoteok';
ALTER TYPE role_status ADD VALUE IF NOT EXISTS 'new';
ALTER TYPE qualification_tier ADD VALUE IF NOT EXISTS 'hot';
ALTER TYPE qualification_tier ADD VALUE IF NOT EXISTS 'warm';
ALTER TYPE qualification_tier ADD VALUE IF NOT EXISTS 'parked';
```

---

## Verification After Fixes

```bash
python3 -c "
import ast
with open('quick_run.py') as f:
    content = f.read()
ast.parse(content)
print('Syntax: OK')
assert 'claude-sonnet-4-20250514' not in content, 'Old model still present'
assert 'claude-sonnet-4-5-20250929' in content, 'New model missing'
assert 'eq.open' not in content, 'eq.open still present'
assert 'sleep(3)' in content, 'Rate limit fix missing'
assert 'existing_by_domain' in content, 'Domain dupe fix missing'
assert '\"source\": \"JSearch\"' not in content, 'Uppercase source still present'
print('All 6 fixes verified!')
"
```

Then:
```bash
git add quick_run.py
git commit -m "fix: Claude model, JSearch rate limit, Supabase enums + domain dupe"
git push
```

---

## Environment
- **Supabase URL**: https://dgrbbvdvziwcxqlyccng.supabase.co
- **GitHub Secrets**: ANTHROPIC_API_KEY, APOLLO_API_KEY, JSEARCH_API_KEY, SUPABASE_URL, SUPABASE_KEY — all configured
