"""Integration tests for enrichment/company_enricher.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX, NOVATECH
from tests.fixtures.apollo_responses import ORG_ENRICHMENT, PEOPLE_SEARCH_DM
from tests.fixtures.claude_responses import COMPANY_SYNTHESIS

import enrichment.company_enricher as company_enricher


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_http_response(json_data=None, text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text or json.dumps(json_data or {})
    resp.headers = {}
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# enrich_via_apollo_org
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_enrich_via_apollo_org_returns_org_data(mocker, monkeypatch):
    """Apollo org enrichment should return organization data when API returns 200."""
    monkeypatch.setattr(company_enricher, "APOLLO_API_KEY", "test-key")

    mocker.patch(
        "enrichment.company_enricher.requests.post",
        return_value=_make_http_response(ORG_ENRICHMENT),
    )

    result = company_enricher.enrich_via_apollo_org("taxfix.de")
    assert result is not None
    assert result["estimated_num_employees"] == 200
    assert result["industry"] == "Financial Technology"


@pytest.mark.integration
def test_enrich_via_apollo_org_returns_none_on_failure(mocker, monkeypatch):
    """Apollo org enrichment returns None on non-200 status."""
    monkeypatch.setattr(company_enricher, "APOLLO_API_KEY", "test-key")

    mocker.patch(
        "enrichment.company_enricher.requests.post",
        return_value=_make_http_response(status_code=404),
    )

    result = company_enricher.enrich_via_apollo_org("unknown.com")
    assert result is None


@pytest.mark.integration
def test_enrich_via_apollo_org_no_api_key(monkeypatch):
    """No APOLLO_API_KEY means skip and return None."""
    monkeypatch.setattr(company_enricher, "APOLLO_API_KEY", "")
    result = company_enricher.enrich_via_apollo_org("taxfix.de")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_tech_stack
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_analyze_tech_stack_detects_modern_tech(mocker, monkeypatch):
    """HTML with React + Next.js signals should produce high_fit detection."""
    html_body = '<html><head><script src="/_next/static/chunks/main.js"></script></head><body></body></html>'

    mock_resp = MagicMock()
    mock_resp.text = html_body
    mock_resp.headers = {"server": "cloudflare"}
    mock_resp.status_code = 200

    mocker.patch(
        "enrichment.company_enricher.requests.get",
        return_value=mock_resp,
    )

    result = company_enricher.analyze_tech_stack("taxfix.de")
    assert result is not None
    assert "Next.js" in result["technologies"]


@pytest.mark.integration
def test_analyze_tech_stack_no_domain(monkeypatch):
    """No domain should return None."""
    result = company_enricher.analyze_tech_stack(None)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# enrich_company (full flow)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_enrich_company_full_flow(mocker, monkeypatch):
    """Full enrichment: Apollo org + people + tech + Claude synthesis + DB writes."""
    monkeypatch.setattr(company_enricher, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_enricher, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(company_enricher, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(company_enricher, "APOLLO_API_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if method == "POST":
            return [{"id": "new-item"}]
        if method == "GET":
            if table == "apollo_credit_ledger":
                return []  # no credits used
            if table == "agent_config":
                return [{"value": "500"}]
            if table == "role":
                return []
            if table == "signal":
                return []
            if table == "company_contact":
                return []
            if table == "contact":
                return []
        return []

    mocker.patch("enrichment.company_enricher.supabase_request", side_effect=mock_supabase)

    # Apollo org
    mocker.patch("enrichment.company_enricher.enrich_via_apollo_org",
                 return_value=ORG_ENRICHMENT["organization"])
    # Apollo people search
    mocker.patch("enrichment.company_enricher.search_apollo_people",
                 return_value=PEOPLE_SEARCH_DM["people"][:1])
    # Tech stack
    mocker.patch("enrichment.company_enricher.analyze_tech_stack",
                 return_value={"technologies": ["React", "Next.js"], "tech_fit": "high"})
    # Claude synthesis
    mocker.patch("enrichment.company_enricher.claude_request",
                 return_value=COMPANY_SYNTHESIS)
    mocker.patch("time.sleep")

    company = {
        "id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de",
        "industry": "FinTech", "status": "lead",
    }
    result = company_enricher.enrich_company(company)
    assert result is True

    # Check that company was marked enriching then complete
    enrichment_patches = [
        d for t, d in patch_calls
        if "enrichment_status" in (d or {})
    ]
    statuses = [d["enrichment_status"] for d in enrichment_patches]
    assert "enriching" in statuses
    assert "complete" in statuses


# ═══════════════════════════════════════════════════════════════════════════════
# run()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_run_processes_pending_companies(mocker, monkeypatch):
    """run() should fetch pending companies and enrich each."""
    monkeypatch.setattr(company_enricher, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_enricher, "SUPABASE_KEY", "test-key")

    companies = [
        {"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de",
         "industry": "FinTech", "funding_stage": "Series C", "headcount": "200",
         "status": "lead", "hq_city": "Berlin", "funding_amount": "$100M"},
    ]

    budget_counter = [100]

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if table == "company" and params and params.get("enrichment_status") == "eq.pending":
            return companies
        if table == "apollo_credit_ledger" and method == "GET":
            return []
        if table == "agent_config":
            return [{"value": "500"}]
        return []

    mocker.patch("enrichment.company_enricher.supabase_request", side_effect=mock_supabase)
    mock_enrich = mocker.patch("enrichment.company_enricher.enrich_company", return_value=True)
    mocker.patch("time.sleep")

    company_enricher.run()
    mock_enrich.assert_called_once()


@pytest.mark.integration
def test_run_stops_on_low_budget(mocker, monkeypatch):
    """run() should stop enriching when Apollo budget is too low."""
    monkeypatch.setattr(company_enricher, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(company_enricher, "SUPABASE_KEY", "test-key")

    companies = [
        {"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de",
         "industry": "FinTech", "funding_stage": "C", "headcount": "200",
         "status": "lead", "hq_city": "Berlin", "funding_amount": "$100M"},
        {"id": NOVATECH["id"], "name": "NovaTech", "domain": "novatech.ch",
         "industry": "DeepTech", "funding_stage": "A", "headcount": "45",
         "status": "lead", "hq_city": "Zurich", "funding_amount": "$12M"},
    ]

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if table == "company" and params and params.get("enrichment_status") == "eq.pending":
            return companies
        if table == "apollo_credit_ledger" and method == "GET":
            # Simulate nearly exhausted budget: 498 used of 500
            return [{"credits": 498}]
        if table == "agent_config":
            return [{"value": "500"}]
        return []

    mocker.patch("enrichment.company_enricher.supabase_request", side_effect=mock_supabase)
    mock_enrich = mocker.patch("enrichment.company_enricher.enrich_company", return_value=True)
    mocker.patch("time.sleep")

    company_enricher.run()
    # Budget is 500 - 498 = 2, which is < 5, so no companies should be enriched
    mock_enrich.assert_not_called()
