"""
E2E tests for signal_scraper — full main() flow with HTTP-level mocking.

The signal scraper uses feedparser (urllib, not requests) for RSS and DDGS for
DuckDuckGo searches. These are mocked via mocker.patch since they don't go
through the `requests` library. Supabase REST and Claude API are mocked at
HTTP level using `responses`.
"""

import json
from unittest.mock import MagicMock

import pytest
import responses

from tests.fixtures.companies import TAXFIX, PERSONIO
from tests.fixtures.claude_responses import (
    CLASSIFY_SIGNALS_HOT,
    CLASSIFY_SIGNALS_IRRELEVANT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPABASE_BASE = "https://test.supabase.co"

COMPANY_SLIM_LIST = [
    {"id": TAXFIX["id"], "name": "Taxfix", "domain": "taxfix.de"},
    {"id": PERSONIO["id"], "name": "Personio GmbH", "domain": "personio.de"},
]


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


def _mock_feedparser_result(entries):
    """Create a mock feedparser.parse() return value."""
    mock_feed = MagicMock()
    mock_entries = []
    for e in entries:
        entry = MagicMock()
        entry.get = lambda key, default="", _e=e: _e.get(key, default)
        mock_entries.append(entry)
    mock_feed.entries = mock_entries
    return mock_feed


def _mock_ddgs_results(articles):
    """Create mock DDGS().news() results."""
    return [
        {
            "title": a.get("title", ""),
            "body": a.get("summary", ""),
            "url": a.get("source_url", ""),
            "date": a.get("published", ""),
        }
        for a in articles
    ]


RSS_ENTRY_TAXFIX_FUNDING = {
    "title": "Taxfix raises $100M in Series C funding round",
    "summary": "Berlin-based fintech Taxfix raised $100 million in Series C funding.",
    "link": "https://techcrunch.com/taxfix-series-c",
    "published": "2026-03-01",
}

DDG_ARTICLE_TAXFIX = {
    "title": "Taxfix CEO announces restructuring after Series C",
    "summary": "Taxfix is restructuring its leadership team following the Series C round.",
    "source_url": "https://news.example.com/taxfix-restructuring",
    "published": "2026-03-02",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@responses.activate
def test_full_signal_scraper_run(monkeypatch, mocker):
    """Full run: RSS + DDG find articles, Claude classifies, signals written."""
    import scrapers.signal_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _: None)

    # -- Supabase: get_monitored_companies (hot roles -> company IDs -> companies)
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"company_id": TAXFIX["id"]}],
        status=200,
    )
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[COMPANY_SLIM_LIST[0]],
        status=200,
    )

    # -- RSS: mock feedparser.parse to return an entry that matches "Taxfix"
    mock_feed = _mock_feedparser_result([RSS_ENTRY_TAXFIX_FUNDING])
    mocker.patch("scrapers.signal_scraper.feedparser.parse", return_value=mock_feed)

    # -- DDG: mock DDGS context manager
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.news.return_value = _mock_ddgs_results([DDG_ARTICLE_TAXFIX])
    mock_ddgs_class = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("scrapers.signal_scraper.DDGS", mock_ddgs_class)

    # -- Supabase: dedup_signals (no existing signals)
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/signal",
        json=[],
        status=200,
    )

    # -- Claude: classify as hot
    responses.add(
        responses.POST,
        "https://api.anthropic.com/v1/messages",
        json=_claude_response(CLASSIFY_SIGNALS_HOT),
        status=200,
    )

    # -- Supabase: write signal + dossier + patch company
    responses.add(
        responses.POST,
        f"{SUPABASE_BASE}/rest/v1/signal",
        json=[{"id": "sig-new-001"}],
        status=201,
    )
    responses.add(
        responses.POST,
        f"{SUPABASE_BASE}/rest/v1/company_dossier",
        json=[{"id": "dossier-001"}],
        status=201,
    )
    responses.add(
        responses.PATCH,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[{"id": TAXFIX["id"]}],
        status=200,
    )

    # Run
    mod.main()

    # Verify Claude was called
    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) >= 1, "Claude classification call expected"

    # Verify signal was written
    signal_posts = [
        c for c in responses.calls
        if "test.supabase.co/rest/v1/signal" in c.request.url and c.request.method == "POST"
    ]
    assert len(signal_posts) >= 1, "At least one signal should be written"


