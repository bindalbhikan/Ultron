"""Myntra courier OTPs (10 AM, again at 11 AM with --retry): today's PICKUP and RETURN one-time codes of the TLPL, MMRJ and BOAT
warehouses, from the partner portal's Orders > OTC page (api/location/otc), to Telegram.

Each OMSGuru channel is one Myntra seller account and its Surat warehouse (the warehouse code
C45111W17453 names channel 45111): TLPL = MAIN 46148, MMRJ = DBCC 50829, BOAT = FMCC 56765
(MYNTRA_OTP_SITES, code:account:warehouse). A courier with no trip today has no code ("-").

The codes go to Telegram and into the team's "Daily OTP 2026" Google Sheet (MYNTRA_OTP_SHEET_ID),
one row per code in its own layout: DATE, PORTAL, COUNT (left empty, filled in by hand), OTP,
STATUS (PICKUP / RETURN), Name (MYNTRA_OTP_NAME, Bhikan) and the courier as the team writes it (MYE = EK, MYS = FL).
A code the sheet already has that day is not added again; a code Myntra changed replaces the bot's own
row (COUNT still empty) and never a row the team filled (Telegram is told). Nothing is logged.
--retry (11 AM): a courier often has no trip yet at 10 AM. The codes are read again; Telegram
hears only when there is a code the sheet did not have yet (or the sheet has no code of today at all).
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime

from ..core import telegram
from ..core.app import run_bot
from ..core.config import env

log = logging.getLogger("bindal.myntra_otp")

SITES = "TLPL:MAIN:46148,MMRJ:DBCC:50829,BOAT:FMCC:56765"
TRIPS = (("PICKUP", "Pickup"), ("RETURN", "Return"))


def sites() -> list[tuple[str, str, str]]:
    return [tuple(s.strip() for s in p.split(":")) for p in (env("MYNTRA_OTP_SITES") or SITES).split(",")
            if p.count(":") == 2]


def read_codes(portal_of=None) -> tuple[list[tuple[str, str, dict[str, str]]], list[str], list[str]]:
    """[(code, trip label, {courier: otc or "-"})], the couriers seen, and notes for sites not read."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal_of = portal_of or myntra_portal
    rows, couriers, notes = [], [], []
    for code, account, warehouse in sites():
        try:
            portal = portal_of(account)
            for trip, label in TRIPS:
                got = portal.otc(warehouse, trip)
                for o in got:
                    if o["courier"] not in couriers:
                        couriers.append(o["courier"])
                rows.append((code, label, {o["courier"]: o["otc"] or "-" for o in got}))
            if hasattr(portal, "cookies"):
                mp.save_to_worker(env, portal.cookies(), account)
        except Exception as exc:  # noqa: BLE001 - the other accounts still go out
            log.warning("%s (%s) OTPs not read: %s", code, account, str(exc)[:150])
            notes.append(f"{code}: not read ({str(exc)[:80]})")
    return rows, couriers, notes


ACCOUNT_NAMES = {"TLPL": "Myntra Main", "MMRJ": "Myntra DBCC", "BOAT": "Myntra FF X MUR CC"}


def message(rows, couriers, notes, now: datetime) -> str:
    """Plain lines, one per account and trip, each code named by its courier as the team writes it
    (EK / FL): it still reads right when copied out of Telegram into WhatsApp."""
    out = [f"🔐 <b>Myntra courier OTP · {now:%d %b %Y}</b>"]
    last = None
    for code, label, codes in rows:
        if code != last:
            out += ["", f"<b>{telegram.esc(code)}</b> ({telegram.esc(ACCOUNT_NAMES.get(code, code))})"]
            last = code
        parts = [f"{COURIER_TAGS.get(c, c)}: {codes[c] if codes.get(c, '-') != '-' else 'no trip'}"
                 for c in sorted(codes, key=lambda c: COURIER_TAGS.get(c, c))]
        out.append(f"{label}: " + " | ".join(telegram.esc(p) for p in parts))
    out += ["", "Pickup = forward pickup OTP, Return = return handover OTP"]
    if notes:
        out += [""] + ["⚠️ " + telegram.esc(n) for n in notes]
    return "\n".join(out)


