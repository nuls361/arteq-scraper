#!/usr/bin/env python3
"""
A-Line Email Writer — Claude-powered email generation with SDR persona.

Generates personalized outreach emails in German (Du-Form).
Sender name: Lena. CTA: 15-min call.
"""

import json
import logging
import os

import requests

logger = logging.getLogger("email_writer")

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Load SDR soul persona
_SDR_SOUL = None


def _get_sdr_soul():
    """Load agent_soul_sdr.md (cached)."""
    global _SDR_SOUL
    if _SDR_SOUL is not None:
        return _SDR_SOUL
    soul_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_soul_sdr.md")
    try:
        with open(soul_path, "r") as f:
            _SDR_SOUL = f.read()
    except FileNotFoundError:
        logger.warning("agent_soul_sdr.md not found, using minimal persona")
        _SDR_SOUL = "Du bist Lena, SDR bei A-Line. Du schreibst kurze, persönliche Emails auf Deutsch (Du-Form)."
    return _SDR_SOUL


def _claude_request(prompt, max_tokens=800, system=None):
    """Make a request to Claude API."""
    if not ANTHROPIC_KEY:
        return None
    try:
        body = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error(f"Claude API {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        return "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return None


def _clean_json_response(text):
    """Strip markdown fences and extract JSON."""
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1]
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1]
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    t = t.strip()
    if t and t[0] not in ('{', '['):
        idx = t.find('{')
        if idx >= 0:
            t = t[idx:]
    if t and t[0] == '{':
        depth = 0
        for i, c in enumerate(t):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            if depth == 0:
                t = t[:i + 1]
                break
    return t


def generate_initial_email(context):
    """Generate initial cold outreach email.

    Args:
        context: dict with keys:
            - company_name: str
            - contact_name: str
            - contact_title: str
            - role_title: str (the role they're hiring for)
            - company_description: str
            - signal: str (trigger/reason for outreach)
            - sourcing_brief: dict (from role enrichment)
            - hiring_manager_name: str
            - engagement_type: str (fractional/interim/full-time)

    Returns:
        dict with {subject, body} or None on failure.
    """
    soul = _get_sdr_soul()

    signal = context.get("signal", "")
    role_title = context.get("role_title", "")
    engagement = context.get("engagement_type", "")

    # Build angle
    if role_title:
        angle = f'Ihr sucht gerade einen {role_title}'
        if engagement in ("fractional", "interim"):
            angle += f' ({engagement.capitalize()})'
    elif signal:
        angle = signal
    else:
        angle = "Euer aktuelles Wachstum"

    prompt = f"""Write a cold outreach email from Lena at A-Line to {context.get('contact_name', 'the decision maker')}.

Context:
- Recipient: {context.get('contact_name', '?')} ({context.get('contact_title', '?')}) at {context.get('company_name', '?')}
- Trigger: {angle}
- Company: {context.get('company_description', 'N/A')}
- A-Line is a DACH-focused Fractional/Interim Executive placement firm

Rules (STRICT):
- Language: German, Du-Form
- Sender: Lena from A-Line
- Max 5-6 sentences
- ONE idea per email
- CTA: 15-Minuten-Gespräch next week
- Reference the specific trigger (role/signal) in the first sentence
- Sound human, not like a template
- No generic "I hope this finds you well" openings

Return ONLY a JSON object:
{{
  "subject": "email subject line (short, specific, no emojis)",
  "body": "email body (plain text, use \\n for line breaks)"
}}"""

    text = _claude_request(prompt, max_tokens=500, system=soul)
    if not text:
        return None

    try:
        return json.loads(_clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"Initial email JSON parse error: {e}")
        return None


def generate_followup_email(context, history):
    """Generate follow-up email with agent reasoning.

    Args:
        context: same as generate_initial_email
        history: list of previous outreach records (dicts with subject, body_html, status, created_at)

    Returns:
        dict with {subject, body, send, reasoning} or None.
        send: bool — whether the agent recommends sending this follow-up.
        reasoning: str — why or why not.
    """
    soul = _get_sdr_soul()

    # Build history summary
    history_text = ""
    for i, msg in enumerate(history, 1):
        status = msg.get("status", "sent")
        date = msg.get("created_at", "?")[:10]
        history_text += f"\nEmail {i} ({date}, status: {status}):\n"
        history_text += f"Subject: {msg.get('subject', '?')}\n"
        body = msg.get("body_html", msg.get("raw_text", ""))
        # Strip HTML tags for readability
        import re
        clean = re.sub(r'<[^>]+>', '', body)
        history_text += f"Body: {clean[:300]}\n"

    step = len(history) + 1

    prompt = f"""You are the A-Line SDR agent (Lena). Decide whether to send follow-up #{step} and write it if yes.

Recipient: {context.get('contact_name', '?')} ({context.get('contact_title', '?')}) at {context.get('company_name', '?')}
Original trigger: {context.get('role_title', context.get('signal', '?'))}

Previous emails:{history_text}

Follow-up strategy:
- Follow-up 1 (after 48h): New angle, new signal, or helpful content
- Follow-up 2 (after 5 days): Short check-in with concrete value
- Follow-up 3 (after 10 days): Last chance — "Kurze Frage" format
- After 3 follow-ups: STOP. Do not send.

Rules:
- Language: German, Du-Form
- Max 2-3 sentences
- New angle each time — never repeat "wollte nur nochmal nachfragen"
- If this is follow-up 4+: set send=false

Return ONLY a JSON object:
{{
  "send": true/false,
  "reasoning": "why you recommend sending or not",
  "subject": "Re: [original subject]",
  "body": "follow-up body (plain text)"
}}"""

    text = _claude_request(prompt, max_tokens=500, system=soul)
    if not text:
        return None

    try:
        return json.loads(_clean_json_response(text))
    except json.JSONDecodeError as e:
        logger.error(f"Follow-up email JSON parse error: {e}")
        return None
