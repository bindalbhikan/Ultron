"""AJIO "Seller Pickup Issue" form (Microsoft Forms), sent after the pickup tickets: one response a
day per courier whose parcels are still not picked up past their pickup deadline.

The form: seller name, POB (last six digits), contact, issue = "Pick-up not done", the courier
(a check box list) and the date from when the pickup is not done. The answers go to the form's
own submit call (the one its page makes: POST .../forms('<id>')/responses), each answer
{questionId, answer1}: text as is, a single choice its text, a check box list a JSON list, a date
yyyy-MM-dd. AJIO_PICKUP_FORM=1 sends; otherwise the responses are only listed (dry run).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import pandas as pd
import requests

from ..core.config import env

log = logging.getLogger("bindal.ajio_tat.form")

FORM_URL = ("https://forms.cloud.microsoft/formapi/api/fe1d95a9-4ce1-41a5-8eab-6dd43aa26d9f/users/"
            "645a1c2c-9fd1-42d2-b186-680be4e3cef7/forms('qZUd_uFMpUGOq23UOqJtnywcWmTRn9JCsYZoC-TjzvdUREtLUFZBNjZUSTZHTEY1Wk1VOEJORTYwOS4u')/responses")
Q_SELLER = "rc1b468078f4f4140b22c49c59ba7c3a0"
Q_POB = "r5976724aaa7b408f8c0349da4dc00978"
Q_CONTACT = "r4bc9978791fb4186ac85eda9a2f08a37"
Q_ISSUE = "rbc5605104cdf4c9cbe25b9f05d97d9ee"        # Pick-up not done / Partial Handover
Q_COURIER = "rb9a3c53db95a4585913e8bad57436bbd"      # the courier list on the "Pick-up not done" path
Q_SINCE = "r1df571e5e07f450283b481b913dcae66"
COURIERS = {"BLUEDART": "Bluedart", "XPRESSBEES": "Xpressbees", "SHADOWFAX": "Shadowfax",
            "DELHIVERY": "Delhivery", "SHIPROCKET": "Shiprocket", "BLITZ": "Blitz"}


def form_courier(name) -> str | None:
    key = str(name or "").upper().replace(" ", "")
    return next((v for k, v in COURIERS.items() if k in key), None)


def responses(done: list[dict], now) -> list[dict]:
    """Per form courier, the orders the courier's site shows not picked up past their pickup
    deadline (from the pickup ticket run's records): {courier, since, orders}."""
    out: dict[str, dict] = {}
    for d in done:
        if d.get("Courier Site") != "not picked" or pd.isna(d.get("Pickup Deadline")):
            continue          # picked up per the courier, or the courier's site not reachable
        if pd.Timestamp(d["Pickup Deadline"]) >= now:
            continue          # still within its pickup time
        c = form_courier(d.get("Courier"))
        if not c:
            continue
        r = out.setdefault(c, {"courier": c, "since": pd.Timestamp(d["Pickup Deadline"]), "orders": 0})
        r["since"] = min(r["since"], pd.Timestamp(d["Pickup Deadline"]))
        r["orders"] += 1
    return sorted(out.values(), key=lambda r: r["courier"])


def submit(courier: str, since) -> None:
    pob = env("POB_ID", "DV00348890")
    answers = [
        {"questionId": Q_SELLER, "answer1": env("AJIO_FORM_SELLER", "Bindal Exports Limited")},
        {"questionId": Q_POB, "answer1": pob[-6:]},
        {"questionId": Q_CONTACT, "answer1": env("AJIO_FORM_CONTACT")},
        {"questionId": Q_ISSUE, "answer1": "Pick-up not done"},
        {"questionId": Q_COURIER, "answer1": json.dumps([courier])},
        {"questionId": Q_SINCE, "answer1": f"{pd.Timestamp(since):%Y-%m-%d}"},
    ]
    now = datetime.now(timezone.utc)
    body = {"startDate": (now - pd.Timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
            "submitDate": now.isoformat().replace("+00:00", "Z"),
            "answers": json.dumps(answers), "submitLanguage": "en-US", "emailReceiptConsent": False}
    r = requests.post(FORM_URL, json=body, timeout=60, headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "Origin": "https://forms.cloud.microsoft", "Referer": "https://forms.cloud.microsoft/",
        "x-ms-form-request-ring": "business", "x-ms-form-request-source": "ms-formweb",
        "x-correlationid": str(uuid.uuid4()), "x-usersessionid": str(uuid.uuid4()),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/141.0.0.0 Safari/537.36"})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"form not accepted: HTTP {r.status_code} {r.text[:200]}")
    log.info("Pickup form sent: %s since %s", courier, f"{pd.Timestamp(since):%d %b}")


def send_forms(done: list[dict], now, already: set[str]) -> tuple[list[str], set[str]]:
    """Send today's forms (a courier once a day: `already` = couriers sent today, from the log).
    Telegram lines, and the couriers sent now."""
    want = [r for r in responses(done, now) if r["courier"] not in already]
    if not want:
        return [], set()
    live = env("AJIO_PICKUP_FORM", "").lower() in ("1", "true", "yes")
    if live and not env("AJIO_FORM_CONTACT"):
        return ["⚠️ AJIO pickup form not sent: AJIO_FORM_CONTACT (contact number) is not set"], set()
    lines, sent = [], set()
    for r in want:
        what = f"{r['courier']} ({r['orders']} orders, not picked up since {r['since']:%d %b})"
        if not live:
            lines.append(f"📝 would send the AJIO pickup form: {what}")
            continue
        try:
            submit(r["courier"], r["since"])
            sent.add(r["courier"])
            lines.append(f"📝 AJIO pickup form sent: {what}")
        except Exception as exc:  # noqa: BLE001 - the other couriers still go
            log.exception("Pickup form for %s not sent", r["courier"])
            lines.append(f"⚠️ AJIO pickup form for {r['courier']} not sent: {str(exc)[:120]}")
    return lines, sent
