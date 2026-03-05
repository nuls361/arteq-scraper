"""Integration tests for scrapers/signal_scraper.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

from tests.fixtures.companies import TAXFIX, PERSONIO, COMPANY_LIST_SLIM
from tests.fixtures.signals import (
    RSS_ARTICLE_FUNDING,
    DDG_ARTICLE_LEADERSHIP,
    ARTICLES_MIXED,
    HOT_SIGNAL,
)
from tests.fixtures.claude_responses import (
    CLASSIFY_SIGNALS_HOT,
    CLASSIFY_SIGNALS_IRRELEVANT,
)

import scrapers.signal_scraper as signal_scraper


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_claude_response(text, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "content": [{"type": "text", "text": text}],
    }
    resp.text = text
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# get_monitored_companies
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_get_monitored_companies_from_hot_roles(mocker, monkeypatch):
    """Should return companies that have hot roles."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if table == "role":
            return [{"company_id": TAXFIX["id"]}]
        if table == "company":
            return [{"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de"}]
        return []

    mocker.patch("scrapers.signal_scraper.supabase_request", side_effect=mock_supabase)

    result = signal_scraper.get_monitored_companies()
    assert len(result) == 1
    assert result[0]["name"] == "Taxfix"


@pytest.mark.integration
def test_get_monitored_companies_fallback_to_score(mocker, monkeypatch):
    """When no hot roles exist, fall back to top companies by score."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    call_count = [0]

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if table == "role":
            return []  # no hot roles
        if table == "company":
            call_count[0] += 1
            return COMPANY_LIST_SLIM
        return []

    mocker.patch("scrapers.signal_scraper.supabase_request", side_effect=mock_supabase)

    result = signal_scraper.get_monitored_companies()
    assert len(result) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# scan_rss_feeds
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_scan_rss_feeds_matches_articles(mocker, monkeypatch):
    """RSS entries mentioning a company name should be matched."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    mock_entry = MagicMock()
    mock_entry.get = lambda k, d="": {
        "title": "Taxfix raises $100M Series C",
        "summary": "Berlin-based fintech Taxfix raised $100M.",
        "link": "https://techcrunch.com/taxfix",
        "published": "2026-03-01",
    }.get(k, d)

    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]

    mocker.patch("scrapers.signal_scraper.feedparser.parse", return_value=mock_feed)

    companies = [{"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de"}]
    result = signal_scraper.scan_rss_feeds(companies)

    assert len(result) >= 1
    assert result[0]["company_name"] == "Taxfix"


# ═══════════════════════════════════════════════════════════════════════════════
# dedup_signals
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_dedup_signals_removes_existing_urls(mocker, monkeypatch):
    """Articles with URLs already in DB should be filtered out."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    mocker.patch(
        "scrapers.signal_scraper.supabase_request",
        return_value=[{"source_url": "https://techcrunch.com/taxfix-series-c"}],
    )

    companies = [{"id": TAXFIX["id"], "name": "Taxfix"}]
    result = signal_scraper.dedup_signals(ARTICLES_MIXED, companies)
    urls = [a["source_url"] for a in result]
    assert "https://techcrunch.com/taxfix-series-c" not in urls


@pytest.mark.integration
def test_dedup_signals_new_articles_pass(mocker, monkeypatch):
    """All new articles should pass through dedup."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    mocker.patch("scrapers.signal_scraper.supabase_request", return_value=[])

    companies = [{"id": TAXFIX["id"]}, {"id": PERSONIO["id"]}]
    result = signal_scraper.dedup_signals(ARTICLES_MIXED, companies)
    assert len(result) == len(ARTICLES_MIXED)


