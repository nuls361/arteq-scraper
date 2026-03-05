"""Integration tests for pipeline/ae_agent.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX
from tests.fixtures.contacts import DM_CEO
from tests.fixtures.supabase_responses import (
    OPPORTUNITY_QUALIFIED,
    OPPORTUNITY_MEETING,
    INBOUND_REPLY_INTERESTED,
    AGENT_CONFIG_DICT,
)
from tests.fixtures.claude_responses import (
    OUTREACH_EMAIL,
    MEETING_BRIEFING,
    PROPOSAL_DRAFT,
)

import pipeline.ae_agent as ae_agent


# ─── helpers ──────────────────────────────────────────────────────────────────

def _config(overrides=None):
    cfg = dict(AGENT_CONFIG_DICT)
    if overrides:
        cfg.update(overrides)
    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
# handle_new_qualifieds
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_handle_new_qualifieds_responds(mocker, monkeypatch):
    """AE responds to a qualified lead, creating outreach + updating opp to meeting."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    post_calls = []
    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "POST":
            post_calls.append((table, data))
            return [{"id": "new-id"}]
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if table == "opportunity" and method == "GET":
            return [OPPORTUNITY_QUALIFIED]
        if table == "outreach" and method == "GET" and params and params.get("status") == "eq.handoff_ae":
            return [INBOUND_REPLY_INTERESTED]
        if table == "outreach" and method == "GET" and params and "thread_id" in (params or {}):
            return [{"direction": "outbound", "subject": "A-Line x Taxfix",
                     "body_html": "<p>Hi Max...</p>", "raw_text": "Hi Max...",
                     "created_at": "2026-03-01"}]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech",
                     "funding_stage": "C", "domain": "taxfix.de"}]
        if table == "contact" and method == "GET":
            return [DM_CEO]
        if table == "role" and method == "GET":
            return []
        if table == "signal" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"is_decision_maker": True, "role_at_company": "CEO",
                     "contact": DM_CEO}]
        return []

    mocker.patch("pipeline.ae_agent.supabase_request", side_effect=mock_supabase)

    ae_response = json.dumps({"subject": "Re: A-Line x Taxfix",
                               "body_html": "<p>Hi Max, let's schedule a call.</p>"})
    mocker.patch("pipeline.ae_agent.claude_request", return_value=ae_response)
    mocker.patch("time.sleep")

    result = ae_agent.handle_new_qualifieds(_config())

    # Outreach record created
    outreach_posts = [d for t, d in post_calls if t == "outreach"]
    assert len(outreach_posts) >= 1

    # Opportunity moved to "meeting"
    opp_patches = [d for t, d in patch_calls if "opportunity" in t]
    assert any(d.get("stage") == "meeting" for d in opp_patches)


@pytest.mark.integration
def test_handle_new_qualifieds_no_opportunities(mocker, monkeypatch):
    """No qualified opportunities -> do nothing."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    mocker.patch("pipeline.ae_agent.supabase_request", return_value=[])

    result = ae_agent.handle_new_qualifieds(_config())
    assert result["responses_sent"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# generate_meeting_preps
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_generate_meeting_preps_creates_briefing(mocker, monkeypatch):
    """Creates a meeting briefing for opportunities in meeting stage."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    post_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "POST":
            post_calls.append((table, data))
            return [{"id": "new-id"}]
        if table == "opportunity" and method == "GET":
            return [OPPORTUNITY_MEETING]
        if table == "meeting_prep" and method == "GET":
            return []  # no existing prep
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech",
                     "funding_stage": "C", "domain": "taxfix.de"}]
        if table == "role" and method == "GET":
            return []
        if table == "signal" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"is_decision_maker": True, "contact": DM_CEO}]
        if table == "outreach" and method == "GET":
            return []
        return []

    mocker.patch("pipeline.ae_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.ae_agent.claude_request", return_value=MEETING_BRIEFING)

    result = ae_agent.generate_meeting_preps(_config())
    assert result["briefings_created"] == 1

    prep_posts = [d for t, d in post_calls if t == "meeting_prep"]
    assert len(prep_posts) == 1


