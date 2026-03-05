"""
E2E tests for orchestrator — full main() flow with mocked step functions.

The orchestrator imports modules lazily inside try/except blocks, so we mock
the imported step functions rather than individual HTTP calls. Supabase REST
calls made directly by the orchestrator (get_config, run_data_hygiene,
send_daily_brief, log_decision) are mocked at HTTP level via `responses`.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import responses

from tests.fixtures.companies import TAXFIX
from tests.fixtures.supabase_responses import AGENT_CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPABASE_BASE = "https://test.supabase.co"


def _register_config(rsps):
    """Register Supabase GET agent_config."""
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/agent_config",
        json=AGENT_CONFIG,
        status=200,
    )


def _register_data_hygiene(rsps):
    """Register Supabase calls for run_data_hygiene (stale roles query + patches)."""
    # GET stale roles — none
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[],
        status=200,
    )


def _register_daily_brief_stats(rsps):
    """Register all Supabase GET calls in send_daily_brief."""
    # Hot roles
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"id": "role-001"}],
        status=200,
    )
    # Pending companies
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[],
        status=200,
    )
    # Active opportunities
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/opportunity",
        json=[],
        status=200,
    )
    # Candidate matches
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role_candidate_match",
        json=[],
        status=200,
    )


def _register_log_decision(rsps):
    """Register Supabase POST agent_log."""
    rsps.add(
        responses.POST,
        f"{SUPABASE_BASE}/rest/v1/agent_log",
        json=[{"id": "log-001"}],
        status=201,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@responses.activate
def test_full_orchestrator_run(monkeypatch, mocker):
    """Full run: all steps succeed, daily brief sent."""
    import orchestrator as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(mod, "RESEND_API_KEY", "test-resend-key")
    monkeypatch.setattr(mod, "ALERT_EMAIL", "test@example.com")

    # Supabase: config + data hygiene + daily brief stats + log
    _register_config(responses)
    _register_data_hygiene(responses)
    _register_daily_brief_stats(responses)
    _register_log_decision(responses)

    # Mock all step imports (lazy imports inside try/except)
    mock_healthcheck = mocker.patch(
        "orchestrator.run_healthcheck",
        create=True,
    )
    # The orchestrator imports like: from healthcheck import run_healthcheck
    # We need to mock at the source so the import finds our mock
    mock_hc_module = MagicMock()
    mock_hc_module.run_healthcheck.return_value = ([], True)
    mocker.patch.dict("sys.modules", {"healthcheck": mock_hc_module})

    mock_ce_module = MagicMock()
    mock_ce_module.run = MagicMock()
    mocker.patch.dict("sys.modules", {
        "healthcheck": mock_hc_module,
        "enrichment": MagicMock(),
        "enrichment.company_enricher": mock_ce_module,
    })

    mock_contact_module = MagicMock()
    mock_contact_module.run = MagicMock()
    mocker.patch.dict("sys.modules", {
        "healthcheck": mock_hc_module,
        "enrichment": MagicMock(),
        "enrichment.company_enricher": mock_ce_module,
        "enrichment.contact_enricher": mock_contact_module,
    })

    mock_role_pipeline = MagicMock()
    mock_role_pipeline.create_opportunities = MagicMock()

    mock_research = MagicMock()
    mock_research.run = MagicMock(return_value={"roles_researched": 2, "matches_found": 5})

    mock_company_pipeline = MagicMock()
    mock_company_pipeline.create_opportunities = MagicMock()

    mock_sdr = MagicMock()
    mock_sdr.run = MagicMock(return_value={"emails_sent": 1, "drafts_created": 2, "handoffs": 0})

    mock_ae = MagicMock()
    mock_ae.run = MagicMock(return_value={"responses_sent": 1, "briefings_created": 1, "proposals_created": 0})

    mocker.patch.dict("sys.modules", {
        "healthcheck": mock_hc_module,
        "enrichment": MagicMock(),
        "enrichment.company_enricher": mock_ce_module,
        "enrichment.contact_enricher": mock_contact_module,
        "pipeline": MagicMock(),
        "pipeline.role_pipeline": mock_role_pipeline,
        "pipeline.research_agent": mock_research,
        "pipeline.company_pipeline": mock_company_pipeline,
        "pipeline.sdr_agent": mock_sdr,
        "pipeline.ae_agent": mock_ae,
    })

    # Mock resend for daily brief
    mock_resend = MagicMock()
    mock_resend.api_key = None
    mock_resend.Emails = MagicMock()
    mock_resend.Emails.send = MagicMock()
    mocker.patch.dict("sys.modules", {
        "healthcheck": mock_hc_module,
        "enrichment": MagicMock(),
        "enrichment.company_enricher": mock_ce_module,
        "enrichment.contact_enricher": mock_contact_module,
        "pipeline": MagicMock(),
        "pipeline.role_pipeline": mock_role_pipeline,
        "pipeline.research_agent": mock_research,
        "pipeline.company_pipeline": mock_company_pipeline,
        "pipeline.sdr_agent": mock_sdr,
        "pipeline.ae_agent": mock_ae,
        "resend": mock_resend,
    })

    mod.main()

    # Verify key steps were invoked
    mock_hc_module.run_healthcheck.assert_called_once()
    mock_ce_module.run.assert_called_once()
    mock_contact_module.run.assert_called_once()
    mock_role_pipeline.create_opportunities.assert_called_once()
    mock_research.run.assert_called_once()
    mock_company_pipeline.create_opportunities.assert_called_once()
    mock_sdr.run.assert_called_once()
    mock_ae.run.assert_called_once()

    # Verify daily brief email was sent via resend
    mock_resend.Emails.send.assert_called_once()
    send_args = mock_resend.Emails.send.call_args[0][0]
    assert "A-Line Daily Brief" in send_args["subject"]


@pytest.mark.e2e
@responses.activate
def test_missing_supabase_returns_early(monkeypatch):
    """Returns early when SUPABASE_URL is empty."""
    import orchestrator as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", "")
    monkeypatch.setattr(mod, "SUPABASE_KEY", "")

    mod.main()

    assert len(responses.calls) == 0, "No HTTP calls when Supabase config is missing"


@pytest.mark.e2e
@responses.activate
def test_partial_failures_daily_brief_still_sent(monkeypatch, mocker):
    """Some steps raise exceptions, others succeed; daily brief still sent."""
    import orchestrator as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(mod, "RESEND_API_KEY", "test-resend-key")
    monkeypatch.setattr(mod, "ALERT_EMAIL", "test@example.com")

    _register_config(responses)
    _register_data_hygiene(responses)
    _register_daily_brief_stats(responses)
    _register_log_decision(responses)

    # Healthcheck: raises
    mock_hc_module = MagicMock()
    mock_hc_module.run_healthcheck.side_effect = RuntimeError("Healthcheck DB down")

    # Company enricher: succeeds
    mock_ce_module = MagicMock()
    mock_ce_module.run = MagicMock()

    # Contact enricher: raises
    mock_contact_module = MagicMock()
    mock_contact_module.run.side_effect = RuntimeError("Apollo API error")

    # Role pipeline: succeeds
    mock_role_pipeline = MagicMock()
    mock_role_pipeline.create_opportunities = MagicMock()

    # Research agent: raises
    mock_research = MagicMock()
    mock_research.run.side_effect = RuntimeError("Research agent timeout")

    # Company pipeline: succeeds
    mock_company_pipeline = MagicMock()
    mock_company_pipeline.create_opportunities = MagicMock()

    # SDR: raises
    mock_sdr = MagicMock()
    mock_sdr.run.side_effect = RuntimeError("SDR config error")

    # AE: raises
    mock_ae = MagicMock()
    mock_ae.run.side_effect = RuntimeError("AE agent error")

    # Resend: succeeds
    mock_resend = MagicMock()
    mock_resend.Emails = MagicMock()
    mock_resend.Emails.send = MagicMock()

    mocker.patch.dict("sys.modules", {
        "healthcheck": mock_hc_module,
        "enrichment": MagicMock(),
        "enrichment.company_enricher": mock_ce_module,
        "enrichment.contact_enricher": mock_contact_module,
        "pipeline": MagicMock(),
        "pipeline.role_pipeline": mock_role_pipeline,
        "pipeline.research_agent": mock_research,
        "pipeline.company_pipeline": mock_company_pipeline,
        "pipeline.sdr_agent": mock_sdr,
        "pipeline.ae_agent": mock_ae,
        "resend": mock_resend,
    })

    # Should not raise despite partial failures
    mod.main()

    # Steps that should succeed still ran
    mock_ce_module.run.assert_called_once()
    mock_role_pipeline.create_opportunities.assert_called_once()
    mock_company_pipeline.create_opportunities.assert_called_once()

    # Daily brief still sent
    mock_resend.Emails.send.assert_called_once()


@pytest.mark.e2e
@responses.activate
def test_daily_brief_sent_with_stats(monkeypatch, mocker):
    """Verify the daily brief email includes pipeline stats."""
    import orchestrator as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(mod, "RESEND_API_KEY", "test-resend-key")
    monkeypatch.setattr(mod, "ALERT_EMAIL", "niels@test.com")

    _register_config(responses)
    _register_data_hygiene(responses)
    _register_log_decision(responses)

    # Daily brief stats: specific counts
    # Hot roles
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"id": "r1"}, {"id": "r2"}, {"id": "r3"}],
        status=200,
    )
    # Pending companies
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[{"id": "c1"}],
        status=200,
    )
    # Active opportunities
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/opportunity",
        json=[
            {"id": "opp-1", "pipeline_type": "role", "stage": "ready_for_outreach"},
            {"id": "opp-2", "pipeline_type": "company", "stage": "sdr_contacted"},
        ],
        status=200,
    )
    # Candidate matches
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role_candidate_match",
        json=[{"id": "m1"}, {"id": "m2"}],
        status=200,
    )

    # Mock all step modules (all succeed quickly)
    mock_hc = MagicMock()
    mock_hc.run_healthcheck.return_value = ([], True)

    mock_ce = MagicMock()
    mock_ct = MagicMock()
    mock_rp = MagicMock()
    mock_rp.create_opportunities = MagicMock()
    mock_ra = MagicMock()
    mock_ra.run.return_value = {"roles_researched": 0, "matches_found": 0}
    mock_cp = MagicMock()
    mock_cp.create_opportunities = MagicMock()
    mock_sdr = MagicMock()
    mock_sdr.run.return_value = {"emails_sent": 0, "drafts_created": 0, "handoffs": 0}
    mock_ae = MagicMock()
    mock_ae.run.return_value = {"responses_sent": 0, "briefings_created": 0, "proposals_created": 0}

    mock_resend = MagicMock()
    mock_resend.Emails = MagicMock()
    mock_resend.Emails.send = MagicMock()

    mocker.patch.dict("sys.modules", {
        "healthcheck": mock_hc,
        "enrichment": MagicMock(),
        "enrichment.company_enricher": mock_ce,
        "enrichment.contact_enricher": mock_ct,
        "pipeline": MagicMock(),
        "pipeline.role_pipeline": mock_rp,
        "pipeline.research_agent": mock_ra,
        "pipeline.company_pipeline": mock_cp,
        "pipeline.sdr_agent": mock_sdr,
        "pipeline.ae_agent": mock_ae,
        "resend": mock_resend,
    })

    mod.main()

    # Verify resend was called with correct recipient
    mock_resend.Emails.send.assert_called_once()
    send_payload = mock_resend.Emails.send.call_args[0][0]
    assert "niels@test.com" in send_payload["to"]
    assert "A-Line Daily Brief" in send_payload["subject"]
    assert "html" in send_payload
