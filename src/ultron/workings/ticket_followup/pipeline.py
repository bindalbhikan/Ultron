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

import argparse
import logging
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num
from ..core.drive import DriveFolder

log = logging.getLogger("bindal.ticket_followup")

MASTER, SHEET = "TICKET MASTER.xlsx", "TICKET FOLLOWUP SHEET.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLS = ["PORTAL", "ACCOUNT", "TYPE", "TICKET ID", "PARTICULAR", "ORDER ID", "RAISED ON", "LAST UPDATE", "AGE DAYS", "STATUS", "OPEN",
        "FOLLOWED UP BY", "LAST FOLLOW-UP", "CHECKED ON"]
SHEET_COLS = ["DATE", "PORTAL", "PARTICULAR", "TICKET ID", "STATUS"]
ACCOUNTS = ("MAIN", "DBCC", "FMCC")
AJIO_CLOSED = {"RESOLVED", "CLOSED", "COMPLETED", "CANCELLED", "CANCELED", "REJECTED", "AUTO_CLOSED", "WITHDRAWN"}
MYNTRA_CLOSED = {"REJECT", "PAYMENT_COMPLETED"}
HAND_CLOSED = AJIO_CLOSED | MYNTRA_CLOSED | {"DONE", "SOLVED"}
AJIO_YEARS_BACK = 2
BY_SPF, BY_PICKUP, BY_THIS, BY_HAND = "ajio-spf (Wed, Sat)", "ajio-tat (every 24 h)", "this run (every 24 h)", "by hand (no reply call known)"
FOLLOWUP_TEXT = ("Any update on this ticket? Kindly check and share the current status and the expected resolution date."
                 "\n\nTeam Bindal Exports")


