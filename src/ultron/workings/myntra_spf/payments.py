"""Myntra payments of one account, the way the QUIRY "Payment and UTR export" tool gets them in Chrome
(CHROME EXTENSION/QUIRY JS, tools/myntra-payment-export.js), with the bot's saved session.

Every payout (UTR) of the window from Payments > Payment Summary, then each payout's line-level
CSV from its signed utrDetailsLink. The file has the QUIRY export's columns (paymentDate, utrNumber,
paymentAmount, ..., detailSource, detailStatus, then the line columns Order_Type, NOD_Comment,
order_line_id, Settled_Amount, Logistics_Commission, ...), so the engine reads it as a PAYMENT
report like a hand-dropped export.

Since Sep 2026 Myntra issues many detail links with the blob path encoded once too often: they
answer 404 BlobNotFound. As in QUIRY, a few such links are probed (as issued and re-encoded); when
both fail that class is skipped and the last-payment breakup API is used where an advice id
exists. A payout with no line rows is still written, with the reason in detailStatus.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

log = logging.getLogger("bindal.myntra_spf.payments")

PAY_COLS = ["paymentDate", "paymentMethod", "utrNumber", "paymentAmount", "yearMonth", "adviceId",
            "detailSource", "detailStatus"]
BROKEN = "no detail file (Myntra link defect)"


def shape(link: str | None) -> str:
    """legacy (works), encoded (the blob path encoded once too often: 404s) or none."""
    if not link:
        return "none"
    path = link.split("?")[0]
    return "encoded" if re.search(r"%2Futr_no%3D|%2Fmonthly%2F|%2Fprod%2F", path, re.I) else "legacy"


def repair(link: str) -> str | None:
    """An encoded link rebuilt in the shape Azure stores the blob under (utr_no escaped as %252F)."""
    path, _, qs = link.partition("?")
    u = urlsplit(path)
    m = re.match(r"^(.*/utr_no=)(.*)(/part-[^/]*)$", unquote(u.path))
    if not m:
        return None
    utr = unquote(m.group(2)).replace("%", "%25").replace("/", "%252F")
    return f"{u.scheme}://{u.netloc}{m.group(1)}{utr}{m.group(3)}" + (f"?{qs}" if qs else "")


def blob(url: str) -> tuple[list[dict] | None, str]:
    """(rows, '') or (None, error code). Transient errors are tried 3 times, a 4xx once."""
    code = ""
    for _ in range(3):
        try:
            r = requests.get(url, timeout=120)
        except requests.RequestException as exc:
            code = str(exc)[:80]
            continue
        if r.ok:
            text = r.content.decode("utf-8-sig")
            return [row for row in csv.DictReader(io.StringIO(text)) if any(row.values())], ""
        code = (re.search(r"<Code>(.*?)</Code>", r.text) or [None, f"HTTP {r.status_code}"])[1]
        if r.status_code in (400, 401, 403, 404, 410):
            break
    return None, code


def account_payments(portal, start: date, end: date, dest: Path) -> dict:
    """The account's payouts start..end with their line rows into dest (CSV). Returns counts:
    payouts, rows, without_lines and the amount of the payouts without line rows."""
    pays = portal.payment_history(start, end)
    mode = "none"                    # how the encoded links behave this run
    for p in [p for p in pays if shape(p.get("utrDetailsLink")) == "encoded"][:3]:
        if blob(p["utrDetailsLink"])[0] is not None:
            mode = "direct"
            break
        fixed = repair(p["utrDetailsLink"])
        if fixed and blob(fixed)[0] is not None:
            mode = "repair"
            break
        mode = "skip"

    def detail(p):
        link = p.get("utrDetailsLink")
        s = shape(link)
        if s == "none":
            return None, "no detail link on this payment", ""
        if s == "encoded" and mode == "skip":
            return None, BROKEN, ""
        rows, err = blob((repair(link) or link) if s == "encoded" and mode == "repair" else link)
        if rows is None:
            return None, (BROKEN if err == "BlobNotFound" else err), ""
        return rows, ("ok" if rows else "empty"), "blob"

    with ThreadPoolExecutor(5) as ex:
        details = list(ex.map(detail, pays))
    if any(d[0] is None for d in details):
        advices = portal.payment_advices()       # the API breakup where the dashboard still has it
        for i, d in enumerate(details):
            ids = advices.get(pays[i].get("utrNumber")) if d[0] is None else None
            rows = [r for a in ids or [] for r in portal.payment_breakup(a)]
            if rows:
                details[i] = (rows, "ok", "api")

    rows, cols = [], list(PAY_COLS)
    for p, (lines, status, src) in zip(pays, details):
        base = {"paymentDate": p.get("paymentDate"), "paymentMethod": p.get("paymentMethod"),
                "utrNumber": p.get("utrNumber"), "paymentAmount": p.get("amount"),
                "yearMonth": p.get("yearMonth"), "adviceId": p.get("adviceId") or "",
                "detailSource": src, "detailStatus": status}
        for line in lines or [{}]:
            cols += [c for c in line if c not in cols]
            rows.append({**base, **line})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    missing = [p for p, d in zip(pays, details) if not d[0]]
    out = {"payouts": len(pays), "rows": len(rows), "without_lines": len(missing),
           "missing_amount": round(sum(float(p.get("amount") or 0) for p in missing)), "mode": mode}
    log.info("payments %s..%s: %s -> %s", start, end, out, dest.name)
    return out