# ═══════════════════════════════════════════════════════════════════════════════
# classify_signals
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_classify_signals_hot(mocker, monkeypatch):
    """Hot signal should be returned with is_hot=True."""
    monkeypatch.setattr(signal_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch(
        "scrapers.signal_scraper.requests.post",
        return_value=_make_claude_response(CLASSIFY_SIGNALS_HOT),
    )
    mocker.patch("time.sleep")

    articles = [RSS_ARTICLE_FUNDING]
    result = signal_scraper.classify_signals(articles)

    assert len(result) == 1
    assert result[0]["is_hot"] is True
    assert result[0]["interim_relevance"] == "hot"


@pytest.mark.integration
def test_classify_signals_irrelevant_filtered(mocker, monkeypatch):
    """Irrelevant signals should be discarded."""
    monkeypatch.setattr(signal_scraper, "ANTHROPIC_KEY", "test-key")

    mocker.patch(
        "scrapers.signal_scraper.requests.post",
        return_value=_make_claude_response(CLASSIFY_SIGNALS_IRRELEVANT),
    )
    mocker.patch("time.sleep")

    articles = [{"company_name": "X", "title": "Award", "summary": "Won award",
                 "source_url": "u1", "source": "rss_gruenderszene", "published": ""}]
    result = signal_scraper.classify_signals(articles)
    assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# write_signals
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_write_signals_writes_signal_and_dossier(mocker, monkeypatch):
    """write_signals should write to signal + company_dossier tables."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    tables_posted = []

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if method == "POST":
            tables_posted.append(table)
            return [{"id": "sig-new"}]
        if method == "PATCH":
            return [{}]
        return []

    mocker.patch("scrapers.signal_scraper.supabase_request", side_effect=mock_supabase)

    signal = {
        "company_id": TAXFIX["id"],
        "company_name": "Taxfix",
        "title": "Taxfix raises $100M",
        "summary": "Series C funding",
        "source_url": "https://tc.com/taxfix",
        "source": "rss_techcrunch",
        "is_hot": True,
        "interim_relevance": "hot",
        "signal_type": "funding_round",
        "relevance_score": 90,
        "urgency": "high",
        "ai_description": "Funding signals growth.",
    }

    written = signal_scraper.write_signals([signal])
    assert written == 1
    assert "signal" in tables_posted
    assert "company_dossier" in tables_posted


@pytest.mark.integration
def test_write_signals_hot_triggers_enrichment(mocker, monkeypatch):
    """Hot signal should PATCH company with enrichment_status=pending."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")

    patch_calls = []

    def mock_supabase(method, table, data=None, params=None, upsert=False):
        if method == "PATCH":
            patch_calls.append((table, data))
            return [{}]
        if method == "POST":
            return [{"id": "sig-new"}]
        return []

    mocker.patch("scrapers.signal_scraper.supabase_request", side_effect=mock_supabase)

    signal = {
        "company_id": TAXFIX["id"], "company_name": "Taxfix",
        "title": "Taxfix raises $100M", "summary": "",
        "source_url": "https://tc.com/taxfix", "source": "rss_techcrunch",
        "is_hot": True, "interim_relevance": "hot", "signal_type": "funding_round",
        "relevance_score": 90, "urgency": "high", "ai_description": "",
    }

    signal_scraper.write_signals([signal])

    assert any("enrichment_status" in (d or {}) for _, d in patch_calls)


# ═══════════════════════════════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_main_full_flow(mocker, monkeypatch):
    """main() orchestrates all steps end-to-end."""
    monkeypatch.setattr(signal_scraper, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(signal_scraper, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(signal_scraper, "ANTHROPIC_KEY", "test-key")

    companies = [{"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de"}]

    mocker.patch("scrapers.signal_scraper.get_monitored_companies", return_value=companies)
    mocker.patch("scrapers.signal_scraper.scan_rss_feeds", return_value=[RSS_ARTICLE_FUNDING])
    mocker.patch("scrapers.signal_scraper.search_duckduckgo_news", return_value=[DDG_ARTICLE_LEADERSHIP])
    mocker.patch("scrapers.signal_scraper.keyword_filter", return_value=[RSS_ARTICLE_FUNDING])
    mocker.patch("scrapers.signal_scraper.dedup_signals", return_value=[RSS_ARTICLE_FUNDING])

    classified = [{
        **RSS_ARTICLE_FUNDING,
        "is_hot": True, "interim_relevance": "hot", "signal_type": "funding_round",
        "relevance_score": 90, "urgency": "high", "ai_description": "Test",
    }]
    mocker.patch("scrapers.signal_scraper.classify_signals", return_value=classified)
    mocker.patch("scrapers.signal_scraper.write_signals", return_value=1)

    signal_scraper.main()