def _day(value) -> str:
    """YYYY-MM-DD of a portal's time, as it gives it."""
    return str(value or "")[:10]


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
        status, raised = str(t.get("status") or ""), _day(t.get("createdOn"))
        out.append({"PORTAL": "MYNTRA", "ACCOUNT": account, "TYPE": "SPF", "TICKET ID": str(t.get("ticketId")),
                    "PARTICULAR": str(t.get("issueCategory") or ""), "ORDER ID": str(t.get("orderId") or ""), "RAISED ON": raised,
                    "LAST UPDATE": _day(t.get("lastModifiedOn")), "AGE DAYS": _age(raised, today), "STATUS": status,
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


def follow_up(client, master: pd.DataFrame, today: date, dry: bool) -> tuple[list[str], list[str]]:
    """The fixed comment on this run's open AJIO tickets whose last word from us is 24 h old; (done ids, problems)."""
    from ..ajio_tat.pipeline import due_followup
    todo = master[(master["PORTAL"] == "AJIO") & (master["OPEN"] == "YES") & (master["FOLLOWED UP BY"] == BY_THIS)]
    # a ticket left open for longer is for the owner to look at, not for a comment every day (2 Nov 2026: two from Nov 2024)
    todo = todo[pd.to_numeric(todo["AGE DAYS"], errors="coerce") <= num("TICKET_OTHER_MAX_DAYS", 90)]
    done, problems = [], []
    now = pd.Timestamp(datetime.now())
    for tid in todo["TICKET ID"].astype(str).head(int(num("TICKET_OTHER_CAP", 10))):
        try:
            ticket = client.ticket_detail(tid)
            if not ticket:
                problems.append(f"AJIO {tid}: not read")
            elif due_followup(ticket, client.seller_id, now, int(num("TICKET_FOLLOWUP_HOURS", 24))):
                if not dry:
                    client.comment(tid, FOLLOWUP_TEXT)
                done.append(tid)
        except Exception as exc:  # noqa: BLE001 - one ticket never stops the others
            problems.append(f"AJIO {tid}: {str(exc).splitlines()[0][:100]}")
    return done, problems


def merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """The newest read of every ticket, a ticket not read today as it was; LAST FOLLOW-UP stays."""
    key = lambda d: d["PORTAL"].astype(str) + "|" + d["TICKET ID"].astype(str)  # noqa: E731
    last = dict(zip(key(old), old["LAST FOLLOW-UP"])) if len(old) else {}
    if len(new):
        new = new.assign(**{"LAST FOLLOW-UP": key(new).map(last)})
    kept = old[~key(old).isin(set(key(new)))] if len(old) and len(new) else old
    both = [d for d in (new, kept) if len(d)]
    if not both:
        return pd.DataFrame(columns=COLS, dtype=object)
    # object: with no follow-up recorded yet the column is all empty (float), which refuses a date (2 Nov 2026)
    return pd.concat(both, ignore_index=True).reindex(columns=COLS).astype({"LAST FOLLOW-UP": object})


def sheet_rows(hand: pd.DataFrame, master: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """The owner's sheet: every open ticket, a ticket already on it with its status now, hand rows as written;
    open ones first, oldest first. Also the number of hand rows still open."""
    known = master.set_index(master["TICKET ID"].astype(str))
    ids = set(hand["TICKET ID"].astype(str)) if len(hand) else set()
    keep = master[(master["OPEN"] == "YES") | master["TICKET ID"].astype(str).isin(ids)]
    rows = [{"DATE": r["RAISED ON"], "PORTAL": f"{r['PORTAL']} {r['ACCOUNT']}".strip() if pd.notna(r["ACCOUNT"]) else r["PORTAL"],
             "PARTICULAR": r["PARTICULAR"], "TICKET ID": str(r["TICKET ID"]), "STATUS": r["STATUS"], "_open": r["OPEN"] == "YES"}
            for _, r in keep.iterrows()]
    own, still = hand[~hand["TICKET ID"].astype(str).isin(set(known.index))] if len(hand) else hand, 0
    for _, r in own.iterrows():
        is_open = str(r["STATUS"]).strip().upper() not in HAND_CLOSED
        still += is_open
        rows.append({**{c: (None if pd.isna(r[c]) else r[c]) for c in SHEET_COLS}, "TICKET ID": str(r["TICKET ID"]), "_open": is_open})
    out = pd.DataFrame(rows, columns=[*SHEET_COLS, "_open"])
    out = out.assign(_d=out["DATE"].astype(str)).sort_values(["_open", "_d"], ascending=[False, True], kind="stable")
    return out[SHEET_COLS], still


def _format(xw) -> None:
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    for ws in xw.book.worksheets:
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, col in enumerate(ws.iter_cols(max_row=200), start=1):
            width = max((len(str(c.value)) for c in col if c.value is not None), default=0)
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)


def write_master(master: pd.DataFrame, path: Path) -> pd.DataFrame:
    rows = master.assign(_d=master["RAISED ON"].astype(str)).sort_values("_d", ascending=False, kind="stable").drop(columns="_d")
    who = rows.assign(ACCOUNT=rows["ACCOUNT"].fillna(""))
    summary = (who.groupby(["PORTAL", "ACCOUNT", "TYPE", "FOLLOWED UP BY"], dropna=False)
               .agg(TICKETS=("TICKET ID", "size"), OPEN=("OPEN", lambda x: int((x == "YES").sum())), **{"CHECKED ON": ("CHECKED ON", "max")}).reset_index())
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="SUMMARY", index=False)
        rows[rows["OPEN"] == "YES"].to_excel(xw, sheet_name="OPEN", index=False)
        rows.to_excel(xw, sheet_name="ALL", index=False)
        _format(xw)
    return summary


def run(args) -> int:
    today = date.today()
    work = Path(tempfile.mkdtemp(prefix="ticket_followup_"))
    root = DriveFolder(env("AGENT_WORK_FOLDER_ID", pr.AGENT_WORK))
    got = root.download(MASTER, work / "old_master.xlsx")
    old = pd.read_excel(got, sheet_name="ALL", dtype=str).reindex(columns=COLS) if got else pd.DataFrame(columns=COLS, dtype=object)
    got = root.download(SHEET, work / "old_sheet.xlsx")
    hand = pd.read_excel(got, dtype=str).reindex(columns=SHEET_COLS).dropna(subset=["TICKET ID"]) if got else pd.DataFrame(columns=SHEET_COLS, dtype=object)

    fresh, problems, client = [], [], None
    for account in ACCOUNTS:
        try:
            fresh += myntra_rows(account, today)
        except Exception as exc:  # noqa: BLE001 - a failed source keeps its last rows and is named
            problems.append(f"Myntra {account}: not read, last known rows kept ({str(exc).splitlines()[0][:90]})")
    try:
        from ..portals.ajio import AjioClient
        client = AjioClient(env("AJIO_USERNAME"), env("AJIO_PASSWORD"))
        client.login()
        fresh += ajio_rows(client, today)
    except Exception as exc:  # noqa: BLE001
        client = None
        problems.append(f"AJIO: not read, last known rows kept ({str(exc).splitlines()[0][:90]})")
    if not fresh:
        raise RuntimeError("no portal could be read: " + "; ".join(problems))
    master = merge(old, pd.DataFrame(fresh, columns=COLS))

    done, bad = follow_up(client, master, today, args.dry_run or args.no_upload) if client else ([], [])
    problems += bad
    if not (args.dry_run or args.no_upload):
        master.loc[master["TICKET ID"].astype(str).isin(done) & (master["PORTAL"] == "AJIO"), "LAST FOLLOW-UP"] = f"{today}"

    sheet, hand_open = sheet_rows(hand, master)
    master_file, sheet_file = work / MASTER, work / SHEET
    summary = write_master(master, master_file)
    with pd.ExcelWriter(sheet_file, engine="openpyxl") as xw:
        sheet.to_excel(xw, sheet_name="Sheet1", index=False)
        _format(xw)

    lines = [f"🎫 <b>Ticket follow-up</b> {today}", ""]
    for _, r in summary[summary["OPEN"] > 0].iterrows():
        name = f"{r['PORTAL']} {r['ACCOUNT']}".strip()
        lines.append(f"<b>{telegram.esc(name)}</b> {telegram.esc(r['TYPE'])}: {r['OPEN']} open · {telegram.esc(r['FOLLOWED UP BY'])}")
    lines.append(f"\nTotal open: <b>{int((master['OPEN'] == 'YES').sum())}</b>" + (f" + {hand_open} added by hand" if hand_open else ""))
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
