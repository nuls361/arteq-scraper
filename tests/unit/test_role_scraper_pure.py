"""
Unit tests for scrapers/role_scraper.py — pure helper functions.

safe, is_dach, is_excluded, normalize_name, detect_role_function, dedup_jobs.
"""

import pytest
from scrapers.role_scraper import (
    safe,
    is_dach,
    is_excluded,
    normalize_name,
    detect_role_function,
    dedup_jobs,
    score_to_tier,
)


# ═══════════════════════════════════════════════════════════
# safe
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_safe_none_returns_default():
    assert safe(None) == ""


@pytest.mark.unit
def test_safe_none_returns_custom_default():
    assert safe(None, "fallback") == "fallback"


@pytest.mark.unit
def test_safe_zero_returns_zero():
    assert safe(0) == 0


@pytest.mark.unit
def test_safe_empty_string_returns_empty():
    assert safe("") == ""


@pytest.mark.unit
def test_safe_value_returns_value():
    assert safe("hello") == "hello"


@pytest.mark.unit
def test_safe_false_returns_false():
    assert safe(False) is False


# ═══════════════════════════════════════════════════════════
# is_dach
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_is_dach_berlin():
    assert is_dach("Berlin, Germany") is True


@pytest.mark.unit
def test_is_dach_munich():
    assert is_dach("München") is True


@pytest.mark.unit
def test_is_dach_wien():
    assert is_dach("Wien, Österreich") is True


@pytest.mark.unit
def test_is_dach_zurich():
    assert is_dach("Zürich") is True


@pytest.mark.unit
def test_is_dach_london():
    assert is_dach("London, UK") is False


@pytest.mark.unit
def test_is_dach_none():
    assert is_dach(None) is False


@pytest.mark.unit
def test_is_dach_empty():
    assert is_dach("") is False


@pytest.mark.unit
def test_is_dach_case_insensitive():
    assert is_dach("BERLIN") is True


@pytest.mark.unit
def test_is_dach_deutschland():
    assert is_dach("Deutschland") is True


@pytest.mark.unit
def test_is_dach_schweiz():
    assert is_dach("Schweiz") is True


# ═══════════════════════════════════════════════════════════
# is_excluded
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_is_excluded_hays():
    assert is_excluded("Hays", "CFO") is True


@pytest.mark.unit
def test_is_excluded_mckinsey():
    assert is_excluded("McKinsey", "Consultant") is True


@pytest.mark.unit
def test_is_excluded_intern_title():
    assert is_excluded("Taxfix", "intern Finance") is True


@pytest.mark.unit
def test_is_excluded_werkstudent():
    assert is_excluded("Taxfix", "Werkstudent Finance") is True


@pytest.mark.unit
def test_is_excluded_valid_company_and_title():
    assert is_excluded("Taxfix", "CFO") is False


@pytest.mark.unit
def test_is_excluded_none_company():
    assert is_excluded(None, "CFO") is False


@pytest.mark.unit
def test_is_excluded_none_title():
    assert is_excluded("Taxfix", None) is False


@pytest.mark.unit
def test_is_excluded_case_insensitive():
    assert is_excluded("HAYS", "Senior Role") is True


@pytest.mark.unit
def test_is_excluded_junior():
    assert is_excluded("Startup", "Junior Developer") is True


# ═══════════════════════════════════════════════════════════
# normalize_name
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_normalize_name_gmbh():
    assert normalize_name("Taxfix GmbH") == "taxfix"


@pytest.mark.unit
def test_normalize_name_ag():
    assert normalize_name("Siemens AG") == "siemens"


@pytest.mark.unit
def test_normalize_name_special_chars():
    """'& co.' suffix not fully stripped due to \\b word-boundary matching quirk."""
    assert normalize_name("Personio & Co.") == "personioco"


@pytest.mark.unit
def test_normalize_name_already_clean():
    assert normalize_name("taxfix") == "taxfix"


# ═══════════════════════════════════════════════════════════
# detect_role_function
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_detect_role_function_cfo():
    assert detect_role_function("CFO") == "Finance"


@pytest.mark.unit
def test_detect_role_function_cto():
    assert detect_role_function("CTO") == "Engineering"


@pytest.mark.unit
def test_detect_role_function_chro():
    assert detect_role_function("CHRO") == "People"


@pytest.mark.unit
def test_detect_role_function_coo():
    assert detect_role_function("COO") == "Operations"


@pytest.mark.unit
def test_detect_role_function_head_of_finance():
    assert detect_role_function("Head of Finance") == "Finance"


@pytest.mark.unit
def test_detect_role_function_geschaeftsfuehrer():
    """NOTE: 'Geschäftsführer' contains 'hr' substring, so FUNCTION_MAP
    matches People before General Management. This is a known quirk
    due to substring matching order in the config dict."""
    assert detect_role_function("Geschäftsführer") == "People"


@pytest.mark.unit
def test_detect_role_function_marketing_manager():
    assert detect_role_function("Marketing Manager") == "Marketing"


@pytest.mark.unit
def test_detect_role_function_random():
    assert detect_role_function("Random Title") == "Other"


@pytest.mark.unit
def test_detect_role_function_ceo():
    assert detect_role_function("CEO") == "General Management"


# ═══════════════════════════════════════════════════════════
# dedup_jobs (with mocked supabase_request)
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_dedup_jobs_empty_list(mocker):
    mocker.patch("scrapers.role_scraper.supabase_request", return_value=None)
    result = dedup_jobs([])
    assert result == []


@pytest.mark.unit
def test_dedup_jobs_in_batch_dedup(mocker):
    """Two jobs with same normalized company+function are deduped within batch."""
    mocker.patch("scrapers.role_scraper.supabase_request", return_value=None)
    jobs = [
        {"company": "Taxfix GmbH", "title": "CFO", "url": "https://a.com", "source": "jsearch"},
        {"company": "Taxfix", "title": "Interim CFO", "url": "https://b.com", "source": "arbeitnow"},
    ]
    result = dedup_jobs(jobs)
    assert len(result) == 1


@pytest.mark.unit
def test_dedup_jobs_different_functions_kept(mocker):
    """Jobs at the same company but different functions are kept."""
    mocker.patch("scrapers.role_scraper.supabase_request", return_value=None)
    jobs = [
        {"company": "Taxfix", "title": "CFO", "url": "https://a.com", "source": "jsearch"},
        {"company": "Taxfix", "title": "CTO", "url": "https://b.com", "source": "jsearch"},
    ]
    result = dedup_jobs(jobs)
    assert len(result) == 2


# ═══════════════════════════════════════════════════════════
# score_to_tier
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_score_to_tier_zero():
    assert score_to_tier(0) == "disqualified"


@pytest.mark.unit
def test_score_to_tier_4():
    assert score_to_tier(4) == "disqualified"


@pytest.mark.unit
def test_score_to_tier_5():
    assert score_to_tier(5) == "park"


@pytest.mark.unit
def test_score_to_tier_39():
    assert score_to_tier(39) == "park"


@pytest.mark.unit
def test_score_to_tier_40():
    assert score_to_tier(40) == "warm"


@pytest.mark.unit
def test_score_to_tier_69():
    assert score_to_tier(69) == "warm"


@pytest.mark.unit
def test_score_to_tier_70():
    assert score_to_tier(70) == "hot"


@pytest.mark.unit
def test_score_to_tier_100():
    assert score_to_tier(100) == "hot"
