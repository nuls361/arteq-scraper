# A-Line Database Schema

## Entity Relationship Overview

```
Signal ──────┐
             ▼
Role ──► Opportunity ◄──► Candidate Assignment
             │
             ▼
          Company ◄──► Contact
             │
             ▼
          Activity
```

---

## 1. Company

Die Firma. Lebt ewig. Wird enriched. Zentrale Entität.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `name` | text, required | Firmenname |
| `domain` | text, unique | Website-Domain (z.B. simscale.com) |
| `website` | text | Volle URL |
| `industry` | text | Branche |
| `description` | text | Was macht die Firma (1-2 Sätze) |
| `logo_url` | text | Logo |
| `status` | enum | `lead → prospect → active → client → churned → disqualified` |
| `source` | enum | `scraper, linkedin, referral, outbound, inbound, event` |
| `source_detail` | text | Welcher Scraper, wer hat empfohlen etc. |
| **Firmographics** | | |
| `founded_year` | integer | Gründungsjahr |
| `headcount` | text | Mitarbeiterzahl oder Range ("50-100") |
| `funding_stage` | enum | `bootstrapped, pre_seed, seed, series_a, series_b, series_c, late_stage, public, pe_backed, unknown` |
| `funding_amount` | text | Gesamtfunding |
| `investors` | text | Komma-getrennt |
| `tech_stack` | text | Erkannte Technologien |
| `hq_city` | text | Hauptsitz Stadt |
| `hq_country` | text | Land |
| **A-Line Intelligence** | | |
| `a-line_fit` | enum | `high, medium, low, unknown` |
| `a-line_fit_reason` | text | Warum guter/schlechter Fit |
| `tags` | text[] | Freie Labels, z.B. ["PE-backed", "IPO-kandidat", "Netzwerk-Kontakt"] |
| `is_agency` | boolean, default false | Ist Personalberatung/Konkurrent |
| `agency_reason` | text | Warum als Agency erkannt |
| **Timestamps** | | |
| `first_seen_at` | timestamp | Wann erstmalig im System |
| `last_enriched_at` | timestamp | Letzte Enrichment-Runde |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 1b. Investor

VC-Firmen, PE-Häuser, Angels. Verknüpft mit Companies über Junction Table.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `name` | text, required | z.B. "Earlybird", "HV Capital", "General Atlantic" |
| `type` | enum | `vc, pe, angel, family_office, corporate, other` |
| `website` | text | |
| `hq_country` | text | |
| `focus_stages` | text[] | z.B. ["seed", "series_a", "series_b"] |
| `focus_industries` | text[] | z.B. ["SaaS", "FinTech"] |
| `notable_portfolio` | text[] | Bekannte Portfolio-Companies |
| `notes` | text | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 1c. Company_Investor (Junction)

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company | |
| `investor_id` | uuid, FK → Investor | |
| `round` | text | z.B. "Series A", "Seed" |
| `amount` | text | Investierter Betrag |
| `announced_at` | date | |
| `source_url` | text | |
| `created_at` | timestamp | |

---

Person bei einer Firma. Decision Maker, Champion, Blocker, HR etc.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company | Aktuelle Firma |
| `first_name` | text | |
| `last_name` | text | |
| `email` | text | |
| `phone` | text | |
| `linkedin_url` | text | |
| `title` | text | Jobtitel (z.B. "CEO", "VP People") |
| `role_type` | enum | `decision_maker, champion, blocker, influencer, hr, other` |
| `seniority` | enum | `c_level, vp, director, manager, other` |
| `is_primary` | boolean | Hauptansprechpartner für diese Company |
| `source` | enum | `scraped, linkedin, enriched, manual, referral` |
| `notes` | text | Freitext-Notizen |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 3. Role

