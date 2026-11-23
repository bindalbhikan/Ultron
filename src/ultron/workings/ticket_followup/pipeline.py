"""Ticket master and daily follow-up: every portal ticket in one place, each with who follows it up.

Sources (read only): Myntra SPF tickets of MAIN, DBCC, FMCC; every AJIO Help Center ticket.
Output (Drive AGENT WORK):
  TICKET MASTER.xlsx          SUMMARY, OPEN and ALL sheets, one row per ticket; a ticket the portal no longer
                              lists, and every ticket of a source that failed, keeps its last known row (CHECKED ON says when)
  TICKET FOLLOWUP SHEET.xlsx  the owner's five columns: every open ticket; a row added by hand (a ticket the
                              portals here do not list) is kept as the owner wrote it

Who follows up, so that no ticket gets two bots:
  AJIO SPF            ajio-spf (replies only Wed + Sat, the hard rule)
  AJIO pickup         ajio-tat (every 24 h)
  AJIO other GENERAL  this run: one fixed comment when our last word is 24 h old, open tickets only (a comment
                      re-opens a resolved one), at most CAP a run
  Myntra              nobody yet: no call to reply on a ticket is known, so they are listed for a reply by hand
"""
from __future__ import annotations

from ..portals.myntra import ACCOUNTS as MYNTRA_ACCOUNTS  # the one account list
import argparse
import logging
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num
from ..core.drive import agent_folder
from ..core import clients

log = logging.getLogger("bindal.ticket_followup")

MASTER, SHEET = "TICKET MASTER.xlsx", "TICKET FOLLOWUP SHEET.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLS = ["PORTAL", "ACCOUNT", "TYPE", "TICKET ID", "PARTICULAR", "ORDER ID", "RAISED ON", "LAST UPDATE", "AGE DAYS", "STATUS", "OPEN",
        "FOLLOWED UP BY", "LAST FOLLOW-UP", "CHECKED ON"]
SHEET_COLS = ["DATE", "PORTAL", "PARTICULAR", "TICKET ID", "STATUS"]
ACCOUNTS = tuple(MYNTRA_ACCOUNTS)
AJIO_CLOSED = {"RESOLVED", "CLOSED", "COMPLETED", "CANCELLED", "CANCELED", "REJECTED", "AUTO_CLOSED", "WITHDRAWN"}
MYNTRA_CLOSED = {"REJECT", "PAYMENT_COMPLETED", "CLOSED"}
HAND_CLOSED = AJIO_CLOSED | MYNTRA_CLOSED | {"DONE", "SOLVED"}
AJIO_YEARS_BACK = 2
BY_SPF, BY_PICKUP, BY_THIS, BY_HAND = "ajio-spf (Wed, Sat)", "ajio-tat (every 24 h)", "this run (every 24 h)", "by hand (no reply call known)"
FOLLOWUP_TEXT = ("Any update on this ticket? Kindly check and share the current status and the expected resolution date."
                 "\n\nTeam Bindal Exports")


def _day(value) -> str:
    """YYYY-MM-DD of a portal's time, as it gives it."""
    return str(value or "")[:10]


def _myntra_day(value) -> str:
    """YYYY-MM-DD in IST: Myntra gives UTC, so a ticket raised before 5:30 AM belongs to the day after the one it shows."""
    from ..myntra_spf.tickets import _utc
    when = _utc(value)
    return f"{when:%Y-%m-%d}" if when else _day(value)


def _age(raised: str, today: date) -> int | str:
    try:
        return (today - date.fromisoformat(raised)).days
    except ValueError:
        return ""


def myntra_rows(account: str, today: date) -> list[dict]:
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal = myntra_portal(account)
    tickets = portal.spf_tickets()
    mp.save_to_worker(env, portal.cookies(), account)
    out = []
    for t in tickets:
        status, raised = str(t.get("status") or ""), _myntra_day(t.get("createdOn"))
        out.append({"PORTAL": "MYNTRA", "ACCOUNT": account, "TYPE": "SPF", "TICKET ID": str(t.get("ticketId")),
                    "PARTICULAR": str(t.get("issueCategory") or ""), "ORDER ID": str(t.get("orderId") or ""), "RAISED ON": raised,
                    "LAST UPDATE": _myntra_day(t.get("lastModifiedOn")), "AGE DAYS": _age(raised, today), "STATUS": status,
                    "OPEN": "NO" if status in MYNTRA_CLOSED else "YES", "FOLLOWED UP BY": BY_HAND, "CHECKED ON": f"{today}"})
    return out


