"""
Unit tests for dedup.py — normalize_company_name, extract_country,
generate_dedup_key, deduplicate_jobs.
"""

import pytest
from dedup import (
    normalize_company_name,
    extract_country,
    generate_dedup_key,
    deduplicate_jobs,
)


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
def test_normalize_strips_ug():
    assert normalize_company_name("MyStartup UG") == "mystartup"


@pytest.mark.unit
def test_normalize_strips_multiple_suffixes():
    """When name contains known suffixes, word-boundary matching applies.
    Note: '& co' and '& co.' use \\b which doesn't match after '&' (non-word char),
    so 'co' may remain after stripping other suffixes."""
    result = normalize_company_name("Acme GmbH & Co. KG")
    # GmbH and KG are stripped; '& co.' remains because \b doesn't match after &
    assert result == "acmeco"


@pytest.mark.unit
def test_normalize_empty_string():
    assert normalize_company_name("") == ""


@pytest.mark.unit
def test_normalize_special_chars_removed():
    """Ampersand, dots, hyphens stripped, but 'co.' suffix not matched due to \\b after &.
    The regex \\b& co\\.\\b does not match because & is a non-word character."""
    assert normalize_company_name("Personio & Co.") == "personioco"


@pytest.mark.unit
def test_normalize_already_clean():
    assert normalize_company_name("taxfix") == "taxfix"


@pytest.mark.unit
def test_normalize_preserves_digits():
    assert normalize_company_name("N26 GmbH") == "n26"


@pytest.mark.unit
def test_normalize_unicode_name():
    """Unicode chars that are not a-z0-9 are removed."""
    result = normalize_company_name("Müller AG")
    # ü is removed by the [^a-z0-9] regex
    assert result == "mller"


# ═══════════════════════════════════════════════════════════
# extract_country
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_extract_country_berlin():
    assert extract_country("Berlin, Germany") == "de"


@pytest.mark.unit
def test_extract_country_munich():
    assert extract_country("München") == "de"


@pytest.mark.unit
def test_extract_country_wien():
    assert extract_country("Wien, Österreich") == "at"


@pytest.mark.unit
def test_extract_country_zurich():
    assert extract_country("Zürich, Switzerland") == "ch"


@pytest.mark.unit
def test_extract_country_london_unknown():
    assert extract_country("London, UK") == "unknown"


@pytest.mark.unit
def test_extract_country_empty_string():
    assert extract_country("") == "unknown"


@pytest.mark.unit
def test_extract_country_none_raises():
    """None input causes AttributeError because .lower() is called on None."""
    with pytest.raises(AttributeError):
        extract_country(None)


@pytest.mark.unit
def test_extract_country_deutschland():
    assert extract_country("Deutschland") == "de"


@pytest.mark.unit
def test_extract_country_graz():
    assert extract_country("Graz") == "at"


@pytest.mark.unit
def test_extract_country_basel():
    assert extract_country("Basel") == "ch"


# ═══════════════════════════════════════════════════════════
# generate_dedup_key
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_generate_dedup_key_normal():
    job = {
        "company_name": "Taxfix GmbH",
        "role_function": "Finance",
        "location": "Berlin, Germany",
    }
    assert generate_dedup_key(job) == "taxfix_finance_de"


@pytest.mark.unit
def test_generate_dedup_key_missing_fields_defaults():
    """Missing fields use defaults: empty company, 'other' function, 'unknown' country."""
    job = {}
    key = generate_dedup_key(job)
    assert key == "_other_unknown"


@pytest.mark.unit
def test_generate_dedup_key_deterministic():
    job = {
        "company_name": "Personio GmbH",
        "role_function": "People",
        "location": "München",
    }
    assert generate_dedup_key(job) == generate_dedup_key(job)


@pytest.mark.unit
def test_generate_dedup_key_spaces_in_function_removed():
    job = {
        "company_name": "Acme",
        "role_function": "General Management",
        "location": "Berlin",
    }
    assert generate_dedup_key(job) == "acme_generalmanagement_de"


# ═══════════════════════════════════════════════════════════
# deduplicate_jobs
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_deduplicate_all_unique():
    jobs = [
        {"company_name": "A", "role_function": "Finance", "location": "Berlin"},
        {"company_name": "B", "role_function": "Engineering", "location": "München"},
    ]
    new_unique, updates = deduplicate_jobs(jobs)
    assert len(new_unique) == 2
    assert len(updates) == 0


@pytest.mark.unit
def test_deduplicate_batch_duplicate_keeps_higher_score():
    jobs = [
        {"company_name": "A", "role_function": "Finance", "location": "Berlin", "score": 10, "source": "jsearch"},
        {"company_name": "A", "role_function": "Finance", "location": "Berlin", "score": 50, "source": "arbeitnow"},
    ]
    new_unique, updates = deduplicate_jobs(jobs)
    assert len(new_unique) == 1
    assert new_unique[0]["score"] == 50


@pytest.mark.unit
def test_deduplicate_existing_keys_go_to_updates():
    jobs = [
        {"company_name": "A", "role_function": "Finance", "location": "Berlin"},
    ]
    existing_keys = {"a_finance_de"}
    new_unique, updates = deduplicate_jobs(jobs, existing_keys)
    assert len(new_unique) == 0
    assert len(updates) == 1


@pytest.mark.unit
def test_deduplicate_timestamps_added():
    jobs = [
        {"company_name": "A", "role_function": "Finance", "location": "Berlin"},
    ]
    new_unique, _ = deduplicate_jobs(jobs)
    assert new_unique[0]["first_seen"] is not None
    assert new_unique[0]["last_updated"] is not None
    assert new_unique[0]["status"] == "New"


@pytest.mark.unit
def test_deduplicate_empty_input():
    new_unique, updates = deduplicate_jobs([])
    assert new_unique == []
    assert updates == []


@pytest.mark.unit
def test_deduplicate_dedup_key_added_to_job():
    jobs = [
        {"company_name": "Taxfix", "role_function": "Finance", "location": "Berlin"},
    ]
    new_unique, _ = deduplicate_jobs(jobs)
    assert "dedup_key" in new_unique[0]
    assert new_unique[0]["dedup_key"] == "taxfix_finance_de"