Roh-Daten aus dem Scraper. Ein Fund. Kann zu einer Opportunity werden.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company | Zugehörige Firma |
| `opportunity_id` | uuid, FK → Opportunity, nullable | Verknüpfte Opportunity (wenn qualifiziert) |
| `title` | text, required | Jobtitel wie gescraped |
| `description` | text | Vollständige Jobbeschreibung |
| `location` | text | Standort |
| `is_remote` | boolean | |
| `url` | text | Link zum Original-Posting |
| `source` | enum | `jsearch, arbeitnow, jobicy, remoteok, wellfound, linkedin, wttj, manual` |
| `posted_at` | date | Veröffentlichungsdatum |
| `scraped_at` | timestamp | Wann gescraped |
| **Scoring** | | |
| `rule_score` | integer | Rule-based Score (0-100) |
| `ai_score` | integer | Claude AI Score (0-100) |
| `final_score` | integer | Finaler Score |
| `tier` | enum | `hot, warm, parked, disqualified` |
| `signals` | text[] | Array von erkannten Signalen |
| **AI Analysis** | | |
| `engagement_type` | enum | `fractional, interim, full_time, convertible, unknown` |
| `engagement_reasoning` | text | |
| `requirements_summary` | text | Wichtigste Anforderungen |
| `decision_maker_guess` | text | Vermuteter Hiring Manager |
| `company_stage_guess` | text | |
| **Status** | | |
| `status` | enum | `new → reviewed → qualified → converted → rejected → expired` |
| `reviewed_at` | timestamp | Wann manuell angesehen |
| `reviewed_by` | text | Wer hat reviewed |
| `rejection_reason` | text | Falls rejected: warum |
| **Semantic Search (pgvector)** | | |
| `embedding` | vector(1536) | Embedding der Job-Description — für Kandidaten-Matching |
| `embedding_updated_at` | timestamp | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 4. Opportunity

Das Mandat. Was monetarisiert wird. Ein konkretes Engagement bei einer Firma.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company, required | |
| `primary_contact_id` | uuid, FK → Contact, nullable | Hauptansprechpartner |
| `title` | text, required | z.B. "Interim CFO für IPO-Vorbereitung" |
| `description` | text | Kontext, Hintergrund, Anforderungen |
| `origin` | enum | `role, signal, referral, outbound, inbound` |
| `origin_role_id` | uuid, FK → Role, nullable | Falls aus Role entstanden |
| `origin_signal_id` | uuid, FK → Signal, nullable | Falls aus Signal entstanden |
| **Engagement Details** | | |
| `engagement_type` | enum | `fractional, interim, permanent, advisory, project` |
| `start_date` | date | Geplanter/tatsächlicher Start |
| `end_date` | date | Geplantes Ende |
| `duration_months` | integer | |
| `days_per_week` | decimal | z.B. 2.5 für Fractional |
| `daily_rate_min` | decimal | Budget-Range unten |
| `daily_rate_max` | decimal | Budget-Range oben |
| `currency` | text, default 'EUR' | |
| **Pipeline** | | |
| `stage` | enum | `identified → qualified → proposal_sent → negotiation → won → delivery → completed → lost` |
| `probability` | integer | Win-Wahrscheinlichkeit 0-100% |
| `expected_revenue` | decimal | Geschätzter Gesamtumsatz |
| `actual_revenue` | decimal | Tatsächlicher Umsatz |
| `lost_reason` | text | Falls lost: warum |
| `won_at` | timestamp | |
| `lost_at` | timestamp | |
| **Urgency** | | |
| `urgency` | enum | `critical, high, medium, low` |
| `urgency_reason` | text | |
| `deadline` | date | Wann muss besetzt sein |
| **Owner** | | |
| `owner` | text | Wer bei A-Line verantwortlich |
| `tags` | text[] | Freie Labels, z.B. ["PE-portfolio", "Referral", "Dringend"] |
| `notes` | text | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 5. Candidate