SHEET_ID = "1dKfym74siyYHPM-JgisDq_2LcOckiqod59aibOAHbAA"
PORTAL_NAMES = {"TLPL": "Myntra_Main_TLPL", "MMRJ": "Myntra_DBCC_MMRJ", "BOAT": "Myntra_FF X MUR CC_BOAT"}
COURIER_TAGS = {"MYE": "EK", "MYS": "FL"}


def sheet_rows(rows, now: datetime, existing: list[list[str]], notes: list[str] | None = None):
    """(new rows, {sheet row number: new code}) for today's codes - never a second row and never a
    team row changed:
      - a code the sheet has that day (any portal: Ultron Phone or the team may have written it) - nothing;
      - a courier whose row of that day, portal and status has another code (Myntra changed it by the
        11 AM retry) - the code of that row is replaced only while its COUNT is empty (the bot's own
        row, not yet worked by the team); a row the team filled is left alone and named in `notes`;
      - else a new row."""
    grid = [(list(map(str, x)) + [""] * 7)[:7] for x in existing]
    day, out, replace = f"{now:%d-%m-%Y}", [], {}
    codes_today = {r[3].strip() for r in grid if r[0].strip() == day}
    for code, label, codes in rows:
        for courier, otc in codes.items():
            if otc in (None, "", "-") or str(otc) in codes_today:
                continue
            portal, status, tag = PORTAL_NAMES.get(code, f"Myntra_{code}"), label.upper(), COURIER_TAGS.get(courier, courier)
            mine = [i for i, r in enumerate(grid) if r[0].strip() == day and r[1].strip() == portal
                    and r[4].strip().upper() == status and r[6].strip() == tag]
            codes_today.add(str(otc))
            if mine:
                i = mine[-1]
                if grid[i][2].strip() == "":
                    replace[i + 1] = str(otc)                # sheet row number (the header is row 1)
                elif notes is not None:
                    notes.append(f"{portal} {tag} {status}: new code {otc}, the team's row has {grid[i][3]} (left)")
                continue
            out.append([day, portal, "", str(otc), status, env("MYNTRA_OTP_NAME") or "Bhikan", tag])
    return out, replace


def write_sheet(rows, now: datetime, notes: list[str] | None = None) -> tuple[int, bool]:
    """Today's codes into the OTP sheet: (rows added or changed, whether the sheet had a code of today before)."""
    import gspread
    from ..core.gauth import credentials
    ws = gspread.authorize(credentials(["https://www.googleapis.com/auth/spreadsheets"])).open_by_key(
        env("MYNTRA_OTP_SHEET_ID") or SHEET_ID).sheet1
    existing = ws.get_all_values()
    had_today = any(r and str(r[0]).strip() == f"{now:%d-%m-%Y}" for r in existing)
    new, replace = sheet_rows(rows, now, existing, notes)
    for row, otc in replace.items():
        ws.update_cell(row, 4, otc)                         # the OTP cell only
    if new:
        ws.append_rows(new, value_input_option="RAW")       # RAW: an OTP keeps its leading zeros
    return len(new) + len(replace), had_today


def run(args) -> int:
    rows, couriers, notes = read_codes()
    now = datetime.now()
    added, had_today = None, False
    if rows and not args.no_sheet:
        try:
            added, had_today = write_sheet(rows, now, notes)
            log.info("OTP sheet: %d rows added", added)
        except Exception as exc:  # noqa: BLE001 - the Telegram message still goes out
            log.warning("OTP sheet not updated: %s", exc)
            notes.append(f"OTP sheet not updated: {type(exc).__name__} {str(exc)[:80]}")
    if args.retry and added == 0 and had_today and not any(n.endswith("(left)") for n in notes):
        log.info("Retry: no OTP the 10 AM run did not already send; no message")
        return 0
    text = message(rows, couriers, notes, now)
    if args.retry:
        text = text.replace("</b>", " · 11 AM update</b>", 1)
    print(text) if args.no_telegram else telegram.send(text)
    return 0 if rows else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py myntra-otp", description="Myntra courier pickup / return OTPs")
    p.add_argument("--no-telegram", action="store_true", help="print the message instead of sending it")
    p.add_argument("--no-sheet", action="store_true", help="leave the Daily OTP sheet alone")
    p.add_argument("--retry", action="store_true",
                   help="11 AM: send only when there is an OTP the sheet does not have yet")
    return run_bot("Myntra courier OTP", p, run, argv)
