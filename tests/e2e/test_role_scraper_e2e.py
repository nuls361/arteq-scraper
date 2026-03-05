"""
E2E tests for role_scraper — full main() flow with HTTP-level mocking.

Mocks JSearch, Arbeitnow, Supabase REST, and Claude API at HTTP transport
level using the `responses` library. Tests the complete scrape-dedup-classify-write
pipeline.
"""

import json

import pytest
import responses
from responses import matchers

from tests.fixtures.claude_responses import CLASSIFY_ROLES_HOT_WARM, CLASSIFY_ROLES_ALL_DISQUALIFIED
from tests.fixtures.companies import TAXFIX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPABASE_BASE = "https://test.supabase.co"


def _jsearch_response(jobs):
    """Build a JSearch API response body."""
    return {"status": "OK", "data": jobs}


def _arbeitnow_response(jobs, has_next=False):
    """Build an Arbeitnow API response body."""
    links = {"next": "https://www.arbeitnow.com/api/job-board-api?page=2"} if has_next else {}
    return {"data": jobs, "links": links}


def _claude_response(text):
    """Build a Claude Messages API response body."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "claude-haiku-4-5-20251001",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


JSEARCH_JOB_DACH = {
    "employer_name": "TestCorp",
    "job_title": "Interim CFO",
    "job_city": "Berlin",
    "job_state": "Berlin",
    "job_country": "DE",
    "job_is_remote": False,
    "job_posted_at_datetime_utc": "2026-03-01T08:00:00.000Z",
    "job_description": "Seeking an experienced Interim CFO for our Berlin office.",
    "job_apply_link": "https://testcorp.de/interim-cfo",
    "job_google_link": "https://google.com/job/999",
}

ARBEITNOW_JOB = {
    "slug": "head-of-finance-startup-xyz",
    "company_name": "StartupXYZ",
    "title": "Head of Finance",
    "location": "Munich, Germany",
    "remote": False,
    "description": "<p>We need a <b>Head of Finance</b> (CFO track).</p>",
    "tags": ["finance", "cfo"],
    "url": "https://www.arbeitnow.com/view/head-of-finance-startup-xyz",
    "created_at": "1709200000",
}


def _register_supabase_dedup_empty(rsps):
    """Register Supabase GET /role for dedup returning no existing roles."""
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[],
        status=200,
    )


def _register_supabase_company_upsert(rsps, company_id=None):
    """Register Supabase GET + POST for company upsert."""
    cid = company_id or TAXFIX["id"]
    # GET company (not found)
    rsps.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[],
        status=200,
    )
    # POST company (create)
    rsps.add(
        responses.POST,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[{"id": cid, "name": "TestCorp"}],
        status=201,
    )


def _register_supabase_write_role(rsps):
    """Register Supabase POST /role for writing a classified role."""
    rsps.add(
        responses.POST,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"id": "role-new-001"}],
        status=201,
    )


def _register_supabase_patch_company(rsps):
    """Register Supabase PATCH /company for hot role enrichment trigger."""
    rsps.add(
        responses.PATCH,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[{"id": TAXFIX["id"]}],
        status=200,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@responses.activate
def test_full_role_scraper_run(monkeypatch):
    """Full run: JSearch + Arbeitnow return jobs, Claude classifies, roles written."""
    import scrapers.role_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(mod, "JSEARCH_API_KEY", "test-key")
    # Remove sleeps for faster tests
    monkeypatch.setattr("time.sleep", lambda _: None)

    # -- JSearch: return 1 DACH job for every query (same job, dedup will collapse)
    for _ in mod.JSEARCH_QUERIES:
        responses.add(
            responses.GET,
            "https://jsearch.p.rapidapi.com/search",
            json=_jsearch_response([JSEARCH_JOB_DACH]),
            status=200,
        )

    # -- Arbeitnow: landing page hit, then API page 1 with 1 job, page 2 empty
    responses.add(responses.GET, "https://www.arbeitnow.com/", body="OK", status=200)
    responses.add(
        responses.GET,
        "https://www.arbeitnow.com/api/job-board-api",
        json=_arbeitnow_response([ARBEITNOW_JOB], has_next=False),
        status=200,
    )

    # -- Supabase dedup: no existing roles
    _register_supabase_dedup_empty(responses)

    # -- Claude classification: 1 hot + 1 warm
    responses.add(
        responses.POST,
        "https://api.anthropic.com/v1/messages",
        json=_claude_response(CLASSIFY_ROLES_HOT_WARM),
        status=200,
    )

    # -- Supabase writes: company upsert + role write + enrichment patch
    # Two classified roles (hot + warm) means 2 company lookups, possible creates, role writes
    for _ in range(2):
        _register_supabase_company_upsert(responses)
        _register_supabase_write_role(responses)
    _register_supabase_patch_company(responses)

    # Run
    mod.main()

    # Verify key HTTP calls were made
    jsearch_calls = [c for c in responses.calls if "jsearch.p.rapidapi.com" in c.request.url]
    assert len(jsearch_calls) >= 1, "At least one JSearch call expected"

    arbeitnow_calls = [c for c in responses.calls if "arbeitnow.com/api" in c.request.url]
    assert len(arbeitnow_calls) >= 1, "At least one Arbeitnow API call expected"

    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) >= 1, "Claude classification call expected"

    supabase_posts = [
        c for c in responses.calls
        if "test.supabase.co" in c.request.url and c.request.method == "POST"
    ]
    assert len(supabase_posts) >= 1, "At least one Supabase POST (role or company) expected"


@pytest.mark.e2e
@responses.activate
def test_no_api_keys_graceful_exit(monkeypatch):
    """Graceful exit when SUPABASE_URL is empty — just logs and returns."""
    import scrapers.role_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", "")
    monkeypatch.setattr(mod, "SUPABASE_KEY", "")

    # Should return early without making any HTTP calls
    mod.main()

    assert len(responses.calls) == 0, "No HTTP calls should be made when keys are missing"


@pytest.mark.e2e
@responses.activate
def test_claude_timeout_continues(monkeypatch):
    """Claude timeout (ConnectionError) should log error and continue."""
    import scrapers.role_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(mod, "JSEARCH_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _: None)

    # JSearch returns 1 job
    for _ in mod.JSEARCH_QUERIES:
        responses.add(
            responses.GET,
            "https://jsearch.p.rapidapi.com/search",
            json=_jsearch_response([JSEARCH_JOB_DACH]),
            status=200,
        )

    # Arbeitnow: landing page + empty
    responses.add(responses.GET, "https://www.arbeitnow.com/", body="OK", status=200)
    responses.add(
        responses.GET,
        "https://www.arbeitnow.com/api/job-board-api",
        json=_arbeitnow_response([], has_next=False),
        status=200,
    )

    # Supabase dedup: no existing roles
    _register_supabase_dedup_empty(responses)

    # Claude: ConnectionError (simulating timeout)
    responses.add(
        responses.POST,
        "https://api.anthropic.com/v1/messages",
        body=ConnectionError("Connection timed out"),
    )

    # main() should not raise
    mod.main()

    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) >= 1, "Claude was called (and failed)"

    # No Supabase role writes since classification failed
    role_posts = [
        c for c in responses.calls
        if "test.supabase.co/rest/v1/role" in c.request.url and c.request.method == "POST"
    ]
    assert len(role_posts) == 0, "No roles should be written when Claude fails"


@pytest.mark.e2e
@responses.activate
def test_all_duplicates_no_classification(monkeypatch):
    """All source_urls already in DB means no classification needed."""
    import scrapers.role_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(mod, "JSEARCH_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _: None)

    # JSearch returns 1 job
    for _ in mod.JSEARCH_QUERIES:
        responses.add(
            responses.GET,
            "https://jsearch.p.rapidapi.com/search",
            json=_jsearch_response([JSEARCH_JOB_DACH]),
            status=200,
        )

    # Arbeitnow: landing page + empty response
    responses.add(responses.GET, "https://www.arbeitnow.com/", body="OK", status=200)
    responses.add(
        responses.GET,
        "https://www.arbeitnow.com/api/job-board-api",
        json=_arbeitnow_response([], has_next=False),
        status=200,
    )

    # Supabase dedup: the job URL already exists
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"source_url": JSEARCH_JOB_DACH["job_apply_link"]}],
        status=200,
    )

    # main() should not call Claude (all duplicates)
    mod.main()

    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) == 0, "Claude should not be called when all jobs are duplicates"
