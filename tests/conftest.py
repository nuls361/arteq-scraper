"""
Global test configuration.

Sets dummy environment variables so modules can be imported without real keys.
Module-level constants (e.g. SUPABASE_URL = os.getenv(...)) are evaluated at import time.
Unit tests don't need these; integration/E2E tests use monkeypatch.setattr() on the module.
"""

import os
import pytest


@pytest.fixture(autouse=True)
def _set_dummy_env(monkeypatch):
    """Set dummy env vars so every module can be imported safely."""
    env_vars = {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_KEY": "test-key-1234",
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "JSEARCH_API_KEY": "test-jsearch-key",
        "APOLLO_API_KEY": "test-apollo-key",
        "PDL_API_KEY": "test-pdl-key",
        "RESEND_API_KEY": "test-resend-key",
        "ALERT_EMAIL": "test@example.com",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
