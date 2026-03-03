-- ═══════════════════════════════════════════════════════════
-- Company Dossier: Living intelligence document per company
-- Run this in Supabase SQL Editor
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS company_dossier (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_id  UUID NOT NULL REFERENCES company(id) ON DELETE CASCADE,

    -- Entry classification
    entry_type  TEXT NOT NULL CHECK (entry_type IN (
        'signal',           -- auto: from signal_scraper
        'news',             -- auto: from RSS/DDG without signal classification
        'meeting_note',     -- manual: notes from meetings
        'note'              -- manual: general observations
    )),

    -- Content
    title       TEXT,
    content     TEXT NOT NULL,
    source      TEXT,           -- e.g. "rss_techcrunch", "web_search", "manual"
    source_url  TEXT,
    signal_id   UUID REFERENCES signal(id) ON DELETE SET NULL,  -- link back to signal if applicable

    -- Metadata
    author      TEXT,           -- who wrote the note (for manual entries)
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Fast lookups: all dossier entries for a company, newest first
CREATE INDEX idx_dossier_company_date ON company_dossier (company_id, created_at DESC);

-- Fast lookups by type
CREATE INDEX idx_dossier_type ON company_dossier (entry_type);

-- ═══════════════════════════════════════════════════════════
-- Backfill: copy existing signals into dossier as initial entries
-- ═══════════════════════════════════════════════════════════

INSERT INTO company_dossier (company_id, entry_type, title, content, source, source_url, signal_id, created_at)
SELECT
    s.company_id,
    'signal',
    s.title,
    COALESCE(s.description, s.title, ''),
    s.source,
    s.source_url,
    s.id,
    COALESCE(s.detected_at, s.created_at, now())
FROM signal s
WHERE s.company_id IS NOT NULL
ON CONFLICT DO NOTHING;
