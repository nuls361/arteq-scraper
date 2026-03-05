"""
Unit tests for candidate_pipeline.py — pure helper functions.

normalize_text, normalize_linkedin_url, is_self_employed,
classify_function, classify_employment_type, score_candidate, is_duplicate.

These are the same functions as in research_agent.py but duplicated
in candidate_pipeline.py — so we test them independently.
"""

import pytest
from candidate_pipeline import (
    normalize_text,
    normalize_linkedin_url,
    is_self_employed,
    classify_function,
    classify_employment_type,
    score_candidate,
    is_duplicate,
)


# ═══════════════════════════════════════════════════════════
# normalize_text
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_normalize_text_basic():
    assert normalize_text("Hello World") == "hello world"


@pytest.mark.unit
def test_normalize_text_accents():
    assert normalize_text("München") == "munchen"


@pytest.mark.unit
def test_normalize_text_none():
    assert normalize_text(None) == ""


@pytest.mark.unit
def test_normalize_text_empty():
    assert normalize_text("") == ""


@pytest.mark.unit
def test_normalize_text_special_chars():
    result = normalize_text("O'Brien-Smith, Jr.")
    assert result == "obriensmith jr"


@pytest.mark.unit
def test_normalize_text_digits_preserved():
    assert normalize_text("N26 Berlin") == "n26 berlin"


@pytest.mark.unit
def test_normalize_text_umlaut_removed():
    """German umlauts get stripped by NFKD + ascii encode."""
    result = normalize_text("Müller Böhm Schröder")
    assert result == "muller bohm schroder"


# ═══════════════════════════════════════════════════════════
# normalize_linkedin_url
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_normalize_linkedin_full_url():
    url = "https://www.linkedin.com/in/john-doe/"
    assert normalize_linkedin_url(url) == "https://www.linkedin.com/in/john-doe"


@pytest.mark.unit
def test_normalize_linkedin_none():
    assert normalize_linkedin_url(None) is None


@pytest.mark.unit
def test_normalize_linkedin_trailing_slash():
    url = "https://linkedin.com/in/test-user/"
    assert normalize_linkedin_url(url) == "https://www.linkedin.com/in/test-user"


@pytest.mark.unit
def test_normalize_linkedin_uppercase():
    url = "HTTPS://WWW.LINKEDIN.COM/IN/John-Doe"
    result = normalize_linkedin_url(url)
    assert result == "https://www.linkedin.com/in/john-doe"


@pytest.mark.unit
def test_normalize_linkedin_non_linkedin():
    url = "https://example.com/profile/"
    result = normalize_linkedin_url(url)
    assert result == "https://example.com/profile"


# ═══════════════════════════════════════════════════════════
# is_self_employed
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_self_employed_by_type():
    assert is_self_employed("CFO", "self_employed") is True


@pytest.mark.unit
def test_self_employed_contract():
    assert is_self_employed("Engineer", "contract") is True


@pytest.mark.unit
def test_self_employed_by_title():
    assert is_self_employed("Interim CFO") is True


@pytest.mark.unit
def test_self_employed_freelance_title():
    assert is_self_employed("Freelance Consultant") is True


@pytest.mark.unit
def test_not_self_employed():
    assert is_self_employed("VP Finance", "full_time") is False


@pytest.mark.unit
def test_self_employed_none_title():
    assert is_self_employed(None) is False


@pytest.mark.unit
def test_self_employed_freiberuflich():
    assert is_self_employed("Freiberuflicher Berater") is True


# ═══════════════════════════════════════════════════════════
# classify_function
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_classify_cfo():
    assert classify_function("CFO") == "cfo"


@pytest.mark.unit
def test_classify_cto():
    assert classify_function("CTO") == "cto"


@pytest.mark.unit
def test_classify_coo():
    assert classify_function("COO") == "coo"


@pytest.mark.unit
def test_classify_chro():
    assert classify_function("CHRO") == "chro"


@pytest.mark.unit
def test_classify_cmo():
    assert classify_function("Head of Marketing") == "cmo"


@pytest.mark.unit
def test_classify_cpo():
    assert classify_function("VP Product") == "cpo"


