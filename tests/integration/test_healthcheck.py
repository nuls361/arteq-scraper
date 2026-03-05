"""Integration tests for healthcheck.py business flows."""

import json
from unittest.mock import MagicMock

import pytest

import healthcheck


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_http_response(json_data=None, text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.text = text or json.dumps(json_data or [])
    resp.headers = {}
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# check_supabase
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_check_supabase_ok(mocker, monkeypatch):
    """Supabase check returns OK on 200 response."""
    monkeypatch.setattr(healthcheck, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(healthcheck, "SUPABASE_KEY", "test-key")

    mocker.patch("healthcheck.requests.get", return_value=_make_http_response(status_code=200))

    result = healthcheck.check_supabase()
    assert result["status"] == "ok"


@pytest.mark.integration
def test_check_supabase_error_on_missing_env(monkeypatch):
    """Supabase check returns error when env vars missing."""
    monkeypatch.setattr(healthcheck, "SUPABASE_URL", "")
    monkeypatch.setattr(healthcheck, "SUPABASE_KEY", "")

    result = healthcheck.check_supabase()
    assert result["status"] == "error"
    assert "not set" in result["message"]


# ═══════════════════════════════════════════════════════════════════════════════
# check_anthropic
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_check_anthropic_ok(mocker, monkeypatch):
    """Anthropic check returns OK on 200."""
    monkeypatch.setattr(healthcheck, "ANTHROPIC_KEY", "test-key")

    mocker.patch("healthcheck.requests.post",
                 return_value=_make_http_response(
                     {"content": [{"type": "text", "text": "ok"}]}, status_code=200))

    result = healthcheck.check_anthropic()
    assert result["status"] == "ok"


@pytest.mark.integration
def test_check_anthropic_warn_on_429(mocker, monkeypatch):
    """Anthropic check returns warn on rate limit."""
    monkeypatch.setattr(healthcheck, "ANTHROPIC_KEY", "test-key")

    mocker.patch("healthcheck.requests.post",
                 return_value=_make_http_response(status_code=429))

    result = healthcheck.check_anthropic()
    assert result["status"] == "warn"


@pytest.mark.integration
def test_check_anthropic_error_on_401(mocker, monkeypatch):
    """Anthropic check returns error on invalid key."""
    monkeypatch.setattr(healthcheck, "ANTHROPIC_KEY", "bad-key")

    mocker.patch("healthcheck.requests.post",
                 return_value=_make_http_response(status_code=401))

    result = healthcheck.check_anthropic()
    assert result["status"] == "error"
    assert "Invalid" in result["message"]


# ═══════════════════════════════════════════════════════════════════════════════
# check_data_freshness
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_check_data_freshness_ok_when_fresh(mocker, monkeypatch):
    """Data freshness returns OK when data is recent."""
    monkeypatch.setattr(healthcheck, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(healthcheck, "SUPABASE_KEY", "test-key")

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    mocker.patch("healthcheck.requests.get",
                 return_value=_make_http_response([{"created_at": now}]))

    result = healthcheck.check_data_freshness()
    assert result["status"] == "ok"


@pytest.mark.integration
def test_check_data_freshness_warn_when_stale(mocker, monkeypatch):
    """Data freshness returns warn when data is old."""
    monkeypatch.setattr(healthcheck, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(healthcheck, "SUPABASE_KEY", "test-key")

    from datetime import datetime, timezone, timedelta

    stale = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()

    mocker.patch("healthcheck.requests.get",
                 return_value=_make_http_response([{"created_at": stale}]))

    result = healthcheck.check_data_freshness()
    assert result["status"] == "warn"


# ═══════════════════════════════════════════════════════════════════════════════
# run_healthcheck
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_run_healthcheck_aggregates_checks(mocker, monkeypatch):
    """run_healthcheck should call all checks and aggregate results."""
    monkeypatch.setattr(healthcheck, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(healthcheck, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(healthcheck, "ANTHROPIC_KEY", "test-key")
    monkeypatch.setattr(healthcheck, "APOLLO_API_KEY", "test-key")
    monkeypatch.setattr(healthcheck, "RESEND_API_KEY", "test-key")

    mocker.patch("healthcheck.check_supabase", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_anthropic", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_apollo", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_resend", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_data_freshness", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_apollo_budget", return_value={"status": "ok"})
    mocker.patch("healthcheck.send_alert")

    checks, all_ok = healthcheck.run_healthcheck()
    assert all_ok is True
    assert "Supabase" in checks
    assert "Anthropic" in checks


@pytest.mark.integration
def test_run_healthcheck_sends_alert_on_failure(mocker, monkeypatch):
    """run_healthcheck should send alert when any check fails."""
    monkeypatch.setattr(healthcheck, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(healthcheck, "SUPABASE_KEY", "test-key")

    mocker.patch("healthcheck.check_supabase", return_value={"status": "error", "message": "DB down"})
    mocker.patch("healthcheck.check_anthropic", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_apollo", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_resend", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_data_freshness", return_value={"status": "ok"})
    mocker.patch("healthcheck.check_apollo_budget", return_value={"status": "ok"})
    mock_alert = mocker.patch("healthcheck.send_alert")

    checks, all_ok = healthcheck.run_healthcheck()
    assert all_ok is False
    mock_alert.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
def test_main_exits_1_on_failure(mocker, monkeypatch):
    """main() should sys.exit(1) when any check fails."""
    mocker.patch("healthcheck.run_healthcheck", return_value=(
        {"Supabase": {"status": "error", "message": "fail"}},
        False,
    ))

    with pytest.raises(SystemExit) as exc_info:
        healthcheck.main()
    assert exc_info.value.code == 1


@pytest.mark.integration
def test_main_exits_cleanly_on_success(mocker, monkeypatch):
    """main() should not exit when all checks pass."""
    mocker.patch("healthcheck.run_healthcheck", return_value=(
        {"Supabase": {"status": "ok"}},
        True,
    ))

    # Should not raise
    healthcheck.main()
