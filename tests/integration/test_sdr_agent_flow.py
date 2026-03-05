"""Integration tests for pipeline/sdr_agent.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX
from tests.fixtures.contacts import DM_CEO
from tests.fixtures.supabase_responses import (
    OPPORTUNITY_ROLE,
    OUTREACH_SENT,
    INBOUND_REPLY_INTERESTED,
    AGENT_CONFIG_DICT,
)
from tests.fixtures.claude_responses import (
    OUTREACH_EMAIL,
    SENTIMENT_INTERESTED,
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
)

import pipeline.sdr_agent as sdr_agent


# ─── helpers ──────────────────────────────────────────────────────────────────

def _config(overrides=None):
    """Return agent config dict with optional overrides."""
    cfg = dict(AGENT_CONFIG_DICT)
    if overrides:
        cfg.update(overrides)
    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
# run_cold_outreach
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_cold_outreach_drafts_email(mocker, monkeypatch):
    """Cold outreach in draft mode: generates email, creates outreach record, updates opp stage."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    post_calls = []
    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "POST":
            post_calls.append((table, data))
            return [{"id": "new-id"}]
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        # Today's outreach count
        if table == "outreach" and method == "GET" and params and "direction" in (params or {}):
            if params.get("direction") == "eq.outbound":
                return []  # 0 sent today
        # Ready opportunities
        if table == "opportunity" and method == "GET":
            return [OPPORTUNITY_ROLE]
        # Existing outreach for company
        if table == "outreach" and method == "GET" and params and "company_id" in (params or {}):
            return []
        # Company intel
        if table == "role" and method == "GET":
            return [{"title": "Interim CFO", "tier": "hot", "is_hot": True,
                     "engagement_type": "Interim", "role_function": "Finance", "status": "active"}]
        if table == "signal" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"is_decision_maker": True, "role_at_company": "CEO",
                     "contact": DM_CEO}]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech",
                     "funding_stage": "Series C", "domain": "taxfix.de"}]
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.claude_request", return_value=OUTREACH_EMAIL)
    mocker.patch("pipeline.sdr_agent.get_successful_examples", return_value="")
    mocker.patch("time.sleep")

    result = sdr_agent.run_cold_outreach(_config())

    assert result["drafts_created"] == 1
    # Outreach record created
    outreach_posts = [t for t, d in post_calls if t == "outreach"]
    assert len(outreach_posts) >= 1
    # Opportunity stage updated
    opp_patches = [d for t, d in patch_calls if "opportunity" in t]
    assert any(d.get("stage") == "sdr_contacted" for d in opp_patches)


@pytest.mark.integration
def test_cold_outreach_respects_daily_limit(mocker, monkeypatch):
    """When daily limit is reached, no outreach should be generated."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")

    def mock_supabase(method, table, data=None, params=None):
        if table == "outreach" and method == "GET" and params and params.get("direction") == "eq.outbound":
            return [{"id": f"out-{i}"} for i in range(5)]  # 5 already sent, limit=3
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.get_successful_examples", return_value="")

    result = sdr_agent.run_cold_outreach(_config({"outreach_daily_limit": "3"}))
    assert result["drafts_created"] == 0
    assert result["emails_sent"] == 0


@pytest.mark.integration
def test_cold_outreach_skips_existing_outreach(mocker, monkeypatch):
    """Companies that already have outreach should be skipped."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    def mock_supabase(method, table, data=None, params=None):
        if table == "outreach" and method == "GET" and params and params.get("direction") == "eq.outbound":
            return []  # daily count = 0
        if table == "opportunity" and method == "GET":
            return [OPPORTUNITY_ROLE]
        if table == "outreach" and method == "GET" and params and "company_id" in (params or {}):
            return [{"id": "existing-outreach"}]  # already contacted
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.get_successful_examples", return_value="")

    result = sdr_agent.run_cold_outreach(_config())
    assert result["drafts_created"] == 0


