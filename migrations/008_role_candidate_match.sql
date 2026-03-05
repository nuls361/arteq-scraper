-- Migration 008: Role-Candidate matching table
-- Stores scored matches between hot roles and candidates from the research agent

CREATE TABLE IF NOT EXISTS role_candidate_match (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
    match_score INTEGER DEFAULT 0,        -- 0-100 role-specific fit
    match_reasoning TEXT,                  -- Claude explanation
    function_match BOOLEAN DEFAULT false,
    location_match BOOLEAN DEFAULT false,
    skills_overlap TEXT[],
    status TEXT DEFAULT 'proposed',        -- proposed → reviewed → accepted → rejected
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(role_id, candidate_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_rcm_role ON role_candidate_match(role_id);
CREATE INDEX IF NOT EXISTS idx_rcm_candidate ON role_candidate_match(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rcm_score ON role_candidate_match(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_rcm_status ON role_candidate_match(status);

-- Add research_status to role table
-- pending → researching → complete
ALTER TABLE role ADD COLUMN IF NOT EXISTS research_status TEXT DEFAULT 'pending';
