"""Sample Supabase query results for tests."""

from tests.fixtures.companies import TAXFIX, PERSONIO, NOVATECH
from tests.fixtures.contacts import DM_CEO, DM_CFO, COMPANY_CONTACT_LINK

ROLE_LIST = [
    {
        "id": "role-001",
        "title": "Interim CFO",
        "company_id": TAXFIX["id"],
        "tier": "hot",
        "is_hot": True,
        "engagement_type": "Interim",
        "role_function": "Finance",
        "role_level": "C-Level",
        "status": "active",
        "source_url": "https://taxfix.jobs/interim-cfo",
        "research_status": "pending",
    },
    {
        "id": "role-002",
        "title": "Head of Finance",
        "company_id": PERSONIO["id"],
        "tier": "warm",
        "is_hot": False,
        "engagement_type": "Full-time",
        "role_function": "Finance",
        "role_level": "Head/Director",
        "status": "active",
        "source_url": "https://personio.jobs/head-of-finance",
        "research_status": "pending",
    },
]

OPPORTUNITY_ROLE = {
    "id": "opp-001",
    "pipeline_type": "role",
    "stage": "ready_for_outreach",
    "company_id": TAXFIX["id"],
    "role_id": "role-001",
    "signal_id": None,
    "owner": "sdr",
    "notes": "Hot role: Interim CFO (Interim) — Finance",
}

OPPORTUNITY_COMPANY = {
    "id": "opp-002",
    "pipeline_type": "company",
    "stage": "ready_for_outreach",
    "company_id": TAXFIX["id"],
    "role_id": None,
    "signal_id": "sig-001",
    "owner": "sdr",
    "notes": "Signal: [funding_round] Taxfix raises $100M Series C",
}

OPPORTUNITY_QUALIFIED = {
    "id": "opp-003",
    "pipeline_type": "role",
    "stage": "qualified",
    "company_id": TAXFIX["id"],
    "role_id": "role-001",
    "signal_id": None,
    "owner": "ae",
    "notes": "Hot role: Interim CFO (Interim) — Finance",
}

OPPORTUNITY_MEETING = {
    "id": "opp-004",
    "pipeline_type": "role",
    "stage": "meeting",
    "company_id": TAXFIX["id"],
    "role_id": "role-001",
    "signal_id": None,
    "owner": "ae",
    "notes": "Hot role: Interim CFO",
    "meeting_scheduled_at": "2026-03-10T10:00:00Z",
}

OUTREACH_SENT = {
    "id": "out-001",
    "company_id": TAXFIX["id"],
    "contact_id": DM_CEO["id"],
    "subject": "A-Line x Taxfix",
    "body_html": "<p>Hi Max...</p>",
    "status": "sent",
    "direction": "outbound",
    "thread_id": "out-001",
    "got_reply": False,
}

INBOUND_REPLY_INTERESTED = {
    "id": "out-002",
    "company_id": TAXFIX["id"],
    "contact_id": DM_CEO["id"],
    "thread_id": "out-001",
    "subject": "Re: A-Line x Taxfix",
    "body_html": "<p>Klingt interessant, lassen Sie uns telefonieren.</p>",
    "raw_text": "Klingt interessant, lassen Sie uns telefonieren.",
    "status": "replied",
    "direction": "inbound",
    "from_email": "max@taxfix.de",
    "reply_sentiment": None,
    "created_at": "2026-03-03T10:00:00Z",
}

AGENT_CONFIG = [
    {"key": "outreach_mode", "value": "draft"},
    {"key": "outreach_daily_limit", "value": "3"},
    {"key": "outreach_from_email", "value": "niels@arteq.app"},
    {"key": "outreach_cc", "value": "niels@arteq.app"},
    {"key": "outreach_persona", "value": '{"dos": ["Be concise"], "donts": ["Be pushy"], "value_props": ["Speed"], "signature": "Beste Gruesse,\\nNiels"}'},
    {"key": "apollo_monthly_credit_budget", "value": "500"},
    {"key": "role_expire_days", "value": "60"},
]

AGENT_CONFIG_DICT = {r["key"]: r["value"] for r in AGENT_CONFIG}
