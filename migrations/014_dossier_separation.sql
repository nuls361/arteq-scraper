-- 014: Dossier separation — per-role, per-contact dossier threads
-- Adds contact_id FK, proper role_id FK, makes company_id nullable,
-- expands entry_type, adds owner constraint + indexes.
-- Existing data is preserved — company_id stays where it is.

-- Add contact_id FK
ALTER TABLE company_dossier
  ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES contact(id) ON DELETE CASCADE;

-- Add proper FK on role_id (column exists from 011 but without FK)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'company_dossier_role_id_fkey'
      AND table_name = 'company_dossier'
  ) THEN
    ALTER TABLE company_dossier
      ADD CONSTRAINT company_dossier_role_id_fkey
      FOREIGN KEY (role_id) REFERENCES role(id) ON DELETE CASCADE;
  END IF;
END $$;

-- Make company_id nullable (existing rows keep their value)
ALTER TABLE company_dossier
  ALTER COLUMN company_id DROP NOT NULL;

-- At least one FK must be set
ALTER TABLE company_dossier
  DROP CONSTRAINT IF EXISTS dossier_has_owner;
ALTER TABLE company_dossier
  ADD CONSTRAINT dossier_has_owner CHECK (
    company_id IS NOT NULL OR role_id IS NOT NULL OR contact_id IS NOT NULL
  );

-- Expand entry_type to cover role and contact entries
ALTER TABLE company_dossier
  DROP CONSTRAINT IF EXISTS company_dossier_entry_type_check;
ALTER TABLE company_dossier
  ADD CONSTRAINT company_dossier_entry_type_check CHECK (entry_type IN (
    -- Company entries (company_id set)
    'signal',
    'news',
    'company_analysis',
    'funding_event',
    'agent_action',
    -- Role entries (role_id set)
    'role_analysis',
    'role_dm_research',
    'sourcing_brief',
    'decision_maker',
    -- Contact entries (contact_id set)
    'contact_intel',
    'personal_hooks',
    'outreach_history',
    'outreach',
    -- Manual entries (any FK)
    'meeting_note',
    'note',
    'file'
  ));

-- Indexes for per-entity lookups
CREATE INDEX IF NOT EXISTS idx_dossier_role ON company_dossier(role_id, created_at DESC)
  WHERE role_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dossier_contact ON company_dossier(contact_id, created_at DESC)
  WHERE contact_id IS NOT NULL;
