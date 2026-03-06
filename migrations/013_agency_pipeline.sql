-- 013: Agency Pipeline — supply-side partner management
-- Tracks interim management agencies in DACH, their contacts,
-- outreach sequences, and role↔agency matching.

-- Agency table (supply side partners)
CREATE TABLE IF NOT EXISTS agency (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  domain TEXT,
  hq_city TEXT,
  hq_country TEXT DEFAULT 'Germany',
  specialization TEXT[],
  headcount TEXT,
  founded_year INT,
  description TEXT,
  source TEXT,
  enrichment_status TEXT DEFAULT 'pending',
  outreach_status TEXT DEFAULT 'pending',
  is_direct_competitor BOOLEAN DEFAULT false,
  is_direct_competitor_reason TEXT,
  quality_score INT,
  quality_reason TEXT,
  geographic_focus TEXT,
  partner_since TIMESTAMPTZ,
  notes TEXT,
  raw_data JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(domain)
);

-- Agency contacts (GF / Inhaber)
CREATE TABLE IF NOT EXISTS agency_contact (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id UUID REFERENCES agency(id) ON DELETE CASCADE,
  name TEXT,
  title TEXT,
  linkedin_url TEXT,
  email TEXT,
  confidence TEXT DEFAULT 'medium',
  source TEXT,
  is_primary BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Agency outreach (same pattern as contact outreach)
CREATE TABLE IF NOT EXISTS agency_outreach (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id UUID REFERENCES agency(id) ON DELETE CASCADE,
  agency_contact_id UUID REFERENCES agency_contact(id),
  thread_id UUID,
  in_reply_to UUID REFERENCES agency_outreach(id),
  direction TEXT DEFAULT 'outbound' CHECK (direction IN ('outbound', 'inbound')),
  sequence_step INT DEFAULT 1,
  subject TEXT,
  body TEXT,
  sent_at TIMESTAMPTZ,
  status TEXT DEFAULT 'pending',
  email_opened BOOLEAN DEFAULT false,
  times_opened INT DEFAULT 0,
  got_reply BOOLEAN DEFAULT false,
  reply_sentiment TEXT CHECK (reply_sentiment IN ('positive','negative','neutral','interested','not_interested')),
  raw_reply_text TEXT,
  instantly_lead_id TEXT,
  sender_name TEXT DEFAULT 'Niels',
  sender_email TEXT,
  follow_up_reasoning TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Role ↔ Agency match (for matching engine)
CREATE TABLE IF NOT EXISTS role_agency_match (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id UUID REFERENCES role(id) ON DELETE CASCADE,
  agency_id UUID REFERENCES agency(id) ON DELETE CASCADE,
  status TEXT DEFAULT 'pending',
  anonymized_brief TEXT,
  candidates_received JSONB,
  finder_fee_pct NUMERIC DEFAULT 20,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(role_id, agency_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_agency_outreach_status ON agency(outreach_status);
CREATE INDEX IF NOT EXISTS idx_agency_enrichment_status ON agency(enrichment_status);
CREATE INDEX IF NOT EXISTS idx_agency_outreach_thread ON agency_outreach(thread_id);
CREATE INDEX IF NOT EXISTS idx_role_agency_match_role ON role_agency_match(role_id);
