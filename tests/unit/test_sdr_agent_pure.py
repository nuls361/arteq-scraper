"""
Unit tests for pipeline/sdr_agent.py — build_outreach_prompt function.
"""

import pytest
from pipeline.sdr_agent import build_outreach_prompt


def _make_opp(pipeline_type="role", notes="Hot role: CFO — urgent"):
    return {"pipeline_type": pipeline_type, "notes": notes}


def _make_company(name="Taxfix", industry="FinTech", funding_stage="Series B"):
    return {"name": name, "industry": industry, "funding_stage": funding_stage}


def _make_dm(name="Max Mustermann", title="CEO", email="max@taxfix.com"):
    return {"name": name, "title": title, "email": email}


def _make_intel(roles=None, signals=None):
    return {
        "roles": roles or [],
        "signals": signals or [],
        "contacts": [],
    }


def _make_persona():
    return {
        "dos": ["Be concise", "Mention A-Line"],
        "donts": ["No spam", "No buzzwords"],
        "value_props": ["Fast placement", "DACH network"],
        "signature": "Beste Gruesse,\nNiels",
    }


# ═══════════════════════════════════════════════════════════
# build_outreach_prompt — role pipeline
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_role_pipeline_contains_wir_haben_gesehen():
    prompt = build_outreach_prompt(
        _make_opp(pipeline_type="role"),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Wir haben gesehen" in prompt


@pytest.mark.unit
def test_role_pipeline_contains_role_title():
    prompt = build_outreach_prompt(
        _make_opp(pipeline_type="role", notes="Hot role: CFO — urgent"),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "CFO" in prompt


# ═══════════════════════════════════════════════════════════
# build_outreach_prompt — company pipeline (signal)
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_company_pipeline_contains_signal_messaging():
    prompt = build_outreach_prompt(
        _make_opp(pipeline_type="company", notes="Signal: Series B funding"),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Signal" in prompt


@pytest.mark.unit
def test_company_pipeline_does_not_contain_wir_haben_gesehen():
    prompt = build_outreach_prompt(
        _make_opp(pipeline_type="company", notes="Signal: Funding"),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Wir haben gesehen" not in prompt


# ═══════════════════════════════════════════════════════════
# build_outreach_prompt — DM name / first_name
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_dm_name_included():
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(name="Anna Schmidt"),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Anna Schmidt" in prompt


@pytest.mark.unit
def test_first_name_extracted():
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(name="Anna Schmidt"),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Hi Anna" in prompt


# ═══════════════════════════════════════════════════════════
# build_outreach_prompt — intel (roles / signals)
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_intel_roles_included():
    roles = [{"title": "Interim CFO", "engagement_type": "Interim"}]
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(),
        _make_intel(roles=roles),
        "",
        _make_persona(),
    )
    assert "Interim CFO" in prompt


@pytest.mark.unit
def test_intel_signals_included():
    signals = [{"type": "funding_round", "title": "Series B at Taxfix"}]
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(),
        _make_intel(signals=signals),
        "",
        _make_persona(),
    )
    assert "funding_round" in prompt


# ═══════════════════════════════════════════════════════════
# build_outreach_prompt — persona
# ═══════════════════════════════════════════════════════════

@pytest.mark.unit
def test_persona_dos_included():
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Be concise" in prompt


@pytest.mark.unit
def test_persona_donts_included():
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "No spam" in prompt


@pytest.mark.unit
def test_persona_signature_included():
    prompt = build_outreach_prompt(
        _make_opp(),
        _make_company(),
        _make_dm(),
        _make_intel(),
        "",
        _make_persona(),
    )
    assert "Niels" in prompt
