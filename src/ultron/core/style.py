"""How Ultron writes for the owner, who reads it on a phone: short lines read at a glance.

MOBILE goes at the end of every prompt whose answer reaches Telegram; tidy() cleans the model's
answer before it is sent (odd dashes and spaces, markdown marks, empty lines).
"""
from __future__ import annotations

import re

MOBILE = """

How to write it (the owner reads it on a phone, at a glance):
- One fact per line, at most about 60 characters. No long sentences, no paragraphs.
- Start each line with one emoji that says what it is: 📉 fell, 📈 grew, ⚠️ a problem, ✅ fine,
  👉 something to do.
- Name first, then the numbers, short and exact: "Flipkart 407 → 207 (-49%)", "Cancels 63 (8%)".
- Say "yesterday", "today", "last week" instead of dates when that is clear.
- End with one or two 👉 lines: what to check or do today.
- Simple, everyday English words. No markdown (#, **, tables), no greeting, no sign-off."""

_DASHES = re.compile("[‐‑‒–—−]")
_SPACES = re.compile("[    ]")


def tidy(text: str) -> str:
    """The model's answer as plain phone text: ordinary dashes and spaces, no ** / # marks, no
    empty lines in a row, no spaces at line ends."""
    text = _SPACES.sub(" ", _DASHES.sub("-", text or ""))
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    out = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()
