"""Integration tests for scrapers/role_scraper.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.roles import HOT_ROLE, WARM_ROLE, PARK_ROLE, SCRAPED_JOBS
from tests.fixtures.companies import TAXFIX, PERSONIO
from tests.fixtures.claude_responses import (
    CLASSIFY_ROLES_HOT_WARM,
    CLASSIFY_ROLES_ALL_DISQUALIFIED,
    CLASSIFY_ROLES_PARK,
    CLASSIFY_ROLES_AGENCY_CAPPED,
)

import scrapers.role_scraper as role_scraper


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_claude_response(text, status_code=200):
    """Build a mock requests.Response for Claude API."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "content": [{"type": "text", "text": text}],
    }
    resp.text = text
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# classify_roles
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_classify_roles_happy_path(mocker, monkeypatch):
    """Two roles: 1 hot (score>=70), 1 warm (40-69) — both pass."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    mock_post = mocker.patch(
        "scrapers.role_scraper.requests.post",
        return_value=_make_claude_response(CLASSIFY_ROLES_HOT_WARM),
    )
    mocker.patch("time.sleep")

    jobs = [
        {"company": "Taxfix", "title": "Interim CFO", "location": "Berlin, Germany",
         "description": "Interim CFO needed", "source": "jsearch", "url": "https://a.com"},
        {"company": "Personio", "title": "Head of Finance", "location": "Munich, Germany",
         "description": "Head of Finance role", "source": "arbeitnow", "url": "https://b.com"},
    ]

    result = role_scraper.classify_roles(jobs)

    assert len(result) == 2
    assert result[0]["is_hot"] is True
    assert result[0]["tier"] == "hot"
    assert result[0]["qualification_score"] == 82
    assert "engagement_type_pts" in result[0]["score_breakdown"]
    assert result[1]["is_hot"] is False
    assert result[1]["tier"] == "warm"
    assert result[1]["qualification_score"] == 45
    mock_post.assert_called_once()


@pytest.mark.integration
def test_classify_roles_all_disqualified_returns_empty(mocker, monkeypatch):
    """When Claude disqualifies everything (score=0), nothing comes back."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch(
        "scrapers.role_scraper.requests.post",
        return_value=_make_claude_response(CLASSIFY_ROLES_ALL_DISQUALIFIED),
    )
    mocker.patch("time.sleep")

    jobs = [
        {"company": "A", "title": "Intern", "location": "Berlin", "description": "", "source": "x", "url": "u1"},
        {"company": "B", "title": "Test", "location": "NYC", "description": "", "source": "x", "url": "u2"},
    ]

    result = role_scraper.classify_roles(jobs)
    assert result == []


@pytest.mark.integration
def test_classify_roles_json_parse_error_logs_and_continues(mocker, monkeypatch, caplog):
    """A JSON parse error should be logged but not crash the pipeline."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch(
        "scrapers.role_scraper.requests.post",
        return_value=_make_claude_response("NOT VALID JSON {{{"),
    )
    mocker.patch("time.sleep")

    jobs = [
        {"company": "X", "title": "CFO", "location": "Berlin", "description": "", "source": "y", "url": "u3"},
    ]

    result = role_scraper.classify_roles(jobs)
    assert result == []
    assert any("JSON parse error" in r.message for r in caplog.records)


@pytest.mark.integration
def test_classify_roles_batch_processing(mocker, monkeypatch):
    """More than 3 jobs should produce multiple Claude API calls (batches of 3)."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    batch_response = json.dumps({
        "roles": [
            {"index": i, "score": 50, "is_disqualified": False,
             "score_breakdown": {"engagement_type_pts": 25, "role_type_pts": 10,
                                 "structural_pts": 8, "company_stage_pts": 10,
                                 "deductions_bonuses": -3, "agency_capped": False},
             "reason": "ok", "engagement_type": "Full-time",
             "role_function": "Finance", "role_level": "Other"}
            for i in range(1, 4)
        ]
    })

    mock_post = mocker.patch(
        "scrapers.role_scraper.requests.post",
        return_value=_make_claude_response(batch_response),
    )
    mocker.patch("time.sleep")

    jobs = [
        {"company": f"Co{i}", "title": f"Role{i}", "location": "Berlin, DE",
         "description": "", "source": "jsearch", "url": f"https://example.com/{i}"}
        for i in range(7)
    ]

    role_scraper.classify_roles(jobs)
    # 7 jobs → ceil(7/3) = 3 batches
    assert mock_post.call_count == 3


