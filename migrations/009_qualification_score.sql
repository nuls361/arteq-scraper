-- 009: Add qualification scoring columns to role table
ALTER TABLE role ADD COLUMN IF NOT EXISTS qualification_score INTEGER DEFAULT 0;
ALTER TABLE role ADD COLUMN IF NOT EXISTS score_breakdown JSONB;
ALTER TABLE role ADD COLUMN IF NOT EXISTS final_score INTEGER;