@pytest.mark.e2e
@responses.activate
def test_no_companies_early_exit(monkeypatch, mocker):
    """When get_monitored_companies returns empty, main exits early."""
    import scrapers.signal_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")

    # Supabase: no hot roles
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[],
        status=200,
    )
    # Fallback: no companies by score
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[],
        status=200,
    )

    # Mock feedparser and DDGS to verify they are NOT called
    mock_parse = mocker.patch("scrapers.signal_scraper.feedparser.parse")
    mock_ddgs = mocker.patch("scrapers.signal_scraper.DDGS")

    mod.main()

    mock_parse.assert_not_called()
    mock_ddgs.assert_not_called()

    # No Claude calls
    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) == 0


@pytest.mark.e2e
@responses.activate
def test_rss_errors_ddg_exception(monkeypatch, mocker):
    """RSS returns empty feed, DDG throws exception — main still completes."""
    import scrapers.signal_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _: None)

    # Supabase: 1 company to monitor
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"company_id": TAXFIX["id"]}],
        status=200,
    )
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[COMPANY_SLIM_LIST[0]],
        status=200,
    )

    # RSS: empty feed (no entries)
    mock_feed = _mock_feedparser_result([])
    mocker.patch("scrapers.signal_scraper.feedparser.parse", return_value=mock_feed)

    # DDG: throws exception
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.news.side_effect = Exception("DDG rate limit")
    mock_ddgs_class = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("scrapers.signal_scraper.DDGS", mock_ddgs_class)

    # main() should not raise — graceful handling
    mod.main()

    # No articles found, so no Claude calls and no signal writes
    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) == 0

    signal_posts = [
        c for c in responses.calls
        if "test.supabase.co/rest/v1/signal" in c.request.url and c.request.method == "POST"
    ]
    assert len(signal_posts) == 0


@pytest.mark.e2e
@responses.activate
def test_all_irrelevant_no_signals_written(monkeypatch, mocker):
    """Claude classifies all articles as irrelevant — no signals written."""
    import scrapers.signal_scraper as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _: None)

    # Supabase: 1 company to monitor
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/role",
        json=[{"company_id": TAXFIX["id"]}],
        status=200,
    )
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/company",
        json=[COMPANY_SLIM_LIST[0]],
        status=200,
    )

    # RSS: one article matching keyword "funding"
    rss_entry_funding = {
        "title": "Taxfix Series C funding round announced",
        "summary": "Taxfix has raised new funding in a major round.",
        "link": "https://techcrunch.com/taxfix-funding",
        "published": "2026-03-01",
    }
    mock_feed = _mock_feedparser_result([rss_entry_funding])
    mocker.patch("scrapers.signal_scraper.feedparser.parse", return_value=mock_feed)

    # DDG: no results
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.news.return_value = []
    mock_ddgs_class = MagicMock()
    mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs_instance)
    mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("scrapers.signal_scraper.DDGS", mock_ddgs_class)

    # Supabase dedup: no existing signals
    responses.add(
        responses.GET,
        f"{SUPABASE_BASE}/rest/v1/signal",
        json=[],
        status=200,
    )

    # Claude: classify as irrelevant
    responses.add(
        responses.POST,
        "https://api.anthropic.com/v1/messages",
        json=_claude_response(CLASSIFY_SIGNALS_IRRELEVANT),
        status=200,
    )

    mod.main()

    # Claude was called
    claude_calls = [c for c in responses.calls if "anthropic.com" in c.request.url]
    assert len(claude_calls) >= 1, "Claude should still be called"

    # No signals written (all irrelevant)
    signal_posts = [
        c for c in responses.calls
        if "test.supabase.co/rest/v1/signal" in c.request.url and c.request.method == "POST"
    ]
    assert len(signal_posts) == 0, "No signals should be written when all are irrelevant"