@pytest.mark.integration
def test_classify_roles_empty_input(monkeypatch):
    """Empty job list returns empty immediately."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")
    assert role_scraper.classify_roles([]) == []


@pytest.mark.integration
def test_classify_roles_park_tier(mocker, monkeypatch):
    """A role scoring 5-39 should get tier='park'."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch(
        "scrapers.role_scraper.requests.post",
        return_value=_make_claude_response(CLASSIFY_ROLES_PARK),
    )
    mocker.patch("time.sleep")

    jobs = [
        {"company": "MidCorp", "title": "VP Finance", "location": "Frankfurt, Germany",
         "description": "VP Finance role", "source": "arbeitnow", "url": "https://c.com"},
    ]

    result = role_scraper.classify_roles(jobs)
    assert len(result) == 1
    assert result[0]["tier"] == "park"
    assert result[0]["is_hot"] is False
    assert result[0]["qualification_score"] == 25


@pytest.mark.integration
def test_classify_roles_agency_capped(mocker, monkeypatch):
    """Agency-capped role (score=8) should get tier='park'."""
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch(
        "scrapers.role_scraper.requests.post",
        return_value=_make_claude_response(CLASSIFY_ROLES_AGENCY_CAPPED),
    )
    mocker.patch("time.sleep")

    jobs = [
        {"company": "Hays Recruiting", "title": "Interim CFO", "location": "Berlin",
         "description": "Agency posting", "source": "jsearch", "url": "https://d.com"},
    ]

    result = role_scraper.classify_roles(jobs)
    assert len(result) == 1
    assert result[0]["tier"] == "park"
    assert result[0]["qualification_score"] == 8
    assert result[0]["score_breakdown"]["agency_capped"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# dedup_jobs
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_dedup_jobs_new_jobs_pass(mocker, monkeypatch):
    """All new URLs should pass through dedup."""
    monkeypatch.setattr(role_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_scraper, "SUPABASE_KEY", "test-key")

    mocker.patch(
        "scrapers.role_scraper.supabase_request",
        return_value=[],  # no existing URLs
    )

    result = role_scraper.dedup_jobs(SCRAPED_JOBS)
    assert len(result) == len(SCRAPED_JOBS)


@pytest.mark.integration
def test_dedup_jobs_existing_urls_filtered(mocker, monkeypatch):
    """Jobs whose URLs already exist in DB should be filtered out."""
    monkeypatch.setattr(role_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_scraper, "SUPABASE_KEY", "test-key")

    mocker.patch(
        "scrapers.role_scraper.supabase_request",
        return_value=[{"source_url": "https://taxfix.jobs/interim-cfo"}],
    )

    result = role_scraper.dedup_jobs(SCRAPED_JOBS)
    urls = [j["url"] for j in result]
    assert "https://taxfix.jobs/interim-cfo" not in urls


# ═══════════════════════════════════════════════════════════════════════════════
# write_roles
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_write_roles_creates_company_and_role(mocker, monkeypatch):
    """write_roles should upsert company then write role record."""
    monkeypatch.setattr(role_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_scraper, "SUPABASE_KEY", "test-key")

    call_log = []

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        call_log.append((method, table, data, params))
        if method == "GET" and table == "company":
            return []  # company not found -> will create
        if method == "POST" and table == "company":
            return [{"id": "new-company-id"}]
        if method == "POST" and table == "role":
            return [{"id": "new-role-id"}]
        if method == "PATCH":
            return [{}]
        return []

    mocker.patch("scrapers.role_scraper.supabase_request", side_effect=mock_supabase)

    job = {
        "company": "Taxfix",
        "title": "Interim CFO",
        "description": "Test",
        "location": "Berlin",
        "is_remote": False,
        "url": "https://example.com/1",
        "posted": "2026-03-01",
        "source": "jsearch",
        "is_hot": True,
        "tier": "hot",
        "classification_reason": "Interim in title",
        "engagement_type": "Interim",
        "role_function": "Finance",
        "role_level": "C-Level",
        "qualification_score": 82,
        "score_breakdown": {"engagement_type_pts": 55, "role_type_pts": 20,
                            "structural_pts": 12, "company_stage_pts": 10,
                            "deductions_bonuses": -15, "agency_capped": False},
    }

    written = role_scraper.write_roles([job])
    assert written == 1

    # Verify company GET (lookup), company POST (create), role POST, PATCH for enrichment
    tables_called = [t for _, t, _, _ in call_log]
    assert "company" in tables_called
    assert "role" in tables_called


@pytest.mark.integration
def test_write_roles_hot_triggers_enrichment_patch(mocker, monkeypatch):
    """A hot role should trigger enrichment_status=pending PATCH on the company."""
    monkeypatch.setattr(role_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_scraper, "SUPABASE_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if method == "GET" and table == "company":
            return [{"id": "cmp-123"}]
        if method == "POST" and table == "role":
            return [{"id": "role-new"}]
        return []

    mocker.patch("scrapers.role_scraper.supabase_request", side_effect=mock_supabase)

    job = {
        "company": "TestCo", "title": "Interim CTO", "description": "",
        "location": "Berlin", "is_remote": False, "url": "https://x.com/1",
        "posted": "2026-03-01", "source": "jsearch", "is_hot": True,
        "tier": "hot", "classification_reason": "", "engagement_type": "Interim",
        "role_function": "Engineering", "role_level": "C-Level",
        "qualification_score": 75, "score_breakdown": {},
    }

    role_scraper.write_roles([job])

    assert len(patch_calls) == 1
    assert patch_calls[0][1]["enrichment_status"] == "pending"


# ═══════════════════════════════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_main_happy_path(mocker, monkeypatch):
    """main() wires scrape_jsearch + scrape_arbeitnow + dedup + classify + write."""
    monkeypatch.setattr(role_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(role_scraper, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(role_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch("scrapers.role_scraper.scrape_jsearch", return_value=SCRAPED_JOBS[:1])
    mocker.patch("scrapers.role_scraper.scrape_arbeitnow", return_value=SCRAPED_JOBS[1:2])
    mocker.patch("scrapers.role_scraper.dedup_jobs", return_value=SCRAPED_JOBS[:2])

    classified = [
        {**SCRAPED_JOBS[0], "is_hot": True, "tier": "hot",
         "classification_reason": "Interim", "engagement_type": "Interim",
         "role_function": "Finance", "role_level": "C-Level",
         "qualification_score": 82, "score_breakdown": {}},
    ]
    mocker.patch("scrapers.role_scraper.classify_roles", return_value=classified)
    mocker.patch("scrapers.role_scraper.write_roles", return_value=1)

    # Should not raise
    role_scraper.main()


@pytest.mark.integration
def test_main_no_env_vars_exits_early(mocker, monkeypatch):
    """main() exits early if SUPABASE_URL missing."""
    monkeypatch.setattr(role_scraper, "SUPABASE_URL", "")
    monkeypatch.setattr(role_scraper, "SUPABASE_KEY", "")

    mock_scrape = mocker.patch("scrapers.role_scraper.scrape_jsearch")

    role_scraper.main()
    mock_scrape.assert_not_called()
