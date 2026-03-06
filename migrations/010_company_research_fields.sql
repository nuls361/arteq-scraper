-- Add company research fields from Claude company research agent
ALTER TABLE company ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE company ADD COLUMN IF NOT EXISTS investors TEXT;
ALTER TABLE company ADD COLUMN IF NOT EXISTS revenue TEXT;
ALTER TABLE company ADD COLUMN IF NOT EXISTS founders TEXT;
ALTER TABLE company ADD COLUMN IF NOT EXISTS funding_amount TEXT;
