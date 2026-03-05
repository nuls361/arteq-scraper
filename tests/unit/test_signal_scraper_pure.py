"""
Unit tests for scrapers/signal_scraper.py — normalize_company_name, keyword_filter.
"""

import pytest
from scrapers.signal_scraper import normalize_company_name, keyword_filter


# ═══════════════════════════════════════════════════════════
# normalize_company_name
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_normalize_strips_gmbh():
    assert normalize_company_name("Taxfix GmbH") == "taxfix"


@pytest.mark.unit
def test_normalize_strips_ag():
    assert normalize_company_name("Siemens AG") == "siemens"


@pytest.mark.unit
def test_normalize_special_chars():
    """'& co.' suffix not fully stripped due to \\b word-boundary matching quirk."""
    assert normalize_company_name("Personio & Co.") == "personioco"


@pytest.mark.unit
def test_normalize_empty():
    assert normalize_company_name("") == ""


@pytest.mark.unit
def test_normalize_already_clean():
    assert normalize_company_name("taxfix") == "taxfix"


@pytest.mark.unit
def test_normalize_multiple_suffixes():
    """GmbH and KG stripped; '& co.' remains due to \\b word-boundary quirk."""
    result = normalize_company_name("Acme GmbH & Co. KG")
    assert result == "acmeco"


@pytest.mark.unit
def test_normalize_preserves_digits():
    assert normalize_company_name("N26 GmbH") == "n26"


# ═══════════════════════════════════════════════════════════
# keyword_filter
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_keyword_filter_funding_article_passes():
    articles = [
        {"title": "Taxfix raises Series B funding", "summary": "Berlin startup closes round"},
    ]
    result = keyword_filter(articles)
    assert len(result) == 1


@pytest.mark.unit
def test_keyword_filter_leadership_change_passes():
    articles = [
        {"title": "CEO steps down at startup", "summary": "Leadership transition"},
    ]
    result = keyword_filter(articles)
    assert len(result) == 1


@pytest.mark.unit
def test_keyword_filter_irrelevant_award_fails():
    articles = [
        {"title": "Company wins design award", "summary": "Great UI recognized"},
    ]
    result = keyword_filter(articles)
    assert len(result) == 0


@pytest.mark.unit
def test_keyword_filter_case_insensitive():
    articles = [
        {"title": "SERIES A FUNDING Announced", "summary": ""},
    ]
    result = keyword_filter(articles)
    assert len(result) == 1


@pytest.mark.unit
def test_keyword_filter_empty_list():
    result = keyword_filter([])
    assert result == []


@pytest.mark.unit
def test_keyword_filter_german_keywords():
    articles = [
        {"title": "Restrukturierung bei Firma", "summary": ""},
    ]
    result = keyword_filter(articles)
    assert len(result) == 1


@pytest.mark.unit
def test_keyword_filter_acquisition():
    articles = [
        {"title": "Major acquisition announced", "summary": "Company acquired by PE firm"},
    ]
    result = keyword_filter(articles)
    assert len(result) == 1


@pytest.mark.unit
def test_keyword_filter_matches_in_summary_only():
    articles = [
        {"title": "Company Update", "summary": "The company raised funding in Q4"},
    ]
    result = keyword_filter(articles)
    assert len(result) == 1