Interim Manager / Fractional Executive. Supply Side.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `first_name` | text, required | |
| `last_name` | text, required | |
| `email` | text | |
| `phone` | text | |
| `linkedin_url` | text | |
| `website` | text | Persönliche Website/Portfolio |
| `photo_url` | text | |
| **Professional Profile** | | |
| `headline` | text | Kurzbeschreibung ("Interim CFO, Ex-Big4, Startup-Erfahrung") |
| `bio` | text | Ausführliches Profil |
| `specializations` | text[] | z.B. ["CFO", "IPO-Vorbereitung", "Post-Merger Integration"] |
| `industries` | text[] | z.B. ["SaaS", "FinTech", "E-Commerce"] |
| `seniority` | enum | `c_level, vp, director, senior_manager` |
| `years_experience` | integer | |
| `languages` | text[] | z.B. ["Deutsch", "Englisch", "Französisch"] |
| **Availability** | | |
| `status` | enum | `available, partially_available, engaged, unavailable, inactive` |
| `available_from` | date | Ab wann verfügbar |
| `available_days_per_week` | decimal | z.B. 3.0 |
| `preferred_engagement` | text[] | `["fractional", "interim", "permanent", "advisory"]` — text[] statt enum[] für ORM-Kompatibilität |
| `preferred_duration_min` | integer | Min Monate |
| `preferred_duration_max` | integer | Max Monate |
| **Commercial** | | |
| `daily_rate` | decimal | Standard-Tagessatz |
| `daily_rate_min` | decimal | Verhandlungsspielraum unten |
| `currency` | text, default 'EUR' | |
| `location` | text | Wohnort |
| `willing_to_relocate` | boolean | |
| `remote_preference` | enum | `remote_only, hybrid, onsite, flexible` |
| `travel_willingness` | enum | `none, regional, national, international` |
| **Performance (A-Line Intelligence)** | | |
| `placements_count` | integer, default 0 | Wie oft über A-Line platziert |
| `avg_rating` | decimal | Durchschnittliche Mandanten-Bewertung |
| `nps_score` | integer | Net Promoter Score |
| `last_placement_at` | date | |
| `company_history` | text[] | Frühere Arbeitgeber, z.B. ["SAP", "Zalando", "McKinsey"] — für Matching und Suche |
| `tags` | text[] | Freie Labels, z.B. ["IPO-Erfahrung", "Series-B", "Restrukturierung"] |
| `notes` | text | Interne Notizen |
| **Source** | | |
| `source` | enum | `referral, linkedin, application, network, event, scraped` |
| `source_detail` | text | |
| `cv_url` | text | Link zum CV |
| **Semantic Search (pgvector)** | | |
| `embedding` | vector(1536) | OpenAI/Claude Embedding des Profils (bio + specializations + company_history) — für semantisches Matching |
| `embedding_updated_at` | timestamp | Wann zuletzt neu berechnet |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 6. Candidate Assignment (Junction Table)

Verknüpfung Candidate ↔ Opportunity. Ein Kandidat kann für mehrere Opportunities vorgeschlagen werden.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `opportunity_id` | uuid, FK → Opportunity | |
| `candidate_id` | uuid, FK → Candidate | |
| `status` | enum | `longlisted → shortlisted → presented → interviewing → offered → placed → rejected → withdrawn` |
| `presented_at` | timestamp | Wann dem Kunden vorgestellt |
| `client_feedback` | text | Feedback vom Mandanten |
| `rejection_reason` | text | |
| `match_score` | integer | AI-Match-Score (0-100) |
| `match_reasoning` | text | Warum guter/schlechter Fit |
| `daily_rate_proposed` | decimal | Vorgeschlagener Tagessatz |
| `started_at` | date | Engagement Start |
| `ended_at` | date | Engagement Ende |
| `performance_rating` | decimal | Bewertung nach Einsatz (1-5) |
| `performance_notes` | text | |
| `notes` | text | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 7. Activity

Jede Interaktion. Timeline eines Leads/Mandaten.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company | |
| `contact_id` | uuid, FK → Contact, nullable | |
| `opportunity_id` | uuid, FK → Opportunity, nullable | |
| `candidate_id` | uuid, FK → Candidate, nullable | |
| `type` | enum | `email_sent, email_received, linkedin_sent, linkedin_received, call, meeting, note, proposal_sent, contract_sent, status_change, system` |
| `direction` | enum | `inbound, outbound, internal` |
| `subject` | text | Betreff / Kurzbeschreibung |
| `body` | text | Volltext / Notizen |
| `channel` | enum | `email, linkedin, phone, whatsapp, in_person, video, system` |
| `scheduled_at` | timestamp | Falls geplant (Meeting etc.) |
| `completed_at` | timestamp | Wann durchgeführt |
| `outcome` | text | Ergebnis (z.B. "Interesse, will Profil sehen") |
| `next_action` | text | Nächster Schritt |
| `next_action_date` | date | Deadline für nächsten Schritt |
| `created_by` | text | Wer hat die Activity erstellt |
| `created_at` | timestamp | |

---

## 8. Signal

Externe Trigger-Events. RSS, Handelsregister, Funding News, Leadership Changes.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company, nullable | Falls Company schon bekannt |
| `company_name_raw` | text | Firmenname wie im Signal |
| `type` | enum | `funding_round, leadership_change, layoff, expansion, acquisition, ipo, restructuring, product_launch, regulatory, hiring_surge, other` |
| `source` | enum | `rss_techcrunch, rss_handelsblatt, rss_gruenderszene, handelsregister, bundesanzeiger, crunchbase, linkedin, manual` |
| `source_url` | text | Link zur Quelle |
| `title` | text | Signal-Titel |
| `description` | text | Details |
| `relevance_score` | integer | AI-Relevanz (0-100) |
| `urgency` | enum | `high, medium, low` |
| `detected_at` | timestamp | Wann erkannt |
| `processed` | boolean, default false | Wurde bearbeitet |
| `processed_at` | timestamp | |
| `action_taken` | text | Was wurde gemacht |
| `created_opportunity_id` | uuid, FK → Opportunity, nullable | Falls daraus Opportunity entstanden |
| `created_at` | timestamp | |

