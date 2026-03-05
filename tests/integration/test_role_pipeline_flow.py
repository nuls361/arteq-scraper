"""Integration tests for pipeline/role_pipeline.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX, NOVATECH
from tests.fixtures.contacts import DM_CEO, CONTACT_NO_EMAIL
from tests.fixtures.supabase_responses import ROLE_LIST

import pipeline.role_pipeline as role_pipeline


# ═══════════════════════════════════════════════════════════════════════════════
# create_opportunities
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_creates_opportunity_for_hot_role_at_enriched_company(mocker, monkeypatch):
    """Hot role at enriched company with email contact -> opportunity created."""
    monkeypatch.setattr(role_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_pipeline, "SUPABASE_KEY", "test-key")

    created_records = []

    def mock_supabase(method, table, data=None, params=None):
        # Hot roles query
        if table == "role" and method == "GET":
            return [ROLE_LIST[0]]  # hot role
        # Company enrichment check
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        # Opportunity existence check
        if table == "opportunity" and method == "GET":
            return []  # no existing
        # Contact with email check
        if table == "company_contact" and method == "GET":
            return [{"contact": {"id": DM_CEO["id"], "email": DM_CEO["email"],
                                 "enrichment_status": "complete"}}]
        # Create opportunity
        if table == "opportunity" and method == "POST":
            created_records.append(data)
            return [{"id": "opp-new"}]
        # Agent log
        if table == "agent_log" and method == "POST":
            return [{"id": "log-1"}]
        return []

    mocker.patch("pipeline.role_pipeline.supabase_request", side_effect=mock_supabase)

    role_pipeline.create_opportunities()

    assert len(created_records) == 1
    assert created_records[0]["pipeline_type"] == "role"
    assert created_records[0]["stage"] == "ready_for_outreach"
    assert created_records[0]["company_id"] == TAXFIX["id"]


@pytest.mark.integration
def test_skips_unenriched_companies(mocker, monkeypatch):
    """Companies with enrichment_status != complete should be skipped."""
    monkeypatch.setattr(role_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_pipeline, "SUPABASE_KEY", "test-key")

    created = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "role" and method == "GET":
            return [{"id": "r1", "title": "Interim CFO", "company_id": NOVATECH["id"],
                     "engagement_type": "Interim", "role_function": "Finance", "role_level": "C-Level"}]
        if table == "company" and method == "GET":
            return [{"id": NOVATECH["id"], "name": "NovaTech", "enrichment_status": "pending"}]
        if table == "opportunity" and method == "POST":
            created.append(data)
            return [{"id": "opp-x"}]
        return []

    mocker.patch("pipeline.role_pipeline.supabase_request", side_effect=mock_supabase)
    role_pipeline.create_opportunities()
    assert len(created) == 0


@pytest.mark.integration
def test_skips_existing_opportunities(mocker, monkeypatch):
    """Roles that already have an opportunity should be skipped."""
    monkeypatch.setattr(role_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_pipeline, "SUPABASE_KEY", "test-key")

    created = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "role" and method == "GET":
            return [ROLE_LIST[0]]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        if table == "opportunity" and method == "GET":
            return [{"id": "existing-opp"}]  # already exists
        if table == "opportunity" and method == "POST":
            created.append(data)
            return [{"id": "opp-x"}]
        return []

    mocker.patch("pipeline.role_pipeline.supabase_request", side_effect=mock_supabase)
    role_pipeline.create_opportunities()
    assert len(created) == 0


@pytest.mark.integration
def test_skips_companies_without_email_contacts(mocker, monkeypatch):
    """Companies with no email contacts should be skipped."""
    monkeypatch.setattr(role_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_pipeline, "SUPABASE_KEY", "test-key")

    created = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "role" and method == "GET":
            return [ROLE_LIST[0]]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        if table == "opportunity" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"contact": {"id": "c1", "email": None, "enrichment_status": "pending"}}]
        if table == "opportunity" and method == "POST":
            created.append(data)
            return [{"id": "opp-x"}]
        return []

    mocker.patch("pipeline.role_pipeline.supabase_request", side_effect=mock_supabase)
    role_pipeline.create_opportunities()
    assert len(created) == 0


@pytest.mark.integration
def test_empty_hot_roles_no_action(mocker, monkeypatch):
    """No hot roles means nothing happens."""
    monkeypatch.setattr(role_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_pipeline, "SUPABASE_KEY", "test-key")

    mocker.patch("pipeline.role_pipeline.supabase_request", return_value=[])
    # Should not raise
    role_pipeline.create_opportunities()


@pytest.mark.integration
def test_logs_to_agent_log_on_creation(mocker, monkeypatch):
    """Opportunity creation should produce an agent_log entry."""
    monkeypatch.setattr(role_pipeline, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_pipeline, "SUPABASE_KEY", "test-key")

    log_entries = []

    def mock_supabase(method, table, data=None, params=None):
        if table == "role" and method == "GET":
            return [ROLE_LIST[0]]
        if table == "company" and method == "GET":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "enrichment_status": "complete"}]
        if table == "opportunity" and method == "GET":
            return []
        if table == "company_contact" and method == "GET":
            return [{"contact": {"id": "c1", "email": "test@test.com", "enrichment_status": "complete"}}]
        if table == "opportunity" and method == "POST":
            return [{"id": "opp-new"}]
        if table == "agent_log" and method == "POST":
            log_entries.append(data)
            return [{"id": "log-1"}]
        return []

    mocker.patch("pipeline.role_pipeline.supabase_request", side_effect=mock_supabase)
    role_pipeline.create_opportunities()

    assert len(log_entries) == 1
    assert log_entries[0]["action"] == "opportunity_created"
    assert log_entries[0]["entity_type"] == "opportunity"
