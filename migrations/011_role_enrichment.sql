-- 011: Role enrichment fields + dossier role link
-- Adds decision maker + sourcing brief columns to role table,
-- and links company_dossier entries to specific roles.

-- Role enrichment fields
ALTER TABLE role ADD COLUMN IF NOT EXISTS enrichment_status TEXT DEFAULT 'pending';
ALTER TABLE role ADD COLUMN IF NOT EXISTS hiring_manager_name TEXT;
ALTER TABLE role ADD COLUMN IF NOT EXISTS hiring_manager_title TEXT;
ALTER TABLE role ADD COLUMN IF NOT EXISTS hiring_manager_linkedin TEXT;
ALTER TABLE role ADD COLUMN IF NOT EXISTS hiring_manager_confidence TEXT;
ALTER TABLE role ADD COLUMN IF NOT EXISTS sourcing_brief JSONB;

-- Link dossier entries to specific roles
ALTER TABLE company_dossier ADD COLUMN IF NOT EXISTS role_id UUID;

-- Index for pending role enrichment
CREATE INDEX IF NOT EXISTS idx_role_enrichment_status ON role(enrichment_status);

-- Add new entry types to company_dossier CHECK constraint
-- Drop and recreate to include role_analysis and role_dm_research
ALTER TABLE company_dossier DROP CONSTRAINT IF EXISTS company_dossier_entry_type_check;
ALTER TABLE company_dossier ADD CONSTRAINT company_dossier_entry_type_check
  CHECK (entry_type IN (
    'signal', 'news', 'meeting_note', 'note', 'file',
    'agent_action', 'contact_intel', 'outreach',
    'role_analysis', 'role_dm_research'
  ));
