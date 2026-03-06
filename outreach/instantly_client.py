#!/usr/bin/env python3
"""
Instantly.ai API v2 wrapper.

Handles lead management for email outreach campaigns.
All functions use INSTANTLY_API_KEY env var.
Retry with exponential backoff on failures (max 3 attempts).
"""

import logging
import os
import time

import httpx

logger = logging.getLogger("instantly_client")

INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "")
BASE_URL = "https://api.instantly.ai/api/v2"


def _headers():
    return {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json",
    }


def _request(method, path, json=None, params=None, max_retries=3):
    """Make a request to Instantly API with exponential backoff."""
    url = f"{BASE_URL}{path}"
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.request(
                    method,
                    url,
                    headers=_headers(),
                    json=json,
                    params=params,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"Instantly rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    logger.error(f"Instantly {method} {path}: {resp.status_code} — {resp.text[:200]}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                logger.warning(f"Instantly timeout on {path}, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(2 ** attempt)
            else:
                raise
    return None


def create_lead(contact, campaign_id):
    """Add a lead to an Instantly campaign.

    Args:
        contact: dict with email, first_name, last_name, company_name, etc.
        campaign_id: Instantly campaign UUID.

    Returns:
        Lead data from Instantly.
    """
    if not INSTANTLY_API_KEY:
        raise ValueError("INSTANTLY_API_KEY not set")

    payload = {
        "campaign_id": campaign_id,
        "email": contact["email"],
        "first_name": contact.get("first_name", ""),
        "last_name": contact.get("last_name", ""),
        "company_name": contact.get("company_name", ""),
    }

    # Pass custom variables for email personalization
    custom_vars = {}
    if contact.get("title"):
        custom_vars["title"] = contact["title"]
    if contact.get("role_title"):
        custom_vars["role_title"] = contact["role_title"]
    if contact.get("company_name"):
        custom_vars["company_name"] = contact["company_name"]
    if custom_vars:
        payload["custom_variables"] = custom_vars

    result = _request("POST", "/leads", json=payload)
    logger.info(f"Lead created in Instantly: {contact['email']}")
    return result


def get_lead_status(email):
    """Get lead status by email address.

    Returns:
        Lead data including status, opens, replies.
    """
    if not INSTANTLY_API_KEY:
        raise ValueError("INSTANTLY_API_KEY not set")

    result = _request("GET", "/leads", params={"email": email})
    return result


def list_replies(campaign_id, since=None):
    """List replies for a campaign.

    Args:
        campaign_id: Instantly campaign UUID.
        since: ISO timestamp to filter replies after this date.

    Returns:
        List of reply objects.
    """
    if not INSTANTLY_API_KEY:
        raise ValueError("INSTANTLY_API_KEY not set")

    params = {"campaign_id": campaign_id}
    if since:
        params["since"] = since

    result = _request("GET", "/emails/replies", params=params)
    return result


def pause_lead(email, campaign_id=None):
    """Pause a lead (stop sending emails).

    Args:
        email: Lead email address.
        campaign_id: Optional campaign ID.

    Returns:
        Updated lead data.
    """
    if not INSTANTLY_API_KEY:
        raise ValueError("INSTANTLY_API_KEY not set")

    payload = {"email": email, "pause": True}
    if campaign_id:
        payload["campaign_id"] = campaign_id

    result = _request("PATCH", "/leads", json=payload)
    logger.info(f"Lead paused in Instantly: {email}")
    return result
