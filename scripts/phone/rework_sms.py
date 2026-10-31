"""Work again the courier SMS already on the Ultron Phone SMS sheet (Phone OTP Sheet 2026), oldest first:
each POD behind an SMS link downloaded and read here, sent with the SMS to the sheet's Apps Script
(rework=1), which files it like a new one - the PDF into Drive AGENT WORK/RETURN PODS/<date>/, its
AWBs into RETURN PODS MASTER, the SMS row's Agent note and OTP SHEET checkbox. Links that expired
(Shadowfax answers 410 after a while) are noted on the row. Nothing is filed twice.

    python scripts/phone/rework_sms.py [--since 2026-09-01]     every courier SMS (from that day)
    python scripts/phone/rework_sms.py --pending [--days 2]     catch-up (.github/workflows/sms-catchup.yml):
                                                                only SMS the script did not work (no Agent
                                                                note), that failed (error) or whose POD
                                                                did not come for a reason other than an
                                                                expired link; Telegram hears of any still failing

SMS_WEBAPP_URL / SMS_WEBAPP_KEY: the web app's /exec URL and its key (the app's "SMS to sheet" settings).
"""
from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ultron.workings.core.config import env, load_dotenv  # noqa: E402

SMS_SHEET = "1bKyLu132rZQakC4sOwQNJ4Ev4lpN-ff4E9ewflIeZkI"
COURIERS = re.compile(r"DLHVRY|SFX|XPBEES|EKART", re.I)
LINK = re.compile(r"https?://\S+")
EXPIRED = re.compile(r"HTTP 4\d\d|not a PDF")
# a courier SMS with something to file: a code or a POD link ("picked up today by rider" has neither,
# so the script leaves no note on it and the catch-up must not take it for a missed one)
WORK = re.compile(r"https?://|\bOTP\b|\bcode\b", re.I)


def pod(body: str) -> dict:
    """The fields the phone sends for an SMS's POD (the same as android app Pod.kt)."""
    link = LINK.search(body)
    if not link:
        return {}
    try:
        r = requests.get(link.group(0).rstrip(".,)"), timeout=60, headers={"User-Agent": "Mozilla/5.0 UltronPhone"})
        if r.status_code != 200:
            return {"pdferror": f"HTTP {r.status_code}"}
        if not r.content.startswith(b"%PDF-"):
            head = r.content[:512].lstrip().lower()
            if head.startswith(b"<") and b"html" in head:     # Shadowfax's HTML sheets: saved as a PDF by the script
                return {"html": base64.b64encode(r.content).decode()}
            return {"pdferror": "link is not a PDF"}
        import pypdf
        text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)
        return {"pdf": base64.b64encode(r.content).decode(), "pdftext": text}
    except Exception as exc:  # noqa: BLE001 - noted on the row, the rest go on
        return {"pdferror": str(exc)[:80]}


def pending(note: str) -> bool:
    """A row the catch-up works again: never worked, failed, or its POD missed for a passing reason."""
    note = note.strip()
    if not note or note.startswith("error"):
        return True
    m = re.search(r"POD not downloaded(?: \(([^)]*)\))?", note)
    return bool(m) and not EXPIRED.search(m.group(1) or "")


def sms_rows():
    import gspread
    from ultron.workings.core.gauth import credentials
    return gspread.authorize(credentials(["https://www.googleapis.com/auth/spreadsheets"])).open_by_key(
        SMS_SHEET).worksheet("SMS").get_all_values()[1:]


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", default="", help="only SMS of this day (YYYY-MM-DD) or later")
    p.add_argument("--pending", action="store_true", help="only SMS not worked, failed or without their POD")
    p.add_argument("--days", type=int, default=2, help="--pending: SMS of the last N days (default 2)")
    p.add_argument("--no-telegram", action="store_true", help="--pending: print instead of telling Telegram")
    args = p.parse_args()
    url, key = env("SMS_WEBAPP_URL"), env("SMS_WEBAPP_KEY")
    if not url or not key:
        print("SMS_WEBAPP_URL / SMS_WEBAPP_KEY not set")
        return 1

    since = args.since or (f"{datetime.now() - timedelta(days=args.days):%Y-%m-%d}" if args.pending else "")
    todo = sorted((r for r in sms_rows() if len(r) > 4 and COURIERS.search(r[1]) and r[3] >= since
                   and (not args.pending or (WORK.search(r[2]) and pending(r[5] if len(r) > 5 else "")))),
                  key=lambda r: r[3])
    print(f"{len(todo)} courier SMS")
    failed = []
    for r in todo:
        sender, body, time, sim = r[1], r[2], r[3], r[4]
        fields = {"key": key, "from": sender, "body": body, "time": time, "sim": sim, "rework": "1", **pod(body)}
        try:
            answer = requests.post(url, data=fields, timeout=180).text.strip()[:60]
        except requests.RequestException as exc:
            answer = f"error: {type(exc).__name__}"
        if answer != "ok":
            failed.append(f"{time} {sender}: {answer}")
        got = "POD" if fields.get("pdf") else "POD (html)" if fields.get("html") else fields.get("pdferror", "-")
        print(f"{time}  {sender:12}  {got:18}  {answer}")

    if args.pending and todo:
        keys = {(r[1], r[2], r[3]) for r in todo}
        failed += [f"{r[3]} {r[1]}: {r[5][:100]}" for r in sms_rows()
                   if (r[1], r[2], r[3]) in keys and len(r) > 5 and r[5].startswith("error")]
        if failed:
            from ultron.workings.core import telegram
            text = ("⚠️ <b>Returns SMS catch-up</b>\n<i>still failing after a retry</i>\n\n"
                    + "\n".join(telegram.esc(f) for f in failed[:20]))
            print(text) if args.no_telegram else telegram.send(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
