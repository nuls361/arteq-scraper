#!/usr/bin/env python3
"""
Arteq Healthcheck — Monitor system health 4x daily.

Checks:
  1. Supabase API reachable + data freshness
  2. Anthropic API key valid
  3. Apollo API key valid + credit status
  4. Resend API key valid
  5. Data freshness (last role, signal, company created)
  6. Orchestrator last run

Sends alert email via Resend ONLY if something is wrong.

Usage: python healthcheck.py
Schedule: Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("healthcheck")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "niels@arteq.app")


def check_supabase():
    """Check Supabase connectivity."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"status": "error", "message": "SUPABASE_URL or SUPABASE_KEY not set"}
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/company?select=id&limit=1",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "ok"}
        return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:100]}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_anthropic():
    """Check Anthropic API key validity."""
    if not ANTHROPIC_KEY:
        return {"status": "warn", "message": "ANTHROPIC_API_KEY not set"}
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "ok"}
        if resp.status_code == 401:
            return {"status": "error", "message": "Invalid API key"}
        if resp.status_code == 429:
            return {"status": "warn", "message": "Rate limited"}
        return {"status": "warn", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_apollo():
    """Check Apollo API key validity."""
    if not APOLLO_API_KEY:
        return {"status": "warn", "message": "APOLLO_API_KEY not set"}
    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": APOLLO_API_KEY,
            },
            json={"q_organization_name": "test", "per_page": 1, "page": 1},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "ok"}
        if resp.status_code == 401:
            return {"status": "error", "message": "Invalid API key"}
        return {"status": "warn", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_resend():
    """Check Resend API key validity."""
    if not RESEND_API_KEY:
        return {"status": "warn", "message": "RESEND_API_KEY not set"}
    try:
        resp = requests.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "ok"}
        if resp.status_code == 401:
            return {"status": "error", "message": "Invalid API key"}
        return {"status": "warn", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_data_freshness():
    """Check when data was last updated."""
    if not SUPABASE_URL:
        return {"status": "error", "message": "No Supabase"}

    issues = []
    now = datetime.now(timezone.utc)

    checks = [
        ("role", "created_at", 48, "Keine neuen Roles seit 48h"),
        ("company", "created_at", 72, "Keine neuen Companies seit 72h"),
    ]

    for table, col, max_hours, msg in checks:
        try:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table}?select={col}&order={col}.desc&limit=1",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    last = datetime.fromisoformat(data[0][col].replace("Z", "+00:00"))
                    hours_ago = (now - last).total_seconds() / 3600
                    if hours_ago > max_hours:
                        issues.append(f"{msg} (letzte: vor {int(hours_ago)}h)")
        except Exception:
            issues.append(f"Konnte {table} nicht prüfen")

    # Check orchestrator last run
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/agent_log?select=created_at&order=created_at.desc&limit=1",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data:
                last = datetime.fromisoformat(data[0]["created_at"].replace("Z", "+00:00"))
                hours_ago = (now - last).total_seconds() / 3600
                if hours_ago > 36:
                    issues.append(f"Orchestrator letzter Run vor {int(hours_ago)}h (>36h)")
            else:
                issues.append("Orchestrator hat noch nie gelaufen")
    except Exception:
        pass  # Table might not exist yet

    if issues:
        return {"status": "warn", "message": "; ".join(issues)}
    return {"status": "ok"}


def check_apollo_budget():
    """Check Apollo credit budget status."""
    if not SUPABASE_URL or not APOLLO_API_KEY:
        return {"status": "ok", "message": "N/A"}

    try:
        month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/apollo_credit_ledger?select=credits&created_at=gte.{month_start}T00:00:00Z",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            monthly_used = sum(r["credits"] for r in (data or []))
            if monthly_used > 400:  # >80% of default 500 budget
                return {"status": "warn", "message": f"Apollo: {monthly_used}/500 Credits diesen Monat (>80%)"}
    except Exception:
        pass

    return {"status": "ok"}


def send_alert(checks):
    """Send alert email if any check has errors."""
    if not RESEND_API_KEY:
        logger.error("Cannot send alert — no RESEND_API_KEY")
        return

    errors = [(name, c) for name, c in checks.items() if c["status"] == "error"]
    warnings = [(name, c) for name, c in checks.items() if c["status"] == "warn"]

    if not errors and not warnings:
        return

    severity = "ERROR" if errors else "WARNING"

    html = f"""<div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;padding:20px">
    <h2 style="color:{'#C13030' if errors else '#AD5700'};margin:0 0 16px">Arteq System {severity}</h2>
    <p style="color:#6B6F76;font-size:13px;margin:0 0 20px">{datetime.now().strftime('%d.%m.%Y %H:%M')} UTC</p>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="background:#F7F7F8"><th style="text-align:left;padding:8px">Check</th><th style="text-align:left;padding:8px">Status</th><th style="text-align:left;padding:8px">Details</th></tr>"""

    for name, c in checks.items():
        color = {"ok": "#30A46C", "warn": "#AD5700", "error": "#C13030"}[c["status"]]
        icon = {"ok": "✓", "warn": "⚠", "error": "✗"}[c["status"]]
        html += f"""<tr style="border-bottom:1px solid #EBEBED">
        <td style="padding:8px;font-weight:500">{name}</td>
        <td style="padding:8px;color:{color};font-weight:600">{icon} {c['status'].upper()}</td>
        <td style="padding:8px;color:#6B6F76">{c.get('message', '')}</td></tr>"""

    html += "</table></div>"

    try:
        import resend
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": "Arteq System <onboarding@resend.dev>",
            "to": [ALERT_EMAIL],
            "subject": f"⚠ Arteq {severity}: {', '.join(name for name, _ in (errors or warnings))}",
            "html": html,
        })
        logger.info(f"  Alert sent to {ALERT_EMAIL}")
    except Exception as e:
        logger.error(f"  Alert send error: {e}")


def run_healthcheck():
    """Run all health checks and return results dict."""
    logger.info("\n💓 ARTEQ HEALTHCHECK")

    checks = {
        "Supabase": check_supabase(),
        "Anthropic": check_anthropic(),
        "Apollo": check_apollo(),
        "Resend": check_resend(),
        "Data Freshness": check_data_freshness(),
        "Apollo Budget": check_apollo_budget(),
    }

    all_ok = True
    for name, result in checks.items():
        icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}[result["status"]]
        msg = f"  {icon} {name}: {result['status'].upper()}"
        if result.get("message"):
            msg += f" — {result['message']}"
        logger.info(msg)
        if result["status"] != "ok":
            all_ok = False

    if not all_ok:
        send_alert(checks)

    return checks, all_ok


def main():
    checks, all_ok = run_healthcheck()
    if not all_ok:
        sys.exit(1)
    logger.info("\n  All systems operational ✓\n")


if __name__ == "__main__":
    main()
