"""Integration tests for pipeline/research_agent.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX
from tests.fixtures.contacts import CANDIDATE_INTERIM_CFO, CANDIDATE_FRACTIONAL_CTO
from tests.fixtures.supabase_responses import ROLE_LIST
from tests.fixtures.claude_responses import ROLE_REQUIREMENTS, CANDIDATE_SCORING

import pipeline.research_agent as research_agent


# ═══════════════════════════════════════════════════════════════════════════════
# load_hot_roles
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_load_hot_roles_returns_pending(mocker, monkeypatch):
    """load_hot_roles should return roles with tier=hot, research_status=pending."""
    monkeypatch.setattr(research_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(research_agent, "SUPABASE_KEY", "test-key")

    role = {
        "id": "role-001",
        "title": "Interim CFO",
        "description": "Looking for an Interim CFO",
        "location": "Berlin, Germany",
        "engagement_type": "Interim",
        "company_id": TAXFIX["id"],
    }

    mocker.patch("pipeline.research_agent.supabase_request", return_value=[role])

    result = research_agent.load_hot_roles()
    assert len(result) == 1
    assert result[0]["title"] == "Interim CFO"


@pytest.mark.integration
def test_load_hot_roles_empty(mocker, monkeypatch):
    """No pending hot roles -> empty list."""
    monkeypatch.setattr(research_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(research_agent, "SUPABASE_KEY", "test-key")

    mocker.patch("pipeline.research_agent.supabase_request", return_value=[])

    result = research_agent.load_hot_roles()
    assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# extract_role_requirements
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_extract_role_requirements_from_claude(mocker, monkeypatch):
    """Claude extracts structured requirements from role."""
    monkeypatch.setattr(research_agent, "ANTHROPIC_KEY", "test-key")

    mocker.patch("pipeline.research_agent.claude_request", return_value=ROLE_REQUIREMENTS)

    role = {"title": "Interim CFO", "description": "Experienced CFO for Series C FinTech",
            "location": "Berlin, Germany", "engagement_type": "Interim"}

    result = research_agent.extract_role_requirements(role)
    assert result["required_function"] == "cfo"
    assert "fundraising" in result["required_skills"]
    assert result["engagement_type"] == "Interim"


@pytest.mark.integration
def test_extract_role_requirements_fallback_on_error(mocker, monkeypatch):
    """When Claude fails, fallback requirements should be returned."""
    monkeypatch.setattr(research_agent, "ANTHROPIC_KEY", "test-key")

    mocker.patch("pipeline.research_agent.claude_request", return_value=None)

    role = {"title": "Interim CFO", "description": "", "location": "Berlin", "engagement_type": "Interim"}

    result = research_agent.extract_role_requirements(role)
    assert result["required_function"] == "cfo"  # inferred from title
    assert result["engagement_type"] == "Interim"
    assert result["seniority"] == "C-Level"


# ═══════════════════════════════════════════════════════════════════════════════
# search_candidates_db
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_search_candidates_db_returns_matches(mocker, monkeypatch):
    """DB search should return candidates matching function + location."""
    monkeypatch.setattr(research_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(research_agent, "SUPABASE_KEY", "test-key")

    mocker.patch("pipeline.research_agent.supabase_request",
                 return_value=[CANDIDATE_INTERIM_CFO])

    requirements = {
        "required_function": "cfo",
        "location_requirement": "Germany",
    }

    result = research_agent.search_candidates_db(requirements)
    assert len(result) == 1
    assert result[0]["function"] == "cfo"


@pytest.mark.integration
def test_search_candidates_db_retries_without_location(mocker, monkeypatch):
    """If location filter yields nothing, retry without it."""
    monkeypatch.setattr(research_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(research_agent, "SUPABASE_KEY", "test-key")

    call_count = [0]

    def mock_supabase(method, table, data=None, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return []  # first call with location filter -> empty
        return [CANDIDATE_INTERIM_CFO]  # second call without filter

    mocker.patch("pipeline.research_agent.supabase_request", side_effect=mock_supabase)

    requirements = {
        "required_function": "cfo",
        "location_requirement": "Germany",
    }

    result = research_agent.search_candidates_db(requirements)
    assert len(result) == 1
    assert call_count[0] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# run() — full flow
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_run_full_flow(mocker, monkeypatch):
    """Full research flow: load roles, extract requirements, search DB, score, save."""
    monkeypatch.setattr(research_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(research_agent, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(research_agent, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(research_agent, "PDL_API_KEY", "")
    monkeypatch.setattr(research_agent, "APOLLO_API_KEY", "")

    role = {
        "id": "role-001", "title": "Interim CFO",
        "description": "Experienced CFO for Series C FinTech",
        "location": "Berlin", "engagement_type": "Interim",
        "company_id": TAXFIX["id"],
    }

    requirements = json.loads(ROLE_REQUIREMENTS)
    scored = json.loads(CANDIDATE_SCORING)

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if method == "POST":
            return [{"id": "new-id"}]
        return []

    mocker.patch("pipeline.research_agent.supabase_request", side_effect=mock_supabase)
    mocker.patch("pipeline.research_agent.load_hot_roles", return_value=[role])
    mocker.patch("pipeline.research_agent.load_existing_candidates", return_value=(set(), set()))
    mocker.patch("pipeline.research_agent.search_candidates_db", return_value=[CANDIDATE_INTERIM_CFO])
    mocker.patch("pipeline.research_agent.extract_role_requirements", return_value=requirements)
    mocker.patch("pipeline.research_agent.score_candidates_for_role", return_value=scored)
    mocker.patch("pipeline.research_agent.save_matches", return_value=1)
    mocker.patch("time.sleep")

    result = research_agent.run()
    assert result["roles_researched"] == 1
    assert result["matches_found"] == 1

    # Role should be marked as complete
    role_patches = [d for t, d in patch_calls if "role" in t and d and d.get("research_status")]
    assert any(d["research_status"] == "complete" for d in role_patches)


@pytest.mark.integration
def test_run_no_roles(mocker, monkeypatch):
    """No hot roles -> early return."""
    monkeypatch.setattr(research_agent, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(research_agent, "SUPABASE_KEY", "test-key")

    mocker.patch("pipeline.research_agent.load_hot_roles", return_value=[])

    result = research_agent.run()
    assert result["roles_researched"] == 0
    assert result["matches_found"] == 0