@pytest.mark.integration
def test_cold_outreach_auto_send(mocker, monkeypatch):
    """In auto mode with RESEND_API_KEY, emails should be sent via resend."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "RESEND_API_KEY", "test-resend-key")

    def mock_supabase(method, table, data=None, params=None):
        if method == "POST":
            return [{"id": "new-id"}]
        if method == "PATCH":
            return [{}]
        if table == "outreach" and method == "GET" and params and params.get("direction") == "eq.outbound":
            return []
        if table == "opportunity" and method == "GET":
            return [OPPORTUNITY_ROLE]
        if table == "outreach" and method == "GET":
            return []
        if table == "role" and method == "GET":
            return [{"title": "Interim CFO", "tier": "hot", "is_hot": True,
                     "engagement_type": "Interim", "role_function": "Finance", "status": "active"}]
        if table == "signal" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"is_decision_maker": True, "role_at_company": "CEO",
                     "contact": DM_CEO}]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech",
                     "funding_stage": "C", "domain": "taxfix.de"}]
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.claude_request", return_value=OUTREACH_EMAIL)
    mocker.patch("pipeline.sdr_agent.get_successful_examples", return_value="")
    mocker.patch("pipeline.sdr_agent.send_email", return_value="resend-123")
    mocker.patch("time.sleep")

    result = sdr_agent.run_cold_outreach(_config({"outreach_mode": "auto"}))
    assert result["emails_sent"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# run_reply_handler
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_reply_handler_classifies_sentiment_and_handoff(mocker, monkeypatch):
    """Interested reply -> classify sentiment -> handoff to AE."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        # Inbound replies
        if table == "outreach" and method == "GET" and params and params.get("direction") == "eq.inbound":
            return [INBOUND_REPLY_INTERESTED]
        # Thread
        if table == "outreach" and method == "GET" and params and "thread_id" in (params or {}):
            if params.get("direction") == "eq.outbound":
                return [OUTREACH_SENT]
            return [OUTREACH_SENT, INBOUND_REPLY_INTERESTED]
        # Opportunity for handoff
        if table == "opportunity" and method == "GET":
            return [{"id": "opp-001"}]
        if method == "POST":
            return [{"id": "new-id"}]
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.classify_sentiment", return_value="interested")

    result = sdr_agent.run_reply_handler(_config())

    assert result["replies_processed"] == 1
    assert result["handoffs"] == 1

    # Verify opportunity was moved to qualified + owner=ae
    opp_patches = [d for t, d in patch_calls if "opportunity" in t]
    assert any(d.get("stage") == "qualified" and d.get("owner") == "ae" for d in opp_patches)


@pytest.mark.integration
def test_reply_handler_negative_closes(mocker, monkeypatch):
    """Negative reply -> close opportunity as lost."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if table == "outreach" and method == "GET" and params and params.get("direction") == "eq.inbound":
            return [INBOUND_REPLY_INTERESTED]
        if table == "outreach" and method == "GET" and params and "thread_id" in (params or {}):
            if params.get("direction") == "eq.outbound":
                return [OUTREACH_SENT]
            return [OUTREACH_SENT]
        if table == "opportunity" and method == "GET":
            return [{"id": "opp-001"}]
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.classify_sentiment", return_value="negative")

    result = sdr_agent.run_reply_handler(_config())
    assert result["replies_processed"] == 1

    opp_patches = [d for t, d in patch_calls if "opportunity" in t]
    assert any(d.get("stage") == "closed_lost" for d in opp_patches)


@pytest.mark.integration
def test_reply_handler_neutral_followup(mocker, monkeypatch):
    """Neutral reply -> generate follow-up."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    post_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "POST":
            post_calls.append((table, data))
            return [{"id": "new-id"}]
        if method == "PATCH":
            return [{}]
        if table == "outreach" and method == "GET" and params and params.get("direction") == "eq.inbound":
            return [INBOUND_REPLY_INTERESTED]
        if table == "outreach" and method == "GET" and params and "thread_id" in (params or {}):
            if params.get("direction") == "eq.outbound":
                return [OUTREACH_SENT]
            return [OUTREACH_SENT]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech", "funding_stage": "C"}]
        if table == "contact" and method == "GET":
            return [DM_CEO]
        if table == "opportunity" and method == "GET":
            return [{"id": "opp-001"}]
        return []

    mocker.patch("pipeline.sdr_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.sdr_agent.classify_sentiment", return_value="neutral")

    followup_json = json.dumps({"subject": "Re: A-Line x Taxfix", "body_html": "<p>Follow-up</p>"})
    mocker.patch("pipeline.sdr_agent.claude_request", return_value=followup_json)
    mocker.patch("time.sleep")

    result = sdr_agent.run_reply_handler(_config())
    assert result["replies_processed"] == 1

    # Should have created a follow-up outreach record
    outreach_posts = [d for t, d in post_calls if t == "outreach"]
    assert len(outreach_posts) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# run()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_run_calls_both_handlers(mocker, monkeypatch):
    """run() should call reply handler then cold outreach."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    mock_reply = mocker.patch("pipeline.sdr_agent.run_reply_handler",
                              return_value={"replies_processed": 1, "followups_sent": 0, "handoffs": 0})
    mock_outreach = mocker.patch("pipeline.sdr_agent.run_cold_outreach",
                                 return_value={"drafts_created": 1, "emails_sent": 0})

    config = _config()
    result = sdr_agent.run(config)

    mock_reply.assert_called_once_with(config)
    mock_outreach.assert_called_once_with(config)
    assert result["replies_processed"] == 1
    assert result["drafts_created"] == 1


@pytest.mark.integration
def test_run_outreach_mode_off_skips(mocker, monkeypatch):
    """outreach_mode=off should skip all SDR actions."""
    monkeypatch.setattr(sdr_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(sdr_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(sdr_agent, "ANTHROPIC_KEY", "test-key")

    mock_reply = mocker.patch("pipeline.sdr_agent.run_reply_handler")
    mock_outreach = mocker.patch("pipeline.sdr_agent.run_cold_outreach")

    result = sdr_agent.run(_config({"outreach_mode": "off"}))

    mock_reply.assert_not_called()
    mock_outreach.assert_not_called()
    assert result["drafts_created"] == 0
