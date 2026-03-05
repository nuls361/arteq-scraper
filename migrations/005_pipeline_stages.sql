-- ═══════════════════════════════════════════════════════════
-- Migration 005: Pipeline Stages & SDR/AE Handoff
-- ═══════════════════════════════════════════════════════════

-- Pipeline stage on company level
ALTER TABLE company ADD COLUMN IF NOT EXISTS pipeline_stage TEXT DEFAULT 'prospect'
  CHECK (pipeline_stage IN ('prospect', 'sdr_outreach', 'sdr_followup', 'qualified', 'meeting_prep', 'meeting_done', 'proposal', 'closed_won', 'closed_lost', 'nurture'));

-- Track which agent owns the relationship
ALTER TABLE company ADD COLUMN IF NOT EXISTS agent_owner TEXT DEFAULT 'sdr'
  CHECK (agent_owner IN ('sdr', 'ae', 'manual'));

-- When the handoff happened
ALTER TABLE company ADD COLUMN IF NOT EXISTS handoff_at TIMESTAMPTZ;
ALTER TABLE company ADD COLUMN IF NOT EXISTS handoff_reason TEXT;

-- AE-specific fields
ALTER TABLE company ADD COLUMN IF NOT EXISTS meeting_scheduled_at TIMESTAMPTZ;
ALTER TABLE company ADD COLUMN IF NOT EXISTS meeting_notes TEXT;
ALTER TABLE company ADD COLUMN IF NOT EXISTS proposal_status TEXT
  CHECK (proposal_status IN ('none', 'drafting', 'sent', 'accepted', 'rejected'));

-- ── Meeting Prep table ────────────────────────────────────

CREATE TABLE IF NOT EXISTS meeting_prep (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID REFERENCES company(id) ON DELETE CASCADE,
  meeting_date TIMESTAMPTZ,
  briefing_html TEXT,
  stakeholders JSONB DEFAULT '[]',
  hypotheses JSONB DEFAULT '[]',
  talking_points JSONB DEFAULT '[]',
  red_flags JSONB DEFAULT '[]',
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'reviewed')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meeting_prep_company ON meeting_prep(company_id);

-- ── Proposal Drafts table ─────────────────────────────────

CREATE TABLE IF NOT EXISTS proposal_draft (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID REFERENCES company(id) ON DELETE CASCADE,
  contact_id UUID REFERENCES contact(id),
  title TEXT,
  content_html TEXT,
  executive_profile JSONB,
  engagement_model JSONB,
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'accepted', 'rejected')),
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proposal_company ON proposal_draft(company_id);

-- ── Pipeline stage indexes ────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_company_pipeline ON company(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_company_agent_owner ON company(agent_owner);

-- ── Backfill: companies with sent outreach → sdr_outreach ──

UPDATE company SET pipeline_stage = 'sdr_outreach', agent_owner = 'sdr'
WHERE id IN (
  SELECT DISTINCT company_id FROM outreach WHERE status = 'sent' AND direction = 'outbound'
) AND pipeline_stage = 'prospect';

-- Companies with positive replies → qualified (AE takes over)
UPDATE company SET pipeline_stage = 'qualified', agent_owner = 'ae',
  handoff_at = now(), handoff_reason = 'auto: positive reply sentiment'
WHERE id IN (
  SELECT DISTINCT company_id FROM outreach
  WHERE reply_sentiment IN ('interested', 'positive') AND direction = 'inbound'
) AND pipeline_stage IN ('prospect', 'sdr_outreach', 'sdr_followup');
