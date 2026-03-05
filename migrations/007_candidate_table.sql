-- Migration 007: Candidate table (supply side)
-- Stores Interim Managers, Fractional Executives, Freelance Advisors, Independent Consultants

CREATE TABLE IF NOT EXISTS candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    -- Identity
    full_name TEXT NOT NULL,
    email TEXT,
    email_status TEXT,  -- 'verified', 'unverified', 'missing'
    phone TEXT,
    linkedin_url TEXT,

    -- Professional
    current_title TEXT,
    function TEXT,  -- cfo, cto, coo, chro, cpo, cmo, md, other
    employment_type TEXT,  -- interim, fractional, advisor, freelance

    -- Location
    location_city TEXT,
    location_country TEXT,

    -- Availability
    availability_signal TEXT,  -- e.g. "Malt profile active", "Substack: 2x/week"

    -- Source
    source TEXT NOT NULL,  -- pdl, comatch, expertlead, malt, substack, linkedin, medium, apollo
    source_url TEXT,

    -- Profile
    skills TEXT[],
    score INTEGER DEFAULT 0,
    tier TEXT,  -- available, passive, research
    notes TEXT,

    -- Tracking
    last_seen_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_candidate_linkedin ON candidate(linkedin_url);
CREATE INDEX IF NOT EXISTS idx_candidate_tier ON candidate(tier);
CREATE INDEX IF NOT EXISTS idx_candidate_function ON candidate(function);
CREATE INDEX IF NOT EXISTS idx_candidate_score ON candidate(score DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_linkedin_unique ON candidate(linkedin_url) WHERE linkedin_url IS NOT NULL;