---

## 9. Outreach Template

Vorlagen für personalisierte Nachrichten.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `name` | text | Template-Name |
| `channel` | enum | `linkedin, email, phone` |
| `type` | enum | `first_touch, follow_up_1, follow_up_2, breakup, referral_ask, warm_intro` |
| `subject` | text | E-Mail-Betreff (Template mit Variablen) |
| `body` | text | Template-Body mit Variablen: {{company}}, {{contact_name}}, {{role_title}}, {{signal}} |
| `language` | enum | `de, en` |
| `is_active` | boolean, default true | |
| `usage_count` | integer, default 0 | Wie oft verwendet |
| `response_rate` | decimal | Antwortquote |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 10. Enrichment Log

Protokoll aller Enrichment-Durchläufe. Für Debugging und Kosten-Tracking.

| Field | Type | Description |
|-------|------|-------------|
| `id` | uuid, PK | |
| `company_id` | uuid, FK → Company | |
| `source` | enum | `claude_website, apollo, crunchbase, linkedin, handelsregister, manual` |
| `status` | enum | `success, partial, failed` |
| `data_retrieved` | jsonb | Was wurde gefunden |
| `tokens_used` | integer | Claude API Token-Verbrauch |
| `cost_eur` | decimal | Geschätzte Kosten |
| `error_message` | text | Falls fehlgeschlagen |
| `created_at` | timestamp | |

---

## Key Relationships

```
Company 1 ←→ N Contact
Company 1 ←→ N Role
Company 1 ←→ N Opportunity
Company 1 ←→ N Signal
Company 1 ←→ N Activity
Company 1 ←→ N Enrichment Log
Company N ←→ M Investor  (via company_investor)

Opportunity 1 ←→ N Candidate Assignment
Opportunity 1 ←→ 1 Primary Contact
Opportunity 0..1 ←→ 1 Origin Role
Opportunity 0..1 ←→ 1 Origin Signal
Opportunity 1 ←→ N Activity

Candidate 1 ←→ N Candidate Assignment

Contact 1 ←→ N Activity

Role N ←→ 1 Company
Role 0..1 ←→ 1 Opportunity
```

---

## Indexes

```sql
-- Performance-critical queries
CREATE INDEX idx_company_status ON company(status);
CREATE INDEX idx_company_a-line_fit ON company(a-line_fit);
CREATE INDEX idx_role_tier ON role(tier);
CREATE INDEX idx_role_status ON role(status);
CREATE INDEX idx_role_company ON role(company_id);
CREATE INDEX idx_opportunity_stage ON opportunity(stage);
CREATE INDEX idx_opportunity_company ON opportunity(company_id);
CREATE INDEX idx_signal_company ON signal(company_id);
CREATE INDEX idx_signal_processed ON signal(processed);
CREATE INDEX idx_activity_company ON activity(company_id);
CREATE INDEX idx_activity_opportunity ON activity(opportunity_id);
CREATE INDEX idx_candidate_status ON candidate(status);
CREATE INDEX idx_candidate_assignment_status ON candidate_assignment(status);
-- GIN Indexes für Array-Felder (tags, specializations, company_history)
CREATE INDEX idx_company_tags ON company USING GIN(tags);
CREATE INDEX idx_candidate_tags ON candidate USING GIN(tags);
CREATE INDEX idx_candidate_specializations ON candidate USING GIN(specializations);
CREATE INDEX idx_candidate_company_history ON candidate USING GIN(company_history);
CREATE INDEX idx_opportunity_tags ON opportunity USING GIN(tags);

-- pgvector HNSW Indexes (schnellste ANN-Suche in Supabase)
CREATE INDEX idx_candidate_embedding ON candidate USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_role_embedding ON role USING hnsw (embedding vector_cosine_ops);

-- Investor
CREATE INDEX idx_company_investor_company ON company_investor(company_id);
CREATE INDEX idx_company_investor_investor ON company_investor(investor_id);
CREATE UNIQUE INDEX idx_role_dedup ON role(company_id, title, source);
-- Cross-source dedup: verhindert dass dasselbe Posting von JSearch + Arbeitnow doppelt landet
CREATE UNIQUE INDEX idx_role_dedup_url ON role(md5(url)) WHERE url IS NOT NULL;
```

