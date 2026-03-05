"""Integration tests for pipeline/company_pipeline.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX
from tests.fixtures.contacts import DM_CEO
from tests.fixtures.signals import HOT_SIGNAL

import pipeline.company_pipeline as company_pipeline


# ═══════════════════════════════════════════════════════════════════════════════
# create_opportunities
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_creates_opportunity_from_hot_signal(mocker, monkeypatch):
    """Hot signal at enriched company with email contact -> opportunity created."""
    monkeypatch.setattr(company_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_pipeline, "SUPABASE_KEY", "test-key")

    created_records = []
    patched_records = []

    def mock_supabase(method, table, data=None, params=None):
        # Hot signals
        if table == "signal" and method == "GET":
            return [HOT_SIGNAL]
        # Company enrichment check
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        # Existing opportunity check (by signal_id)
        if table == "opportunity" and method == "GET" and params and "signal_id" in (params or {}):
            return []
        # Existing company opp check
        if table == "opportunity" and method == "GET" and params and "company_id" in (params or {}):
            return []
        # Company contact check
        if table == "company_contact" and method == "GET":
            return [{"contact": {"id": DM_CEO["id"], "email": DM_CEO["email"]}}]
        # Create opportunity
        if table == "opportunity" and method == "POST":
            created_records.append(data)
            return [{"id": "opp-new"}]
        # PATCH signal as processed
        if table.startswith("signal") and method == "PATCH":
            patched_records.append(data)
            return [{}]
        # Agent log
        if table == "agent_log" and method == "POST":
            return [{"id": "log-1"}]
        return []

    mocker.patch("pipeline.company_pipeline.supabase_request", side_effect=mock_supabase)

    company_pipeline.create_opportunities()

    assert len(created_records) == 1
    assert created_records[0]["pipeline_type"] == "company"
    assert created_records[0]["stage"] == "ready_for_outreach"
    assert created_records[0]["signal_id"] == HOT_SIGNAL["id"]


@pytest.mark.integration
def test_skips_unenriched_companies(mocker, monkeypatch):
    """Signals at unenriched companies should be skipped."""
    monkeypatch.setattr(company_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_pipeline, "SUPABASE_KEY", "test-key")

    created = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "signal" and method == "GET":
            return [HOT_SIGNAL]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "pending"}]
        if table == "opportunity" and method == "POST":
            created.append(data)
            return [{"id": "opp-x"}]
        return []

    mocker.patch("pipeline.company_pipeline.supabase_request", side_effect=mock_supabase)
    company_pipeline.create_opportunities()
    assert len(created) == 0


@pytest.mark.integration
def test_skips_existing_opportunity_by_signal_id(mocker, monkeypatch):
    """Signals that already have an opportunity should be skipped and marked processed."""
    monkeypatch.setattr(company_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_pipeline, "SUPABASE_KEY", "test-key")

    created = []
    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "signal" and method == "GET":
            return [HOT_SIGNAL]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        if table == "opportunity" and method == "GET" and params and "signal_id" in (params or {}):
            return [{"id": "existing-opp"}]
        if table.startswith("signal") and method == "PATCH":
            patch_calls.append(data)
            return [{}]
        if table == "opportunity" and method == "POST":
            created.append(data)
            return [{"id": "opp-x"}]
        return []

    mocker.patch("pipeline.company_pipeline.supabase_request", side_effect=mock_supabase)
    company_pipeline.create_opportunities()
    assert len(created) == 0
    # Signal should be marked processed
    assert any(d.get("processed") is True for d in patch_calls)


@pytest.mark.integration
def test_skips_company_with_active_opportunity(mocker, monkeypatch):
    """Companies that already have an active company pipeline opp should be skipped."""
    monkeypatch.setattr(company_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_pipeline, "SUPABASE_KEY", "test-key")

    created = []
    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "signal" and method == "GET":
            return [HOT_SIGNAL]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        if table == "opportunity" and method == "GET" and params and "signal_id" in (params or {}):
            return []
        if table == "opportunity" and method == "GET" and params and "company_id" in (params or {}):
            return [{"id": "active-opp"}]  # active company opp
        if table.startswith("signal") and method == "PATCH":
            patch_calls.append(data)
            return [{}]
        if table == "opportunity" and method == "POST":
            created.append(data)
            return [{"id": "opp-x"}]
        return []

    mocker.patch("pipeline.company_pipeline.supabase_request", side_effect=mock_supabase)
    company_pipeline.create_opportunities()
    assert len(created) == 0


@pytest.mark.integration
def test_marks_signals_as_processed(mocker, monkeypatch):
    """After creating an opportunity, the signal should be marked processed."""
    monkeypatch.setattr(company_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_pipeline, "SUPABASE_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "signal" and method == "GET":
            return [HOT_SIGNAL]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        if table == "opportunity" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"contact": {"id": "c1", "email": "test@x.com"}}]
        if table == "opportunity" and method == "POST":
            return [{"id": "opp-new"}]
        if method == "PATCH" and "signal" in table:
            patch_calls.append(data)
            return [{}]
        if table == "agent_log" and method == "POST":
            return [{"id": "log-1"}]
        return []

    mocker.patch("pipeline.company_pipeline.supabase_request", side_effect=mock_supabase)
    company_pipeline.create_opportunities()

    assert any(d.get("processed") is True for d in patch_calls)


@pytest.mark.integration
def test_empty_signals_no_action(mocker, monkeypatch):
    """No hot signals means nothing happens."""
    monkeypatch.setattr(company_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_pipeline, "SUPABASE_KEY", "test-key")

    mocker.patch("pipeline.company_pipeline.supabase_request", return_value=[])
    company_pipeline.create_opportunities()