def ajio_rows(client, today: date) -> list[dict]:
    from ..portals.ajio import PICKUP_NOT_DONE
    out = []
    for t in client.ticket_list(today - timedelta(days=365 * AJIO_YEARS_BACK), today):
        kind, sub = str(t.get("ticketType") or ""), str(t.get("subCategory") or "")
        status, raised = str(t.get("status") or ""), _day(t.get("createdDate"))
        by = BY_SPF if kind == "SPF" else BY_PICKUP if sub.upper() == PICKUP_NOT_DONE else BY_THIS
        out.append({"PORTAL": "AJIO", "ACCOUNT": "", "TYPE": kind, "TICKET ID": str(t.get("ticketId")),
                    "PARTICULAR": f"{sub}: {t.get('subject') or ''}"[:200], "ORDER ID": str(t.get("orderId") or ""), "RAISED ON": raised,
                    "LAST UPDATE": _day(t.get("lastUpdatedOn")), "AGE DAYS": _age(raised, today), "STATUS": status,
                    "OPEN": "NO" if status.upper() in AJIO_CLOSED else "YES", "FOLLOWED UP BY": by, "CHECKED ON": f"{today}"})
    return out


Row = dict


def _s(v) -> str:
    """A value as pandas' astype(str) showed it: an empty one is "nan"."""
    return "nan" if v is None else str(v)