@pytest.mark.integration
def test_generate_meeting_preps_skips_existing(mocker, monkeypatch):
    """Should not create duplicate meeting prep."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    def mock_supabase(method, table, data=None, params=None):
        if table == "opportunity" and method == "GET":
            return [OPPORTUNITY_MEETING]
        if table == "meeting_prep" and method == "GET":
            return [{"id": "existing-prep"}]  # already exists
        return []

    mocker.patch("pipeline.ae_agent.supabase_request", side_effect=mock_supabase)

    result = ae_agent.generate_meeting_preps(_config())
    assert result["briefings_created"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# generate_proposals
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_generate_proposals_creates_proposal(mocker, monkeypatch):
    """Creates a proposal draft for opportunities in proposal stage."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    post_calls = []

    proposal_opp = dict(OPPORTUNITY_QUALIFIED)
    proposal_opp["stage"] = "proposal"

    def mock_supabase(method, table, data=None, params=None):
        if method == "POST":
            post_calls.append((table, data))
            return [{"id": "new-id"}]
        if method == "PATCH":
            return [{}]
        if table == "opportunity" and method == "GET":
            return [proposal_opp]
        if table == "proposal_draft" and method == "GET":
            return []  # no existing
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech",
                     "funding_stage": "C", "domain": "taxfix.de"}]
        if table == "role" and method == "GET":
            return [{"title": "Interim CFO", "engagement_type": "Interim",
                     "tier": "hot", "is_hot": True, "role_function": "Finance", "status": "active"}]
        if table == "signal" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"is_decision_maker": True, "contact": DM_CEO}]
        return []

    mocker.patch("pipeline.ae_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.ae_agent.claude_request", return_value=PROPOSAL_DRAFT)

    result = ae_agent.generate_proposals(_config())
    assert result["proposals_created"] == 1

    proposal_posts = [d for t, d in post_calls if t == "proposal_draft"]
    assert len(proposal_posts) == 1


@pytest.mark.integration
def test_generate_proposals_skips_existing(mocker, monkeypatch):
    """Should not create duplicate proposals."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    proposal_opp = dict(OPPORTUNITY_QUALIFIED)
    proposal_opp["stage"] = "proposal"

    def mock_supabase(method, table, data=None, params=None):
        if table == "opportunity" and method == "GET":
            return [proposal_opp]
        if table == "proposal_draft" and method == "GET":
            return [{"id": "existing-proposal"}]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "industry": "FinTech",
                     "funding_stage": "C", "domain": "taxfix.de"}]
        if table == "role" and method == "GET":
            return []
        if table == "signal" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return []
        return []

    mocker.patch("pipeline.ae_agent.supabase_request", side_effect=mock_supabase)

    result = ae_agent.generate_proposals(_config())
    assert result["proposals_created"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# run()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_run_calls_all_three(mocker, monkeypatch):
    """run() should call handle_new_qualifieds, meeting preps, and proposals."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    mock_q = mocker.patch("pipeline.ae_agent.handle_new_qualifieds",
                          return_value={"responses_sent": 1})
    mock_m = mocker.patch("pipeline.ae_agent.generate_meeting_preps",
                          return_value={"briefings_created": 1})
    mock_p = mocker.patch("pipeline.ae_agent.generate_proposals",
                          return_value={"proposals_created": 1})

    config = _config()
    result = ae_agent.run(config)

    mock_q.assert_called_once_with(config)
    mock_m.assert_called_once_with(config)
    mock_p.assert_called_once_with(config)
    assert result["responses_sent"] == 1
    assert result["briefings_created"] == 1
    assert result["proposals_created"] == 1


@pytest.mark.integration
def test_run_outreach_mode_off_skips(mocker, monkeypatch):
    """outreach_mode=off should skip all AE actions."""
    monkeypatch.setattr(ae_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(ae_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(ae_agent, "ANTHROPIC_KEY", "test-key")

    mock_q = mocker.patch("pipeline.ae_agent.handle_new_qualifieds")

    result = ae_agent.run(_config({"outreach_mode": "off"}))

    mock_q.assert_not_called()
    assert result["responses_sent"] == 0