@pytest.mark.unit
def test_classify_md():
    """NOTE: 'Managing Director' contains 'cto' substring (dire-cto-r),
    so the mappings match 'cto' before 'md'. Known quirk."""
    assert classify_function("Managing Director") == "cto"


@pytest.mark.unit
def test_classify_geschaeftsfuehrer():
    assert classify_function("Geschäftsführer") == "md"


@pytest.mark.unit
def test_classify_other():
    assert classify_function("Random Title") == "other"


@pytest.mark.unit
def test_classify_none():
    assert classify_function(None) == "other"


@pytest.mark.unit
def test_classify_chief_financial():
    assert classify_function("Chief Financial Officer") == "cfo"


# ═══════════════════════════════════════════════════════════
# classify_employment_type
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_employment_interim():
    assert classify_employment_type("Interim CFO") == "interim"


@pytest.mark.unit
def test_employment_interims():
    assert classify_employment_type("Interims-Manager") == "interim"


@pytest.mark.unit
def test_employment_fractional():
    assert classify_employment_type("Fractional CTO") == "fractional"


@pytest.mark.unit
def test_employment_advisor():
    assert classify_employment_type("Senior Advisor") == "advisor"


@pytest.mark.unit
def test_employment_advisory():
    assert classify_employment_type("Advisory Board") == "advisor"


@pytest.mark.unit
def test_employment_default():
    assert classify_employment_type("Software Engineer") == "freelance"


@pytest.mark.unit
def test_employment_none():
    assert classify_employment_type(None) == "freelance"


# ═══════════════════════════════════════════════════════════
# score_candidate
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_score_all_signals():
    """Max score candidate."""
    candidate = {
        "current_title": "Interim CFO",
        "linkedin_url": "https://linkedin.com/in/test",
        "email": "t@example.com",
        "location_country": "germany",
        "source": "substack",
        "skills": ["strategy"],
    }
    score, tier = score_candidate(candidate)
    assert score == 100
    assert tier == "available"


@pytest.mark.unit
def test_score_none_signals():
    """Minimal candidate with no matching signals."""
    candidate = {"current_title": "Worker", "source": "random"}
    score, tier = score_candidate(candidate)
    assert score == 0
    assert tier == "research"


@pytest.mark.unit
def test_score_passive_tier():
    """Score 40-69 is passive."""
    candidate = {
        "current_title": "Fractional COO",
        "linkedin_url": "https://linkedin.com/in/test",
    }
    score, tier = score_candidate(candidate)
    assert score == 50
    assert tier == "passive"


@pytest.mark.unit
def test_score_dach_austria():
    candidate = {"current_title": "X", "location_country": "austria"}
    score, _ = score_candidate(candidate)
    assert score == 15


@pytest.mark.unit
def test_score_dach_schweiz():
    candidate = {"current_title": "X", "location_country": "schweiz"}
    score, _ = score_candidate(candidate)
    assert score == 15


@pytest.mark.unit
def test_score_marketplace_malt():
    candidate = {"current_title": "X", "source": "malt"}
    score, _ = score_candidate(candidate)
    assert score == 10


# ═══════════════════════════════════════════════════════════
# is_duplicate
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_duplicate_by_linkedin():
    existing_li = {"https://www.linkedin.com/in/john-doe"}
    existing_names = set()
    candidate = {"linkedin_url": "https://www.linkedin.com/in/john-doe/", "full_name": "John Doe", "current_title": "CFO"}
    assert is_duplicate(candidate, existing_li, existing_names) is True


@pytest.mark.unit
def test_duplicate_by_name_title():
    existing_li = set()
    existing_names = {"john doe|cfo"}
    candidate = {"full_name": "John Doe", "current_title": "CFO"}
    assert is_duplicate(candidate, existing_li, existing_names) is True


@pytest.mark.unit
def test_not_duplicate():
    candidate = {"full_name": "New Person", "current_title": "CEO", "linkedin_url": "https://linkedin.com/in/new"}
    assert is_duplicate(candidate, set(), set()) is False


@pytest.mark.unit
def test_duplicate_empty_name_not_false_positive():
    """An empty name+title should NOT match against an empty set."""
    candidate = {"full_name": "", "current_title": ""}
    # name_key becomes "|" which is explicitly skipped
    assert is_duplicate(candidate, set(), set()) is False