---

## Enum Definitions

## Architecture Decision: SQL + pgvector (Final)

**Stack: Supabase PostgreSQL + pgvector. Kein separater Graph.**

**pgvector für semantisches Matching:**
- `candidate.embedding` + `role.embedding` (je vector(1536))
- Kandidaten-Matching: cosine similarity zwischen Job-Description-Embedding und Kandidaten-Profil-Embedding
- Berechnungslogik: `bio || specializations || company_history` → Embedding → gespeichert in DB
- Supabase hat pgvector nativ — kein Extra-Setup

**Investor-Tabelle für späteres Netzwerk-Mapping:**
- `investor` + `company_investor` Junction jetzt angelegt
- Befüllung passiert schrittweise via Enrichment (Crunchbase API)
- Ermöglicht später: "Welche meiner Leads hat HV Capital finanziert?" — simpler JOIN, kein Graph nötig
- Multi-Hop PE-Netzwerk-Queries (3+ Hops) können mit recursive CTEs abgebildet werden; Graph-Migration bleibt Option wenn das zu schmerzhaft wird

---

```sql
-- Company
CREATE TYPE company_status AS ENUM ('lead', 'prospect', 'active', 'client', 'churned', 'disqualified');
CREATE TYPE company_source AS ENUM ('scraper', 'linkedin', 'referral', 'outbound', 'inbound', 'event');
CREATE TYPE funding_stage AS ENUM ('bootstrapped', 'pre_seed', 'seed', 'series_a', 'series_b', 'series_c', 'late_stage', 'public', 'pe_backed', 'unknown');
CREATE TYPE fit_level AS ENUM ('high', 'medium', 'low', 'unknown');

-- Role
CREATE TYPE role_source AS ENUM ('jsearch', 'arbeitnow', 'jobicy', 'remoteok', 'wellfound', 'linkedin', 'wttj', 'manual');
CREATE TYPE role_tier AS ENUM ('hot', 'warm', 'parked', 'disqualified');
CREATE TYPE role_status AS ENUM ('new', 'reviewed', 'qualified', 'converted', 'rejected', 'expired');
CREATE TYPE engagement_type AS ENUM ('fractional', 'interim', 'full_time', 'convertible', 'advisory', 'project', 'unknown');

-- Opportunity
CREATE TYPE opportunity_origin AS ENUM ('role', 'signal', 'referral', 'outbound', 'inbound');
CREATE TYPE opportunity_stage AS ENUM ('identified', 'qualified', 'proposal_sent', 'negotiation', 'won', 'delivery', 'completed', 'lost');
CREATE TYPE urgency_level AS ENUM ('critical', 'high', 'medium', 'low');

-- Candidate
CREATE TYPE candidate_status AS ENUM ('available', 'partially_available', 'engaged', 'unavailable', 'inactive');
CREATE TYPE remote_preference AS ENUM ('remote_only', 'hybrid', 'onsite', 'flexible');

-- Candidate Assignment
CREATE TYPE assignment_status AS ENUM ('longlisted', 'shortlisted', 'presented', 'interviewing', 'offered', 'placed', 'rejected', 'withdrawn');

-- Activity
CREATE TYPE activity_type AS ENUM ('email_sent', 'email_received', 'linkedin_sent', 'linkedin_received', 'call', 'meeting', 'note', 'proposal_sent', 'contract_sent', 'status_change', 'system');
CREATE TYPE activity_direction AS ENUM ('inbound', 'outbound', 'internal');
CREATE TYPE activity_channel AS ENUM ('email', 'linkedin', 'phone', 'whatsapp', 'in_person', 'video', 'system');

-- Signal
CREATE TYPE signal_type AS ENUM ('funding_round', 'leadership_change', 'layoff', 'expansion', 'acquisition', 'ipo', 'restructuring', 'product_launch', 'regulatory', 'hiring_surge', 'other');
CREATE TYPE signal_source AS ENUM ('rss_techcrunch', 'rss_handelsblatt', 'rss_gruenderszene', 'handelsregister', 'bundesanzeiger', 'crunchbase', 'linkedin', 'manual');
```
