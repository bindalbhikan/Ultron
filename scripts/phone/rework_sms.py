"""Work again the courier SMS already on the Ultron Phone SMS sheet (Phone OTP Sheet 2026), oldest first:
each POD behind an SMS link downloaded and read here, sent with the SMS to the sheet's Apps Script
(rework=1), which files it like a new one - the PDF into Drive AGENT WORK/RETURN PODS/<date>/, its
AWBs into RETURN PODS MASTER, the SMS row's Agent note and OTP SHEET checkbox. Links that expired
(Shadowfax answers 410 after a while) are noted on the row.

    python scripts/phone/rework_sms.py [--since 2026-09-01]

SMS_WEBAPP_URL / SMS_WEBAPP_KEY: the web app's /exec URL and its key (the app's "SMS to sheet" settings).
"""
from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ultron.workings.core.config import env, load_dotenv  # noqa: E402

SMS_SHEET = "1bKyLu132rZQakC4sOwQNJ4Ev4lpN-ff4E9ewflIeZkI"
COURIERS = re.compile(r"DLHVRY|SFX|XPBEES|EKART", re.I)
LINK = re.compile(r"https?://\S+")


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
            return {"pdferror": "link is not a PDF"}
        import pypdf
        text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)
        return {"pdf": base64.b64encode(r.content).decode(), "pdftext": text}
    except Exception as exc:  # noqa: BLE001 - noted on the row, the rest go on
        return {"pdferror": str(exc)[:80]}


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", default="", help="only SMS of this day (YYYY-MM-DD) or later")
    args = p.parse_args()
    url, key = env("SMS_WEBAPP_URL"), env("SMS_WEBAPP_KEY")
    if not url or not key:
        print("SMS_WEBAPP_URL / SMS_WEBAPP_KEY not set")
        return 1

    import gspread
    from ultron.workings.core.gauth import credentials
    rows = gspread.authorize(credentials(["https://www.googleapis.com/auth/spreadsheets"])).open_by_key(
        SMS_SHEET).worksheet("SMS").get_all_values()[1:]
    todo = sorted((r for r in rows if len(r) > 4 and COURIERS.search(r[1]) and r[3] >= args.since), key=lambda r: r[3])
    print(f"{len(todo)} courier SMS")
    for r in todo:
        sender, body, time, sim = r[1], r[2], r[3], r[4]
        fields = {"key": key, "from": sender, "body": body, "time": time, "sim": sim, "rework": "1", **pod(body)}
        answer = requests.post(url, data=fields, timeout=180).text.strip()[:60]
        print(f"{time}  {sender:12}  {'POD' if fields.get('pdf') else fields.get('pdferror', '-'):18}  {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