def _number(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _key(r: Row) -> str:
    return f"{_s(r.get('PORTAL'))}|{_s(r.get('TICKET ID'))}"


def _rows(path: Path, sheet, cols: list[str]) -> list[Row]:
    """A sheet's rows as dicts of text (an empty cell None), only `cols`."""
    from ..core.tables import read_excel_text
    df = read_excel_text(path, sheet, engine="openpyxl")
    return [{c: r.get(c) for c in cols} for r in df.iter_rows(named=True)]


def follow_up(client, master: list[Row], today: date, dry: bool) -> tuple[list[str], list[str]]:
    """The fixed comment on the AJIO tickets read open today whose last word from us is old enough; (done ids, problems).
    A ticket not read today (kept from an earlier run) may have closed since: a comment would re-open it. Its detail is read
    first for the same reason; TICKET_OTHER_CAP counts comments, not tickets read."""
    from ..ajio_tat.pipeline import due_followup
    most = num("TICKET_OTHER_MAX_DAYS", 90)
    # a ticket left open for longer is for the owner to look at, not for a comment every day (2 Nov 2026: two from Nov 2024)
    todo = [r for r in master if r["PORTAL"] == "AJIO" and r["OPEN"] == "YES" and r["FOLLOWED UP BY"] == BY_THIS
            and r["CHECKED ON"] == f"{today}" and (age := _number(r["AGE DAYS"])) is not None and age <= most]
    done, problems = [], []
    now = datetime.now()
    cap = int(num("TICKET_OTHER_CAP", 10))
    for tid in (_s(r["TICKET ID"]) for r in todo):
        if len(done) >= cap:
            break
        try:
            ticket = client.ticket_detail(tid)
            if not ticket:
                problems.append(f"AJIO {tid}: not read")
            elif str(ticket.get("status") or "").upper() in AJIO_CLOSED:
                continue
            elif due_followup(ticket, client.seller_id, now, int(num("TICKET_FOLLOWUP_HOURS", 22))):
                if not dry:
                    client.comment(tid, FOLLOWUP_TEXT)
                done.append(tid)
        except Exception as exc:  # noqa: BLE001 - one ticket never stops the others
            problems.append(f"AJIO {tid}: {str(exc).splitlines()[0][:100]}")
    return done, problems


def merge(old: list[Row], new: list[Row]) -> list[Row]:
    """The newest read of every ticket, a ticket not read today as it was; LAST FOLLOW-UP stays. Each value keeps its
    own kind (a number read today stays a number, a kept row's text stays text), as the sheet always had them."""
    last = {_key(r): r.get("LAST FOLLOW-UP") for r in old}
    new = [{**r, "LAST FOLLOW-UP": last.get(_key(r))} for r in new]
    fresh = {_key(r) for r in new}
    kept = [r for r in old if _key(r) not in fresh] if old and new else old
    return [{c: r.get(c) for c in COLS} for r in new + kept]


def sheet_rows(hand: list[Row], master: list[Row]) -> tuple[list[Row], int]:
    """The owner's sheet: every open ticket, a ticket already on it with its status now, hand rows as written;
    open ones first, oldest first. Also the number of hand rows still open."""
    known = {_s(r["TICKET ID"]) for r in master}
    ids = {_s(r["TICKET ID"]) for r in hand}
    rows = [{"DATE": r["RAISED ON"], "PORTAL": f"{r['PORTAL']} {r['ACCOUNT']}".strip() if r["ACCOUNT"] is not None else r["PORTAL"],
             "PARTICULAR": r["PARTICULAR"], "TICKET ID": _s(r["TICKET ID"]), "STATUS": r["STATUS"], "_open": r["OPEN"] == "YES"}
            for r in master if r["OPEN"] == "YES" or _s(r["TICKET ID"]) in ids]
    still = 0
    for r in hand:
        if _s(r["TICKET ID"]) in known:
            continue
        is_open = _s(r["STATUS"]).strip().upper() not in HAND_CLOSED
        still += is_open
        rows.append({**{c: r.get(c) for c in SHEET_COLS}, "_open": is_open})
    rows.sort(key=lambda r: (not r["_open"], _s(r["DATE"])))          # open first, then by date; ties as they came
    return [{c: r[c] for c in SHEET_COLS} for r in rows], still


def _write(path: Path, sheets: list[tuple[str, list[str], list[Row]]]) -> None:
    """The sheets the way the master always looked: white bold header on dark blue, header row frozen, a filter,
    widths from the first 200 rows (10 to 60)."""
    import xlsxwriter
    wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "strings_to_formulas": False, "strings_to_urls": False})
    head = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "pattern": 1})
    for name, cols, rows in sheets:
        ws = wb.add_worksheet(name)
        for c, h in enumerate(cols):
            ws.write_string(0, c, h, head)
        for r, row in enumerate(rows, 1):
            for c, h in enumerate(cols):
                v = row.get(h)
                if v is None or v == "" or (isinstance(v, float) and v != v):
                    continue                      # an empty text stays a blank cell, as pandas wrote it
                if isinstance(v, bool):
                    ws.write_boolean(r, c, v)
                elif isinstance(v, (int, float)):
                    ws.write_number(r, c, v)
                else:
                    ws.write_string(r, c, str(v))
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, max(len(rows), 0), max(len(cols) - 1, 0))
        for c, h in enumerate(cols):
            seen = [h] + [row.get(h) for row in rows[:199]]
            width = max((len(str(v)) for v in seen if v is not None and not (isinstance(v, float) and v != v)), default=0)
            ws.set_column(c, c, min(max(width + 2, 10), 60))
    wb.close()


SUMMARY_COLS = ["PORTAL", "ACCOUNT", "TYPE", "FOLLOWED UP BY", "TICKETS", "OPEN", "CHECKED ON"]


def write_master(master: list[Row], path: Path) -> list[Row]:
    rows = sorted(master, key=lambda r: _s(r["RAISED ON"]), reverse=True)     # newest first; ties keep their order
    groups: dict[tuple, list[Row]] = {}
    for r in rows:
        groups.setdefault((r["PORTAL"], r["ACCOUNT"] if r["ACCOUNT"] is not None else "", r["TYPE"], r["FOLLOWED UP BY"]), []).append(r)
    last = lambda v: (v is None, "" if v is None else str(v))  # noqa: E731 - an empty key last, as pandas sorted groups
    summary = []
    for k in sorted(groups, key=lambda k: tuple(last(v) for v in k)):
        g = groups[k]
        checked = [r["CHECKED ON"] for r in g if r["CHECKED ON"] is not None]
        summary.append(dict(zip(SUMMARY_COLS, (*k, len(g), sum(1 for r in g if r["OPEN"] == "YES"),
                                               max(checked) if checked else None))))
    _write(path, [("SUMMARY", SUMMARY_COLS, summary), ("OPEN", COLS, [r for r in rows if r["OPEN"] == "YES"]), ("ALL", COLS, rows)])
    return summary


