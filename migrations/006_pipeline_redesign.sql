-- 006_pipeline_redesign.sql
-- Redesign: two data streams (Roles + Signals) feeding two separate pipelines
-- Run: psql or apply via Supabase SQL editor

-- ═══════════════════════════════════════════════════════════
-- role: hot classification
-- ═══════════════════════════════════════════════════════════
ALTER TABLE role ADD COLUMN IF NOT EXISTS is_hot BOOLEAN DEFAULT false;
ALTER TABLE role ADD COLUMN IF NOT EXISTS classification_reason TEXT;

-- ═══════════════════════════════════════════════════════════
-- signal: hot classification
-- ═══════════════════════════════════════════════════════════
ALTER TABLE signal ADD COLUMN IF NOT EXISTS is_hot BOOLEAN DEFAULT false;
ALTER TABLE signal ADD COLUMN IF NOT EXISTS interim_relevance TEXT;

-- ═══════════════════════════════════════════════════════════
-- company: enrichment tracking
-- ═══════════════════════════════════════════════════════════
ALTER TABLE company ADD COLUMN IF NOT EXISTS enrichment_status TEXT DEFAULT 'pending';
ALTER TABLE company ADD COLUMN IF NOT EXISTS pipeline_type TEXT;

-- ═══════════════════════════════════════════════════════════
-- contact: deep enrichment
-- ═══════════════════════════════════════════════════════════
ALTER TABLE contact ADD COLUMN IF NOT EXISTS enrichment_status TEXT DEFAULT 'pending';
ALTER TABLE contact ADD COLUMN IF NOT EXISTS career_history JSONB;
ALTER TABLE contact ADD COLUMN IF NOT EXISTS thought_leadership JSONB;
ALTER TABLE contact ADD COLUMN IF NOT EXISTS decision_maker_score INTEGER;

-- ═══════════════════════════════════════════════════════════
-- opportunity table (two pipelines: role + company)
-- ═══════════════════════════════════════════════════════════
-- Stages: new → enriching → ready_for_outreach → sdr_contacted → replied
--         → qualified → meeting → proposal → closed_won / closed_lost

CREATE TABLE IF NOT EXISTS opportunity (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_type TEXT NOT NULL,  -- 'role' or 'company'
  stage TEXT NOT NULL DEFAULT 'new',
  company_id UUID REFERENCES company(id) ON DELETE CASCADE,
  role_id UUID REFERENCES role(id) ON DELETE SET NULL,
  signal_id UUID REFERENCES signal(id) ON DELETE SET NULL,
  owner TEXT,  -- 'sdr', 'ae', 'manual'
  outreach_priority INTEGER,
  meeting_scheduled_at TIMESTAMPTZ,
  proposal_status TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_opportunity_stage ON opportunity(stage);
CREATE INDEX IF NOT EXISTS idx_opportunity_pipeline_type ON opportunity(pipeline_type);
CREATE INDEX IF NOT EXISTS idx_opportunity_company_id ON opportunity(company_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_owner ON opportunity(owner);
CREATE INDEX IF NOT EXISTS idx_company_enrichment_status ON company(enrichment_status);
CREATE INDEX IF NOT EXISTS idx_contact_enrichment_status ON contact(enrichment_status);
