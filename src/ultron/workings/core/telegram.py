"""Telegram notifications (Bot API) for every bot: text, photos and files.

TELEGRAM_CHAT_ID may hold several comma-separated chats. Long messages are cut
on line boundaries and any HTML tag still open at a cut (<pre>, <b>, <i> ...)
is closed and reopened in the next part, so Telegram never rejects a part for
broken HTML. If Telegram still refuses the HTML, the part is sent as plain text
instead of being lost.

A report with long lists (AWBs, orders, SKUs) is built as blocks: text and Listing. When the
whole report fits in one message the lists go inline; otherwise the message keeps each list's
title and count and every row goes to one attached Excel, a sheet per list (send_report).
<pre> tables stay within PHONE_WIDTH characters a line so they do not wrap on a phone.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ultron.core import http

from ultron.integrations.telegram import TAG, _plain, esc, md, split_html  # noqa: F401 - one place

log = logging.getLogger(__name__)
MAX_LEN = 4000  # Telegram hard limit is 4096
API = "https://api.telegram.org/bot{token}/{method}"
PHONE_WIDTH = 28  # monospace characters a <pre> line shows on a phone without wrapping


def _config() -> tuple[str, list[str]]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    return token, chats


def _post(token: str, method: str, tries: int = 3, **kw) -> "http.Response | None":
    """The one Bot API sender, shared with the agent (ultron.integrations.telegram._post: tries again on a
    dropped connection or a timeout, waits 5, 10 s, rewinds files; None when not sent)."""
    from ultron.integrations.telegram import _post as post
    return post(token, method, tries, **kw)


def send(text: str) -> bool:
    token, chats = _config()
    if not token or not chats:
        log.warning("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) - message printed instead")
        print(text)
        return False
    ok = True
    for chat in chats:
        for part in split_html(text):
            r = _post(token, "sendMessage", json={"chat_id": chat, "text": part, "parse_mode": "HTML",
                                                  "disable_web_page_preview": True})
            if r is not None and r.status_code == 400 and "parse" in r.text.lower():
                log.warning("Telegram refused the HTML (%s); sending as plain text", r.text[:200])
                r = _post(token, "sendMessage", json={"chat_id": chat, "text": _plain(part)[:4096],
                                                      "disable_web_page_preview": True})
            if not http.ok(r):
                ok = False
                if r is not None:
                    log.error("Telegram send to %s failed: %s %s", chat, r.status_code, r.text[:300])
    return ok


def send_file(path, caption: str = "", as_document: bool = False) -> bool:
    """Send a file to every chat: an image as a photo (inline preview) or any file as a document."""
    token, chats = _config()
    if not token or not chats:
        log.warning("Telegram not configured - %s not sent", path)
        return False
    method, field = ("sendDocument", "document") if as_document else ("sendPhoto", "photo")
    caption = split_html(caption, 1000)[0] if caption else ""
    ok = True
    for chat in chats:
        try:
            with open(path, "rb") as fh:
                r = _post(token, method, data={"chat_id": chat, "caption": caption, "parse_mode": "HTML"},
                          files={field: (os.path.basename(str(path)), fh)})
        except OSError as exc:
            log.error("Telegram %s: cannot read %s: %s", method, path, exc)
            return False
        if not http.ok(r):
            ok = False
            if r is not None:
                log.error("Telegram %s to %s failed: %s %s", method, chat, r.status_code, r.text[:300])
    return ok


def send_document(path, caption: str = "") -> bool:
    return send_file(path, caption, as_document=True)


# ------------------------------------------------------------------ reports with long lists

@dataclass
class Listing:
    """A list inside a report: `lines` (HTML) inline when the report fits in one message, otherwise
    `rows` (column -> value) on the Excel sheet `sheet`. `title` stays in the message either way."""
    title: str
    lines: list[str]
    rows: list[dict] = field(default_factory=list)
    sheet: str = "List"


def render(report: list, inline: bool = True) -> str:
    """The report's text: lists inline, or only their titles with a pointer to the Excel."""
    out = []
    for block in report:
        if not isinstance(block, Listing):
            out.append(block)
        elif inline or not block.rows:
            out += [block.title, *block.lines]
        else:
            out += [block.title, f"📎 all {len(block.rows)} in the Excel below (sheet {esc(block.sheet)})"]
    return "\n".join(out)


def fits(report: list) -> bool:
    return len(render(report)) <= MAX_LEN


def write_xlsx(report: list, path) -> Path | None:
    """One sheet per list with rows: bold frozen header, columns as wide as their text (workings/core/xlsx.py)."""
    from .xlsx import write_sheets
    lists = [b for b in report if isinstance(b, Listing) and b.rows]
    if not lists:
        return None
    sheets = [(block.sheet or "List", list(dict.fromkeys(k for r in block.rows for k in r)), block.rows)
              for block in lists]                    # same names allowed: write_sheets makes them unique
    return write_sheets(path, sheets, bold_header=True, freeze=True, auto_width=True)


def send_report(report: list, name: str, dry: bool = False, excel: bool = False) -> bool:
    """Send a report of text and Listing blocks: one message with the lists inline when it fits,
    otherwise the message with the lists' titles plus an Excel (name_YYYY-MM-DD_HHMM.xlsx) of every row.
    excel: the Excel goes out even when the lists fit inline (the rows carry more columns than the
    inline table). dry: print the message and keep the Excel locally instead of sending."""
    inline = fits(report)
    if inline and not excel:
        text = render(report)
        print(text) if dry else None
        return True if dry else send(text)
    text = render(report, inline=inline)
    path = write_xlsx(report, Path(tempfile.mkdtemp(prefix="tg_")) / f"{name}_{datetime.now():%Y-%m-%d_%H%M}.xlsx")
    if dry:
        print(text)
        print(f"[Excel: {path}]")
        return True
    ok = send(text)
    if path:
        lists = [b for b in report if isinstance(b, Listing) and b.rows]
        caption = f"📎 <b>{esc(name.replace('_', ' '))}</b> · " + " · ".join(f"{esc(b.sheet)} {len(b.rows)}" for b in lists)
        ok = send_document(path, caption) and ok
    return ok
