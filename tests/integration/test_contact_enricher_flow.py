"""Integration tests for enrichment/contact_enricher.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX
from tests.fixtures.contacts import DM_CEO, CONTACT_NO_EMAIL
from tests.fixtures.apollo_responses import PEOPLE_MATCH, PEOPLE_MATCH_NO_RESULT
from tests.fixtures.claude_responses import DM_SCORING

import enrichment.contact_enricher as contact_enricher


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_http_response(json_data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = json.dumps(json_data or {})
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# enrich_via_apollo_match
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_enrich_via_apollo_match_returns_contact_data(mocker, monkeypatch):
    """Apollo People Match should return email, phone, career history."""
    monkeypatch.setattr(contact_enricher, "APOLLO_API_KEY", "test-key")

    mocker.patch(
        "enrichment.contact_enricher.requests.post",
        return_value=_make_http_response(PEOPLE_MATCH),
    )

    contact = {"name": "Max Mustermann", "apollo_id": "apollo-001"}
    result = contact_enricher.enrich_via_apollo_match(contact, "taxfix.de")

    assert result is not None
    assert result["email"] == "max@taxfix.de"
    assert result["email_status"] == "verified"
    assert len(result["career_history"]) == 2
    assert result["career_history"][0]["company"] == "Taxfix"


@pytest.mark.integration
def test_enrich_via_apollo_match_no_result(mocker, monkeypatch):
    """Apollo returns no person data -> None."""
    monkeypatch.setattr(contact_enricher, "APOLLO_API_KEY", "test-key")

    mocker.patch(
        "enrichment.contact_enricher.requests.post",
        return_value=_make_http_response(PEOPLE_MATCH_NO_RESULT),
    )

    contact = {"name": "Nobody", "linkedin_url": "https://linkedin.com/in/nobody"}
    result = contact_enricher.enrich_via_apollo_match(contact, "unknown.com")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# search_thought_leadership
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_search_thought_leadership_finds_results(mocker, monkeypatch):
    """DDG search finds podcast/conference mentions for a person."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Max at FinTech Podcast", "body": "Interview with Max about finance podcast trends",
         "href": "https://podcast.example.com/max"},
        {"title": "Max keynote at TechConf", "body": "Max delivered a keynote at conference on scaling",
         "href": "https://techconf.com/max"},
    ]
    mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

    mocker.patch("enrichment.contact_enricher.DDGS", return_value=mock_ddgs_instance)

    result = contact_enricher.search_thought_leadership("Max Mustermann", "Taxfix")
    assert result is not None
    assert len(result) == 2
    assert result[0]["type"] == "thought_leadership"


@pytest.mark.integration
def test_search_thought_leadership_no_results(mocker, monkeypatch):
    """DDG search finds nothing relevant -> returns None."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Unrelated article", "body": "Nothing about anyone important", "href": "https://x.com"},
    ]
    mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

    mocker.patch("enrichment.contact_enricher.DDGS", return_value=mock_ddgs_instance)

    result = contact_enricher.search_thought_leadership("Nobody", "Unknown")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# enrich_contact (full flow)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_enrich_contact_full_flow(mocker, monkeypatch):
    """Full contact enrichment: Apollo match + DDG + Claude DM scoring + DB write."""
    monkeypatch.setattr(contact_enricher, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(contact_enricher, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(contact_enricher, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(contact_enricher, "APOLLO_API_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if method == "POST":
            return [{"id": "new-item"}]
        if method == "GET":
            if table == "apollo_credit_ledger":
                return []
            if table == "agent_config":
                return [{"value": "500"}]
        return []

    mocker.patch("enrichment.contact_enricher.supabase_request", side_effect=mock_supabase)

    # Apollo match
    mocker.patch("enrichment.contact_enricher.enrich_via_apollo_match", return_value={
        "email": "max@taxfix.de", "email_status": "verified",
        "phone": "+49123456789", "linkedin_url": "https://linkedin.com/in/max",
        "title": "CEO", "career_history": [{"company": "Taxfix", "title": "CEO",
                                             "start_date": "2016", "end_date": None, "current": True}],
    })

    # Thought leadership
    mocker.patch("enrichment.contact_enricher.search_thought_leadership", return_value=[
        {"title": "Podcast", "url": "https://pod.com", "snippet": "Test", "type": "thought_leadership"},
    ])

    # DM scoring
    mocker.patch("enrichment.contact_enricher.score_decision_maker",
                 return_value=(90, ["Hook1", "Hook2"]))

    mocker.patch("time.sleep")

    contact = {"id": "contact-001", "name": "Max Mustermann", "title": "CEO",
               "email": None, "phone": None, "linkedin_url": None}
    company = {"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de",
               "industry": "FinTech", "headcount": "200"}

    result = contact_enricher.enrich_contact(contact, company)
    assert result is True

    # Verify contact was PATCHed with enrichment_status=complete
    contact_patches = [d for t, d in patch_calls if "enrichment_status" in (d or {})]
    assert len(contact_patches) >= 1
    assert contact_patches[0]["enrichment_status"] == "complete"


# ═══════════════════════════════════════════════════════════════════════════════
# run()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_run_processes_pending_contacts(mocker, monkeypatch):
    """run() should fetch enriched companies + pending contacts, then enrich each."""
    monkeypatch.setattr(contact_enricher, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(contact_enricher, "SUPABASE_KEY", "test-key")

    companies = [
        {"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de",
         "industry": "FinTech", "headcount": "200"},
    ]
    links = [
        {
            "company_id": TAXFIX["id"],
            "contact": {
                "id": "contact-001", "name": "Max Mustermann",
                "title": "CEO", "email": None, "phone": None,
                "linkedin_url": None, "enrichment_status": "pending",
                "apollo_id": "apollo-001",
            },
        },
    ]

    def mock_supabase(method, table, data=None, params=None):
        if table == "company" and method == "GET":
            return companies
        if table == "company_contact" and method == "GET":
            return links
        if table == "apollo_credit_ledger" and method == "GET":
            return []
        if table == "agent_config":
            return [{"value": "500"}]
        return []

    mocker.patch("enrichment.contact_enricher.supabase_request", side_effect=mock_supabase)
    mock_enrich = mocker.patch("enrichment.contact_enricher.enrich_contact", return_value=True)
    mocker.patch("time.sleep")

    contact_enricher.run()
    mock_enrich.assert_called_once()
