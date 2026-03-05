"""
Unit tests for clean_json_response from ALL modules that implement it.

There are two variants:
  1. FULL (handles both { and [):
     - scrapers.role_scraper
     - scrapers.signal_scraper
     - enrichment.company_enricher
     - pipeline.research_agent

  2. OBJECT-ONLY (handles only {, not [):
     - enrichment.contact_enricher
     - pipeline.sdr_agent
     - pipeline.ae_agent
"""

import pytest

from scrapers.role_scraper import clean_json_response as role_clean
from scrapers.signal_scraper import clean_json_response as signal_clean
from enrichment.company_enricher import clean_json_response as company_clean
from enrichment.contact_enricher import clean_json_response as contact_clean
from pipeline.sdr_agent import clean_json_response as sdr_clean
from pipeline.ae_agent import clean_json_response as ae_clean
from pipeline.research_agent import clean_json_response as research_clean

# Group the full-support versions
FULL_IMPLEMENTATIONS = [
    pytest.param(role_clean, id="role_scraper"),
    pytest.param(signal_clean, id="signal_scraper"),
    pytest.param(company_clean, id="company_enricher"),
    pytest.param(research_clean, id="research_agent"),
]

# Group the object-only versions
OBJECT_ONLY_IMPLEMENTATIONS = [
    pytest.param(contact_clean, id="contact_enricher"),
    pytest.param(sdr_clean, id="sdr_agent"),
    pytest.param(ae_clean, id="ae_agent"),
]

ALL_IMPLEMENTATIONS = FULL_IMPLEMENTATIONS + OBJECT_ONLY_IMPLEMENTATIONS


# ═══════════════════════════════════════════════════════════
# Tests that apply to ALL implementations
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_plain_json_object(clean_fn):
    assert clean_fn('{"key": "value"}') == '{"key": "value"}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_markdown_fenced_json(clean_fn):
    text = '```json\n{"key": "value"}\n```'
    assert clean_fn(text) == '{"key": "value"}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_text_before_json(clean_fn):
    text = 'Here is the JSON: {"key": "value"}'
    assert clean_fn(text) == '{"key": "value"}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_nested_objects(clean_fn):
    text = '{"a": {"b": 1}}'
    assert clean_fn(text) == '{"a": {"b": 1}}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_text_after_json_trimmed(clean_fn):
    text = '{"key": "value"} some trailing text'
    assert clean_fn(text) == '{"key": "value"}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_generic_code_fences(clean_fn):
    """Generic ``` fences (without 'json' label) are also handled."""
    text = '```\n{"key": "value"}\n```'
    assert clean_fn(text) == '{"key": "value"}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", ALL_IMPLEMENTATIONS)
def test_whitespace_only_returns_empty(clean_fn):
    """Whitespace-only input returns empty or whitespace."""
    result = clean_fn("   ")
    assert result.strip() == ""


# ═══════════════════════════════════════════════════════════
# Tests for FULL implementations (support both { and [)
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", FULL_IMPLEMENTATIONS)
def test_json_array_full(clean_fn):
    text = '[{"a": 1}]'
    assert clean_fn(text) == '[{"a": 1}]'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", FULL_IMPLEMENTATIONS)
def test_json_array_with_text_before(clean_fn):
    text = 'Here is the result: [{"a": 1}, {"b": 2}]'
    assert clean_fn(text) == '[{"a": 1}, {"b": 2}]'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", FULL_IMPLEMENTATIONS)
def test_json_array_with_trailing_text(clean_fn):
    text = '[{"a": 1}] extra text'
    assert clean_fn(text) == '[{"a": 1}]'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", FULL_IMPLEMENTATIONS)
def test_array_preferred_when_first(clean_fn):
    """When [ appears before { in the text, the array is extracted."""
    text = 'Result: [{"key": "val"}]'
    result = clean_fn(text)
    assert result == '[{"key": "val"}]'


# ═══════════════════════════════════════════════════════════
# Tests for OBJECT-ONLY implementations (only { support)
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", OBJECT_ONLY_IMPLEMENTATIONS)
def test_json_array_passthrough_when_starts_with_bracket(clean_fn):
    """Object-only implementations pass arrays through unchanged when
    the input starts with '['. They check t[0] not in ('{', '[') first,
    so '[' passes that check (it IS in the tuple). Then they check
    t[0] == '{', which is False, so no depth-tracking occurs.
    The original text is returned as-is."""
    text = '[{"a": 1}]'
    result = clean_fn(text)
    # The array is returned unchanged because the function doesn't enter
    # the depth-tracking block (t[0] != '{')
    assert result == '[{"a": 1}]'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", OBJECT_ONLY_IMPLEMENTATIONS)
def test_text_before_array_extracts_object_only(clean_fn):
    """When text precedes an array, object-only implementations look for '{'
    and will extract the first inner object, NOT the array."""
    text = 'Here is the result: [{"a": 1}]'
    result = clean_fn(text)
    # These find '{' first (not '[') and extract '{"a": 1}'
    assert result == '{"a": 1}'


@pytest.mark.unit
@pytest.mark.parametrize("clean_fn", OBJECT_ONLY_IMPLEMENTATIONS)
def test_plain_array_passthrough_object_only(clean_fn):
    """A plain JSON array with non-object elements passes through."""
    text = '[1, 2, 3]'
    result = clean_fn(text)
    # t[0] is '[' which is in ('{', '['), so the first check passes.
    # Then t[0] == '{' is False, so no depth tracking. Returns as-is.
    assert result == '[1, 2, 3]'