def run(args) -> int:
    today = date.today()
    work = Path(tempfile.mkdtemp(prefix="ticket_followup_"))
    root = agent_folder()
    got = root.download(MASTER, work / "old_master.xlsx")
    old = _rows(got, "ALL", COLS) if got else []

    fresh, problems, client = [], [], None
    for account in ACCOUNTS:
        try:
            fresh += myntra_rows(account, today)
        except Exception as exc:  # noqa: BLE001 - a failed source keeps its last rows and is named
            problems.append(f"Myntra {account}: not read, last known rows kept ({str(exc).splitlines()[0][:90]})")
    try:
        client = clients.ajio()
        fresh += ajio_rows(client, today)
    except Exception as exc:  # noqa: BLE001
        client = None
        problems.append(f"AJIO: not read, last known rows kept ({str(exc).splitlines()[0][:90]})")
    if not fresh:
        raise RuntimeError("no portal could be read: " + "; ".join(problems))
    master = merge(old, fresh)

    done, bad = follow_up(client, master, today, args.dry_run or args.no_upload) if client else ([], [])
    problems += bad
    if not (args.dry_run or args.no_upload):
        for r in master:
            if r["PORTAL"] == "AJIO" and _s(r["TICKET ID"]) in done:
                r["LAST FOLLOW-UP"] = f"{today}"

    # read last, as the portals take minutes: a row the owner adds meanwhile is kept. A row with no ticket id is the owner's too.
    got = root.download(SHEET, work / "old_sheet.xlsx")
    hand = [r for r in _rows(got, 0, SHEET_COLS) if any(v is not None for v in r.values())] if got else []
    sheet, hand_open = sheet_rows(hand, master)
    master_file, sheet_file = work / MASTER, work / SHEET
    summary = write_master(master, master_file)
    _write(sheet_file, [("Sheet1", SHEET_COLS, sheet)])

    lines = [f"🎫 <b>Ticket follow-up</b> {today}", ""]
    for r in summary:
        if r["OPEN"] > 0:
            name = f"{r['PORTAL']} {r['ACCOUNT']}".strip()
            lines.append(f"<b>{telegram.esc(name)}</b> {telegram.esc(r['TYPE'])}: {r['OPEN']} open · {telegram.esc(r['FOLLOWED UP BY'])}")
    lines.append(f"\nTotal open: <b>{sum(1 for r in master if r['OPEN'] == 'YES')}</b>" + (f" + {hand_open} added by hand" if hand_open else ""))
    lines.append(f"Followed up in this run: <b>{len(done)}</b>" + (" (dry run, nothing posted)" if args.dry_run or args.no_upload else ""))
    lines += [f"❌ {telegram.esc(x)}" for x in problems[:12]]
    if args.no_upload:
        lines.append("\n<i>test run: Drive not changed</i>")
        out = Path("output/ticket_followup")
        out.mkdir(parents=True, exist_ok=True)
        for f in (master_file, sheet_file):
            (out / f.name).write_bytes(f.read_bytes())
        print("\n".join(lines))
        return 0
    root.put(master_file, XLSX)
    root.put(sheet_file, XLSX)
    lines.append(f"\n<i>Drive AGENT WORK: {MASTER}, {SHEET}</i>")
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py ticket-followup", description=__doc__.splitlines()[0])
    p.add_argument("--no-upload", action="store_true", help="test run: nothing posted, Drive not changed (output/ticket_followup)")
    p.add_argument("--dry-run", action="store_true", help="nothing posted on any ticket, Drive still updated")
    return run_bot("Ticket follow-up", p, run, argv)
