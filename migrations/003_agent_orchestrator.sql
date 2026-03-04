-- ═══════════════════════════════════════════════════════════
-- Migration 003: Agent Orchestrator Tables
-- ═══════════════════════════════════════════════════════════

-- Agent configuration (key-value settings)
CREATE TABLE IF NOT EXISTS agent_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO agent_config (key, value) VALUES
  ('apollo_daily_credit_budget', '25'),
  ('apollo_monthly_credit_budget', '500'),
  ('role_expire_days', '60'),
  ('auto_promote_signal_threshold', '2'),
  ('auto_downgrade_days_inactive', '30'),
  ('outreach_mode', 'draft'),
  ('outreach_daily_limit', '3'),
  ('outreach_from_email', 'niels@arteq.app'),
  ('outreach_cc', 'niels@arteq.app')
ON CONFLICT (key) DO NOTHING;

-- Agent decision audit trail
CREATE TABLE IF NOT EXISTS agent_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id UUID,
  reason TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_log_created ON agent_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_log_entity ON agent_log(entity_type, entity_id);

-- Outreach tracking
CREATE TABLE IF NOT EXISTS outreach (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  company_id UUID REFERENCES company(id),
  contact_id UUID REFERENCES contact(id),
  subject TEXT NOT NULL,
  body_html TEXT NOT NULL,
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'replied', 'bounced')),
  sent_at TIMESTAMPTZ,
  resend_email_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outreach_company ON outreach(company_id);
CREATE INDEX IF NOT EXISTS idx_outreach_contact ON outreach(contact_id);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach(status);

-- Apollo credit tracking
CREATE TABLE IF NOT EXISTS apollo_credit_ledger (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  action TEXT NOT NULL,
  credits INTEGER NOT NULL,
  contact_id UUID,
  company_id UUID
);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_date ON apollo_credit_ledger(created_at);

-- ── Extend existing tables ──────────────────────────────

ALTER TABLE company ADD COLUMN IF NOT EXISTS signal_density INTEGER DEFAULT 0;
ALTER TABLE company ADD COLUMN IF NOT EXISTS composite_score REAL;
ALTER TABLE company ADD COLUMN IF NOT EXISTS outreach_priority INTEGER;
ALTER TABLE company ADD COLUMN IF NOT EXISTS last_orchestrator_eval TIMESTAMPTZ;

ALTER TABLE contact ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;

-- ── RLS Policies ────────────────────────────────────────

ALTER TABLE agent_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read agent_config" ON agent_config FOR SELECT USING (true);
CREATE POLICY "Allow anon write agent_config" ON agent_config FOR ALL USING (true);

ALTER TABLE agent_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read agent_log" ON agent_log FOR SELECT USING (true);
CREATE POLICY "Allow anon insert agent_log" ON agent_log FOR INSERT WITH CHECK (true);

ALTER TABLE outreach ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon all outreach" ON outreach FOR ALL USING (true);

ALTER TABLE apollo_credit_ledger ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon all apollo_credit_ledger" ON apollo_credit_ledger FOR ALL USING (true);
