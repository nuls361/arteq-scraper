"""
E2E tests for candidate_pipeline — full main() flow with mocked step functions.

The candidate pipeline has a complex main() that calls several source functions
(search_pdl, scrape_marketplaces, search_thought_leaders, enrich_via_apollo)
plus DB functions (check_candidate_table, load_existing_candidates, write_to_supabase).
We mock at the step-function level since the sources use different HTTP clients
(requests, BeautifulSoup, DDGS) and the full HTTP mocking would be extremely brittle.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import responses

from tests.fixtures.contacts import CANDIDATE_INTERIM_CFO, CANDIDATE_FRACTIONAL_CTO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPABASE_BASE = "https://test.supabase.co"


def _make_candidate(name, linkedin, source="pdl", function="cfo", email=None):
    """Build a minimal candidate dict matching candidate_pipeline format."""
    return {
        "full_name": name,
        "first_name": name.split()[0],
        "last_name": name.split()[-1],
        "email": email,
        "phone": None,
        "linkedin_url": linkedin,
        "current_title": f"Interim {function.upper()}",
        "function": function,
        "employment_type": "interim",
        "location_city": "Berlin",
        "location_country": "germany",
        "source": source,
        "source_url": linkedin,
        "skills": ["strategy", "leadership"],
        "bio": f"Experienced {function.upper()} professional.",
    }


PDL_CANDIDATES = [
    _make_candidate("Klaus Fischer", "https://linkedin.com/in/klausfischer", "pdl", "cfo"),
    _make_candidate("Anna Mueller", "https://linkedin.com/in/annamueller", "pdl", "cto"),
]

MARKETPLACE_CANDIDATES = [
    _make_candidate("Lisa Berger", "https://linkedin.com/in/lisaberger", "comatch", "cfo"),
]

THOUGHT_LEADER_CANDIDATES = [
    _make_candidate("Max Schmidt", "https://linkedin.com/in/maxschmidt", "substack", "coo"),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_full_candidate_pipeline_run(monkeypatch, mocker):
    """Full run: PDL + marketplaces + thought leaders + Apollo, dedup, write."""
    import candidate_pipeline as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "PDL_API_KEY", "test-pdl-key")
    monkeypatch.setattr(mod, "APOLLO_API_KEY", "test-apollo-key")

    # Mock check_candidate_table -> True
    mocker.patch.object(mod, "check_candidate_table", return_value=True)

    # Mock load_existing_candidates -> empty sets (no existing candidates)
    mocker.patch.object(mod, "load_existing_candidates", return_value=(set(), set()))

    # Mock sources
    mocker.patch.object(mod, "search_pdl", return_value=PDL_CANDIDATES.copy())
    mocker.patch.object(mod, "scrape_marketplaces", return_value=MARKETPLACE_CANDIDATES.copy())
    mocker.patch.object(mod, "search_thought_leaders", return_value=THOUGHT_LEADER_CANDIDATES.copy())

    # Mock Apollo enrichment (returns count of enriched)
    mocker.patch.object(mod, "enrich_via_apollo", return_value=2)

    # Mock write_to_supabase
    mock_write = mocker.patch.object(mod, "write_to_supabase")

    # Mock write_csv_backup
    mocker.patch.object(mod, "write_csv_backup")

    # Mock print_summary
    mocker.patch.object(mod, "print_summary")

    mod.main()

    # Verify sources were called
    mod.search_pdl.assert_called_once()
    mod.scrape_marketplaces.assert_called_once()
    mod.search_thought_leaders.assert_called_once()
    mod.enrich_via_apollo.assert_called_once()

    # Verify write_to_supabase was called with all candidates (4 total, no dupes)
    mock_write.assert_called_once()
    written_candidates = mock_write.call_args[0][0]
    assert len(written_candidates) == 4, f"Expected 4 candidates, got {len(written_candidates)}"

    # Verify all sources represented
    sources = {c["source"] for c in written_candidates}
    assert "pdl" in sources
    assert "comatch" in sources
    assert "substack" in sources


@pytest.mark.e2e
def test_no_pdl_key_skips_pdl(monkeypatch, mocker):
    """When PDL_API_KEY is empty, PDL raises but pipeline continues with other sources."""
    import candidate_pipeline as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "PDL_API_KEY", "")
    monkeypatch.setattr(mod, "APOLLO_API_KEY", "test-apollo-key")

    mocker.patch.object(mod, "check_candidate_table", return_value=True)
    mocker.patch.object(mod, "load_existing_candidates", return_value=(set(), set()))

    # PDL: returns empty (no API key = no results inside search_pdl)
    mocker.patch.object(mod, "search_pdl", return_value=[])

    # Other sources still work
    mocker.patch.object(mod, "scrape_marketplaces", return_value=MARKETPLACE_CANDIDATES.copy())
    mocker.patch.object(mod, "search_thought_leaders", return_value=THOUGHT_LEADER_CANDIDATES.copy())
    mocker.patch.object(mod, "enrich_via_apollo", return_value=1)

    mock_write = mocker.patch.object(mod, "write_to_supabase")
    mocker.patch.object(mod, "write_csv_backup")
    mocker.patch.object(mod, "print_summary")

    mod.main()

    # write_to_supabase should be called with marketplace + thought leader candidates
    mock_write.assert_called_once()
    written_candidates = mock_write.call_args[0][0]
    assert len(written_candidates) == 2, f"Expected 2 candidates (no PDL), got {len(written_candidates)}"

    # No PDL candidates
    sources = {c["source"] for c in written_candidates}
    assert "pdl" not in sources
    assert "comatch" in sources
    assert "substack" in sources


@pytest.mark.e2e
def test_all_duplicates_none_written(monkeypatch, mocker):
    """All candidates already exist in DB — none written."""
    import candidate_pipeline as mod

    monkeypatch.setattr(mod, "SUPABASE_URL", SUPABASE_BASE)
    monkeypatch.setattr(mod, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(mod, "PDL_API_KEY", "test-pdl-key")
    monkeypatch.setattr(mod, "APOLLO_API_KEY", "test-apollo-key")

    mocker.patch.object(mod, "check_candidate_table", return_value=True)

    # All LinkedIn URLs already exist (normalized with www. as normalize_linkedin_url does)
    existing_linkedin = {
        "https://www.linkedin.com/in/klausfischer",
        "https://www.linkedin.com/in/annamueller",
        "https://www.linkedin.com/in/lisaberger",
        "https://www.linkedin.com/in/maxschmidt",
    }
    existing_names = set()
    mocker.patch.object(mod, "load_existing_candidates", return_value=(existing_linkedin, existing_names))

    # Sources return candidates that are all duplicates
    mocker.patch.object(mod, "search_pdl", return_value=PDL_CANDIDATES.copy())
    mocker.patch.object(mod, "scrape_marketplaces", return_value=MARKETPLACE_CANDIDATES.copy())
    mocker.patch.object(mod, "search_thought_leaders", return_value=THOUGHT_LEADER_CANDIDATES.copy())
    mocker.patch.object(mod, "enrich_via_apollo", return_value=0)

    mock_write = mocker.patch.object(mod, "write_to_supabase")
    mocker.patch.object(mod, "write_csv_backup")
    mocker.patch.object(mod, "print_summary")

    mod.main()

    # write_to_supabase should NOT be called (no new candidates after dedup)
    # The main() code calls write_to_supabase only if table_ok and all_candidates is truthy
    mock_write.assert_not_called()
