"""Short WhatsApp alerts to the owner's own number through CallMeBot, a free outside service for
personal use: CALLMEBOT_PHONE (with the country code) and CALLMEBOT_APIKEY. It sends text only and
cannot read replies, so Telegram stays the main channel. Its failure never stops a run.

The text passes through CallMeBot's servers: counts and bot names only, no customer data or log lines.
"""
from __future__ import annotations

import logging

import requests

from ..core.config import env

log = logging.getLogger("ultron")
API = "https://api.callmebot.com/whatsapp.php"
MAX_LEN = 1000


def send(text: str) -> bool:
    """Send one message; False when it is not set up or was not sent. The key is never logged."""
    phone, key = env("CALLMEBOT_PHONE"), env("CALLMEBOT_APIKEY")
    if not phone or not key:
        return False
    if len(text) > MAX_LEN:
        text = text[:MAX_LEN - 20].rstrip() + "\n... (see Telegram)"
    try:
        r = requests.get(API, params={"phone": phone, "text": text, "apikey": key}, timeout=30)
    except requests.RequestException as exc:
        log.warning("WhatsApp alert not sent: %s", type(exc).__name__)
        return False
    if not r.ok or "invalid" in r.text.lower():
        log.warning("WhatsApp alert not sent: HTTP %s", r.status_code)
        return False
    return True
