-- 012: Instantly.ai integration columns on outreach table

ALTER TABLE outreach ADD COLUMN IF NOT EXISTS instantly_lead_id TEXT;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS email_opened BOOLEAN DEFAULT false;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS times_opened INT DEFAULT 0;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS bounced BOOLEAN DEFAULT false;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS sequence_step INT DEFAULT 1;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS follow_up_reasoning TEXT;
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS sender_name TEXT DEFAULT 'Lena';
ALTER TABLE outreach ADD COLUMN IF NOT EXISTS sender_email TEXT;

CREATE INDEX IF NOT EXISTS idx_outreach_open_sequences
  ON outreach(contact_id, status)
  WHERE status = 'sent' AND got_reply = false;
