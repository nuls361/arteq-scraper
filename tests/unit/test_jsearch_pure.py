"""
Unit tests for scrapers/jsearch.py — normalize_job function.
"""

import pytest
from scrapers.jsearch import normalize_job


@pytest.mark.unit
def test_normalize_job_full():
    """Full job with all fields present."""
    raw = {
        "employer_name": "Taxfix",
        "employer_logo": "https://logo.png",
        "employer_company_type": "Startup",
        "job_title": "Interim CFO",
        "job_description": "We need an Interim CFO for our Berlin office.",
        "job_city": "Berlin",
        "job_state": "Berlin",
        "job_country": "DE",
        "job_is_remote": False,
        "job_posted_at_datetime_utc": "2026-03-01T12:00:00.000Z",
        "job_apply_link": "https://apply.example.com",
        "job_google_link": "https://google.com/jobs",
        "job_employment_type": "CONTRACT",
        "job_required_experience": {"required_experience_in_months": 60},
        "job_highlights": {},
    }
    result = normalize_job(raw)

    assert result["company_name"] == "Taxfix"
    assert result["role_title"] == "Interim CFO"
    assert result["location"] == "Berlin, Berlin, DE"
    assert result["is_remote"] is False
    assert result["posted_date"] == "2026-03-01"
    assert result["source"] == "JSearch"
    assert result["source_url"] == "https://apply.example.com"
    assert result["employment_type"] == "CONTRACT"
    assert len(result["description"]) <= 2000


@pytest.mark.unit
def test_normalize_job_remote_no_location():
    """Remote job with no city/state/country produces 'Remote' location."""
    raw = {
        "employer_name": "RemoteCo",
        "job_title": "CTO",
        "job_description": "Remote CTO role",
        "job_city": "",
        "job_state": "",
        "job_country": "",
        "job_is_remote": True,
        "job_posted_at_datetime_utc": "2026-02-15T00:00:00.000Z",
        "job_apply_link": "",
        "job_google_link": "https://google.com/jobs",
    }
    result = normalize_job(raw)

    assert result["location"] == "Remote"
    assert result["is_remote"] is True


@pytest.mark.unit
def test_normalize_job_remote_with_location():
    """Remote job with location appends (Remote)."""
    raw = {
        "employer_name": "RemoteCo",
        "job_title": "CTO",
        "job_description": "desc",
        "job_city": "Berlin",
        "job_state": "",
        "job_country": "DE",
        "job_is_remote": True,
        "job_posted_at_datetime_utc": "",
        "job_apply_link": "",
        "job_google_link": "",
    }
    result = normalize_job(raw)

    assert result["location"] == "Berlin, DE (Remote)"


@pytest.mark.unit
def test_normalize_job_missing_fields():
    """Missing fields get reasonable defaults."""
    raw = {}
    result = normalize_job(raw)

    assert result["company_name"] == "Unknown"
    assert result["role_title"] == ""
    assert result["source"] == "JSearch"
    assert result["description"] == ""


@pytest.mark.unit
def test_normalize_job_date_parsing_iso():
    """ISO date is parsed correctly."""
    raw = {
        "employer_name": "X",
        "job_title": "Y",
        "job_description": "d",
        "job_posted_at_datetime_utc": "2025-12-25T08:30:00.000Z",
    }
    result = normalize_job(raw)
    assert result["posted_date"] == "2025-12-25"


@pytest.mark.unit
def test_normalize_job_long_description_truncated():
    """Description longer than 2000 chars is truncated."""
    raw = {
        "employer_name": "X",
        "job_title": "Y",
        "job_description": "a" * 5000,
    }
    result = normalize_job(raw)
    assert len(result["description"]) == 2000


@pytest.mark.unit
def test_normalize_job_fallback_to_google_link():
    """If job_apply_link is empty, use job_google_link."""
    raw = {
        "employer_name": "X",
        "job_title": "Y",
        "job_description": "",
        "job_apply_link": "",
        "job_google_link": "https://google.com/jobs/123",
    }
    result = normalize_job(raw)
    assert result["source_url"] == "https://google.com/jobs/123"


@pytest.mark.unit
def test_normalize_job_source_is_always_jsearch():
    raw = {"employer_name": "X", "job_title": "Y", "job_description": ""}
    result = normalize_job(raw)
    assert result["source"] == "JSearch"
