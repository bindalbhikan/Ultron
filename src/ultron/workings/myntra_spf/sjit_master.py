"""MYNTRA SJIT SPF MASTER.xlsx: the SJIT / FBM returns and their SPF claims, in their own file (owner, 25 Nov 2026:
not in the PPMP master, laid out like MYNTRA SPF MASTER), Drive AGENT WORK/SPF CLAIMS, rebuilt by every
myntra-spf run after the PPMP master.

Its rows are the PPMP master's SJIT / FBM rows (model SJIT or FBM, which that master keeps NON ELIGIBLE and out
of its summaries): every column as the engine fills it (order amount, settlement, return debit, SPF paid, UTR,
PODs), with the claim columns taken from the SJIT claims instead (CLAIM STATUS, CLAIM TYPE, TICKET ID, CLAIM TAT,
STATUS, REJECTION REASON) and five SJIT columns at the end (FACT CORE ITEM ID, MYNTRA STOCK, LAST CHECKED,
BOT RESULT, BOT JOB). An item of the SJIT returns report the master does not have yet gets a short row.

Sheets as in the PPMP master: SUMMARY (account x return month), DATE SUMMARY (account x return day), CLAIM TAT
(account x claim month), one sheet per account, RETURN IN TRANSIT, TICKETS (the SJIT claims), INPUT LOG (the SJIT
returns reports read). The figures are values (the PPMP master's are COUNTIFS formulas over the same columns).
The bot owns the file: an edit made on Drive is not kept.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from . import tickets as tk

log = logging.getLogger(__name__)

SJIT_MASTER = "MYNTRA SJIT SPF MASTER.xlsx"
MODELS = {"SJIT", "FBM"}
TRANSIT_SHEET = "RETURN IN TRANSIT"        # engine.PARKED_SHEET; its rows name their account in ACCOUNT
SJIT_COLS = ["FACT CORE ITEM ID", "MYNTRA STOCK", "LAST CHECKED", "BOT RESULT", "BOT JOB"]
# The PPMP master's layout (MYNTRA SPF MASTER.xlsx, 25 Nov 2026)
YELLOW, BLUE = "#FFFF00", "#D9E1F2"
YELLOW_FROM, YELLOW_TO = "AGE (DAYS)", "UTR NO"          # the engine's columns, yellow headers
SUBTOTAL_COLS = ["ORDER AMOUNT", "ORDER SETTLEMENT", "RETURN DEBIT", "RETURN CHARGE", "SPF PAID", "NET"]
ID_COLS = {"seller_id", "warehouse_id", "order_group_id", "order_line_id", "return_id", "return_tracking_number"}
AMOUNT_COLS = {"ORDER AMOUNT", "ORDER SETTLEMENT", "RETURN DEBIT", "NET"}
WIDTHS = {"seller_id": 10.7, "warehouse_id": 12.7, "model": 9.7, "seller_order_id": 24.7, "STORE ORDER ID": 22.7,
          "order_group_id": 14.7, "return_created_date": 16.7, "RETURN MONTH": 12.7, "deliver_to_seller_date": 17.7,
          "type": 10.7, "status": 14.7, "return_status": 12.7, "forward_tracking_number": 17.7,
          "DISPATCH STATUS": 15.7, "DISPATCH DATE": 14.7, "DISPATCH VOUCHER": 18.7, "AGE (DAYS)": 10.7,
          "CLAIM STATUS": 16.7, "CLAIM TYPE": 21.7, "OMSGURU STATUS": 20.7, "MANUAL RETURN STATUS": 21.7,
          "FINAL RETURN STATUS": 19.7, "TICKET ID": 12.7, "REJECTION REASON": 46.7, "ORDER AMOUNT": 14.7,
          "ORDER SETTLEMENT": 16.7, "RETURN DEBIT": 14.7, "SPF PAID": 15.7, "NET": 12.7, "UTR NO": 30.7,
          "PICKUP POD": 12.7, "RETURN POD DATE": 16.7, "FACT CORE ITEM ID": 18.7, "MYNTRA STOCK": 14.7,
          "LAST CHECKED": 17.7, "BOT RESULT": 30.7, "BOT JOB": 12.7}
SUMMARY_COLS = ["ACCOUNT", "RETURN MONTH", "TOTAL RETURNS", "RETURN RECEIVED", "SPF / PAYMENT SETTLED", "IN TRANSIT",
                "IN TRANSIT AMT", "DELIVERED PENDING", "DELIVERED PENDING AMT", "ELIGIBLE CLAIMS",
                "ELIGIBLE CLAIM AMT", "UPCOMING CLAIM AMT", "CLAIM DONE", "SPF PAID AMT"]
DATE_COLS = ["ACCOUNT", "RETURN DATE", "TOTAL RETURNS", "RETURN RECEIVED", "IN TRANSIT", "IN TRANSIT AMT",
             "DELIVERED PENDING", "DELIVERED PENDING AMT", "ELIGIBLE CLAIMS", "ELIGIBLE CLAIM AMT"]
TAT_COLS = ["ACCOUNT", "TICKET MONTH", "CLAIMS RAISED", "CLAIM QTY", "CLAIM AMT", "WITHIN TAT", "WITHIN TAT QTY",
            "WITHIN TAT AMT", "OUTSIDE TAT", "OUTSIDE TAT QTY", "OUTSIDE TAT AMT", "ACCEPTED", "ACCEPTED AMT", "PAID",
            "PAID AMT", "SPF PAID AMT", "REJECTED", "REJECTED AMT", "OPEN", "OPEN AMT"]
TICKET_COLS = ["ACCOUNT", "TICKET ID", "ORDER LINE ID", "RETURN ID", "ORDER ID", "CATEGORY", "STATUS",
               "NEEDS OUR REPLY", "CREATED", "LAST UPDATED", "STATUS HISTORY", "REASON", "COMPENSATION", "UTR",
               "PAYMENT INITIATED", "DESCRIPTION", "SUPPORT TICKET", "REPLIES", "LAST REPLY BY", "LAST REPLY AT",
               "LAST REPLY", "FACT CORE ITEM ID"]
LOG_COLS = ["ACCOUNT", "REPORT", "FROM", "TO", "FILE", "PROCESSED ON"]
SETTLED = {"SPF Paid", "SPF Accepted", "Payment Received"}
PAID = {"PAYMENT_COMPLETED", "PAYMENT_INITIATED", "INVOICE_CREATED", "INVOICE_INITIATED"}
ELIGIBLE_RESULTS = {tk.SJIT_DUE, tk.SJIT_NOT_RAISED, tk.SJIT_FAILED, tk.SJIT_CAPPED}
NO_CORE = "NO FACT CORE ID (older than the SJIT report window)"
FILE_DATES = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.\w+$")


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _v(v):
    """A cell as written: whole floats as ints (ids), "" as None."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None if v == "" else v


def _id(v) -> str:
    v = _v(v)
    return "" if v is None else str(v).strip()


def _day(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(_s(v)[:10])
    except ValueError:
        return None


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ reading

def read_book(path: Path) -> dict[str, tuple[list[str], list[dict]]]:
    """sheet -> (headers, rows) of a master (account sheets and RETURN IN TRANSIT: headers on row 2, below the
    SUBTOTAL row; the other sheets on row 1). None when the file is not there."""
    from python_calamine import CalamineWorkbook
    if not path or not path.exists():
        return {}
    wb = CalamineWorkbook.from_path(str(path))
    out = {}
    for name in wb.sheet_names:
        rows = wb.get_sheet_by_name(name).to_python()
        if not rows:
            continue
        at = 1 if len(rows) > 1 and not any(_s(v) for v in rows[0][:3]) else 0
        head = [_s(h) for h in rows[at]]
        out[name] = (head, [dict(zip(head, r)) for r in rows[at + 1:] if any(_s(v) for v in r)])
    return out


def sjit_rows(book: dict, accounts: list[str]) -> tuple[list[str], dict[str, list[dict]], list[dict]]:
    """(the engine's headers, account -> its SJIT / FBM rows, the in-transit sheet's SJIT / FBM rows)."""
    head: list[str] = []
    per: dict[str, list[dict]] = {}
    for account in accounts:
        if account in book:
            head = head or book[account][0]
            per[account] = [r for r in book[account][1] if _s(r.get("model")).upper() in MODELS]
    transit = [r for r in book.get(TRANSIT_SHEET, ([], []))[1] if _s(r.get("model")).upper() in MODELS]
    return head, per, transit


# ------------------------------------------------------------------ the rows

def claim_status(row: dict, result: str, ticket: dict | None) -> str:
    """The PPMP master's CLAIM STATUS words, from the SJIT claim and what the bot found."""
    if ticket or result == tk.SJIT_RAISED or _s(row.get("TICKET ID")):
        return "CLAIM DONE"
    if _s(row.get("FINAL RETURN STATUS")):
        return "NON ELIGIBLE"
    if result in ELIGIBLE_RESULTS:
        return "ELIGIBLE"
    if result == tk.SJIT_YOUNG:
        return "UPCOMING CLAIM"
    return "NON ELIGIBLE"


def enrich(row: dict, account: str, today: date, items: dict, prev: dict, out: dict, tickets: dict,
           why_not: str) -> dict:
    """One master row with the SJIT claim columns."""
    oli = _id(row.get("order_line_id"))
    item = items.get((account, oli)) or {}
    old = prev.get((account, oli)) or {}
    core = item.get("core_item_id") or _s(old.get("FACT CORE ITEM ID"))
    done = out.get(account) or {}
    res = (done.get("results") or {}).get(core) or {}
    result = res.get("result") or (done.get("reasons") or {}).get(core) or ""
    if not result and core and account not in out and why_not:
        result = f"NOT CHECKED TODAY ({why_not})"
    if not result:
        result = _s(old.get("BOT RESULT")) or ("" if core else NO_CORE)
    ticket = tickets.get((account, core)) or tickets.get((account, oli))
    row = {k: _v(v) for k, v in row.items()}
    row.update({"FACT CORE ITEM ID": core or None, "MYNTRA STOCK": res.get("stock") or _s(old.get("MYNTRA STOCK")) or None,
                "LAST CHECKED": res.get("checked") or _s(old.get("LAST CHECKED")) or None, "BOT RESULT": result or None,
                "BOT JOB": str(res["job"]) if res.get("job") else (_s(old.get("BOT JOB")) or None)})
    status = claim_status(row, result, ticket)
    row["CLAIM STATUS"] = status
    if status in ("ELIGIBLE", "UPCOMING CLAIM") or result == tk.SJIT_RAISED:
        row["CLAIM TYPE"] = f"SJIT: {tk.CATEGORY_NAME[res.get('category') or tk.sjit_category()]}"
    if ticket:
        created = _day(ticket.get("CREATED_DAY"))
        start = _day(row.get("return_created_date"))
        _, hi = tk.sjit_window()
        row.update({"TICKET ID": ticket["TICKET ID"], "STATUS": ticket["STATUS"], "CLAIM TYPE": f"SJIT: {ticket['CATEGORY']}",
                    "REJECTION REASON": ticket.get("REASON") or row.get("REJECTION REASON"),
                    "CLAIM TAT": ("WITHIN TAT" if (created - start).days <= hi else "OUTSIDE TAT")
                    if created and start else row.get("CLAIM TAT")})
    if isinstance(row.get("return_created_date"), (date, datetime)):
        row["AGE (DAYS)"] = (today - _day(row["return_created_date"])).days
    return row


def short_row(account: str, item: dict, transit: bool) -> dict:
    """A row for an item of the SJIT returns report that the PPMP master does not have yet."""
    d = item.get("created")
    row = {"model": "SJIT", "order_line_id": _v(float(item["order_line_id"])) if item["order_line_id"].isdigit() else
           item["order_line_id"], "return_created_date": d, "RETURN MONTH": f"{d:%Y-%m}" if d else None,
           "type": item.get("type"), "status": item.get("status")}
    if transit:
        row["ACCOUNT"] = account
    return row


def ticket_rows(sjit: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for account, ts in sjit.items():
        for t in ts:
            created = tk._utc(t.get("createdOn"))
            rows.append({"ACCOUNT": account, "TICKET ID": _s(t.get("ticketId")), "ORDER LINE ID": _s(t.get("orderLineId")),
                         "RETURN ID": _s(t.get("returnId")), "ORDER ID": _s(t.get("orderId")),
                         "CATEGORY": tk.CATEGORY_NAME.get(t.get("issueCategory"), _s(t.get("issueCategory"))),
                         "STATUS": _s(t.get("status")), "CREATED": tk._when(created), "CREATED_DAY": created,
                         "LAST UPDATED": tk._when(tk._utc(t.get("lastModifiedOn"))),
                         "REASON": _s(t.get("rejectReasonDescription") or t.get("rejectReason") or t.get("validationReason")),
                         "COMPENSATION": t.get("compensationAmount"), "UTR": _s(t.get("utr")),
                         "PAYMENT INITIATED": _s(t.get("paymentInitiatedOn")), "DESCRIPTION": _s(t.get("description")),
                         "FACT CORE ITEM ID": _s(t.get("factCoreId"))})
    return sorted(rows, key=lambda r: r["TICKET ID"], reverse=True)


# ------------------------------------------------------------------ summaries

def _blank_counts(cols: list[str]) -> dict:
    return {c: 0 for c in cols[2:]}


def summaries(per: dict[str, list[dict]], transit: list[dict], tix: list[dict], rows_by_core: dict) -> tuple:
    """(SUMMARY rows, DATE SUMMARY rows, CLAIM TAT rows), each account's block then its TOTAL row, then ALL."""
    month: dict[tuple, dict] = {}
    day: dict[tuple, dict] = {}
    for account, rows in per.items():
        for in_transit, src in ((False, rows), (True, [r for r in transit if r.get("ACCOUNT") == account])):
            for r in src:
                final, amt = _s(r.get("FINAL RETURN STATUS")), _num(r.get("ORDER AMOUNT"))
                m = month.setdefault((account, _s(r.get("RETURN MONTH"))), _blank_counts(SUMMARY_COLS))
                d = day.setdefault((account, _day(r.get("return_created_date"))), _blank_counts(DATE_COLS))
                for x in (m, d):
                    x["TOTAL RETURNS"] += 1
                    x["RETURN RECEIVED"] += final == "Return Received"
                    if not final:
                        k = "IN TRANSIT" if in_transit else "DELIVERED PENDING"
                        x[k] += 1
                        x[f"{k} AMT"] += amt
                    if r.get("CLAIM STATUS") == "ELIGIBLE":
                        x["ELIGIBLE CLAIMS"] += 1
                        x["ELIGIBLE CLAIM AMT"] += amt
                m["SPF / PAYMENT SETTLED"] += final in SETTLED
                m["UPCOMING CLAIM AMT"] += amt if r.get("CLAIM STATUS") == "UPCOMING CLAIM" else 0
                m["CLAIM DONE"] += r.get("CLAIM STATUS") == "CLAIM DONE"
                m["SPF PAID AMT"] += _num(r.get("SPF PAID"))
    tat: dict[tuple, dict] = {}
    _, hi = tk.sjit_window()
    for t in tix:
        created = t.get("CREATED_DAY")
        x = tat.setdefault((t["ACCOUNT"], f"{created:%Y-%m}" if created else ""), _blank_counts(TAT_COLS))
        row = rows_by_core.get((t["ACCOUNT"], t["FACT CORE ITEM ID"])) or rows_by_core.get((t["ACCOUNT"], t["ORDER LINE ID"])) or {}
        amt, start = _num(row.get("ORDER AMOUNT")), _day(row.get("return_created_date"))
        x["CLAIMS RAISED"] += 1
        x["CLAIM QTY"] += 1
        x["CLAIM AMT"] += amt
        k = "WITHIN TAT" if created and start and (created.date() - start).days <= hi else "OUTSIDE TAT"
        x[k] += 1
        x[f"{k} QTY"] += 1
        x[f"{k} AMT"] += amt
        status = t["STATUS"]
        for key, hit in (("ACCEPTED", status == "ACCEPT"), ("PAID", status in PAID), ("REJECTED", status == "REJECT"),
                         ("OPEN", status not in PAID | {"ACCEPT", "REJECT", "CLOSED"})):
            if hit:
                x[key] += 1
                x[f"{key} AMT"] += amt
        x["SPF PAID AMT"] += _num(t.get("COMPENSATION")) if status in PAID else 0
    return _blocks(month, SUMMARY_COLS), _blocks(day, DATE_COLS), _blocks(tat, TAT_COLS)


def _blocks(groups: dict[tuple, dict], cols: list[str]) -> list[tuple[str, dict]]:
    """[(kind, row)]: kind "" for a data row, "total" for an account's TOTAL, "gap", "all" for the GRAND TOTAL."""
    out, grand = [], _blank_counts(cols)
    for account in sorted({a for a, _ in groups}):
        total = _blank_counts(cols)
        for (a, key), x in sorted(((k, v) for k, v in groups.items() if k[0] == account),
                                  key=lambda kv: (kv[0][1] is None, kv[0][1] or "")):
            out.append(("", {cols[0]: a, cols[1]: key, **x}))
            for c in total:
                total[c] += x[c]
        out.append(("total", {cols[0]: account, cols[1]: "TOTAL", **total}))
        out.append(("gap", {}))
        for c in grand:
            grand[c] += total[c]
    out.append(("all", {cols[0]: "ALL", cols[1]: "GRAND TOTAL", **grand}))
    return out


# ------------------------------------------------------------------ writing

def write(dest: Path, account_head: list[str], per: dict[str, list[dict]], transit_head: list[str],
          transit: list[dict], sums: tuple, tix: list[dict], input_log: list[dict]) -> None:
    import xlsxwriter
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(dest), {"strings_to_numbers": False, "strings_to_formulas": False,
                                         "strings_to_urls": False, "nan_inf_to_errors": True})
    f = {"head": wb.add_format({"bold": True, "bg_color": YELLOW, "border": 1}),
         "plain_head": wb.add_format({"bold": True, "border": 1}),
         "sub": wb.add_format({"bold": True, "bg_color": BLUE, "num_format": "0.00"}),
         "total": wb.add_format({"bold": True, "bg_color": BLUE}),
         "total_amt": wb.add_format({"bold": True, "bg_color": BLUE, "num_format": "#,##0.00"}),
         "all": wb.add_format({"bold": True, "bg_color": YELLOW}),
         "all_amt": wb.add_format({"bold": True, "bg_color": YELLOW, "num_format": "#,##0.00"}),
         "day": wb.add_format({"num_format": "dd-mm-yyyy"}), "id": wb.add_format({"num_format": "0"}),
         "amt": wb.add_format({"num_format": "0.00"}), "money": wb.add_format({"num_format": "#,##0.00"})}

    def cell(ws, r, c, v, fmt=None):
        v = _v(v)
        if v is None:
            return
        if isinstance(v, datetime) or isinstance(v, date):
            d = v if isinstance(v, datetime) else datetime(v.year, v.month, v.day)
            ws.write_datetime(r, c, d.replace(tzinfo=None), fmt or f["day"])
        elif isinstance(v, bool):
            ws.write_boolean(r, c, v)
        elif isinstance(v, (int, float)):
            ws.write_number(r, c, v, fmt)
        else:
            ws.write_string(r, c, str(v), fmt)

    def summary(name, cols, blocks):
        ws = wb.add_worksheet(name)
        for c, h in enumerate(cols):
            ws.write_string(0, c, h, f["head"])
        r = 0
        for kind, row in blocks:
            r += 1
            if kind == "gap":
                continue
            for c, h in enumerate(cols):
                money = h.endswith("AMT")
                fmt = {"total": f["total_amt"] if money else f["total"], "all": f["all_amt"] if money else f["all"]}.get(
                    kind, f["money"] if money else None)
                cell(ws, r, c, row.get(h), fmt)
        ws.freeze_panes(1, 2)
        ws.set_column(0, 1, 12.7)
        ws.set_column(2, len(cols) - 1, 19.7 if name != "CLAIM TAT" else 15.7)

    def master_sheet(name, head, rows):
        ws = wb.add_worksheet(name)
        cols = head + [c for c in SJIT_COLS if c not in head]
        yellow = set(head[head.index(YELLOW_FROM):head.index(YELLOW_TO) + 1]) if YELLOW_FROM in head and YELLOW_TO in head else set()
        yellow |= set(SJIT_COLS)
        ws.set_row(0, 18)
        ws.set_row(1, 18)
        for c, h in enumerate(cols):
            ws.write_string(1, c, h, f["head"] if h in yellow else f["plain_head"])
            ws.set_column(c, c, WIDTHS.get(h, 13.0))
            if h in SUBTOTAL_COLS:
                letter = xlsxwriter.utility.xl_col_to_name(c)
                total = round(sum(_num(r.get(h)) for r in rows), 2)
                ws.write_formula(0, c, f"=SUBTOTAL(9,{letter}3:{letter}{len(rows) + 2})", f["sub"], total)
        for r, row in enumerate(rows, 2):
            for c, h in enumerate(cols):
                fmt = f["id"] if h in ID_COLS else f["amt"] if h in AMOUNT_COLS else None
                cell(ws, r, c, row.get(h), fmt)
        ws.freeze_panes(2, 0)
        ws.autofilter(1, 0, max(1, len(rows) + 1), len(cols) - 1)

    def table(name, cols, rows, freeze=(1, 2), widths=None):
        ws = wb.add_worksheet(name)
        for c, h in enumerate(cols):
            ws.write_string(0, c, h, f["head"])
            ws.set_column(c, c, (widths or {}).get(h, 14.7))
        for r, row in enumerate(rows, 1):
            for c, h in enumerate(cols):
                cell(ws, r, c, row.get(h))
        ws.freeze_panes(*freeze)
        ws.autofilter(0, 0, max(0, len(rows)), len(cols) - 1)

    summary("SUMMARY", SUMMARY_COLS, sums[0])
    summary("DATE SUMMARY", DATE_COLS, sums[1])
    summary("CLAIM TAT", TAT_COLS, sums[2])
    for account, rows in per.items():
        master_sheet(account, account_head, rows)
    master_sheet(TRANSIT_SHEET, transit_head, transit)
    table("TICKETS", TICKET_COLS, tix, widths={"ACCOUNT": 8.7, "TICKET ID": 11.7, "ORDER LINE ID": 14.7,
                                              "CATEGORY": 40.7, "CREATED": 17.7, "LAST UPDATED": 17.7,
                                              "REASON": 40.7, "DESCRIPTION": 40.7, "FACT CORE ITEM ID": 18.7})
    table("INPUT LOG", LOG_COLS, input_log, freeze=(1, 0), widths={"REPORT": 20.7, "FILE": 42.7})
    wb.close()


# ------------------------------------------------------------------ build / publish

def build(ppmp: Path, work: Path, today: date, sjit: dict[str, list[dict]], out: dict[str, dict], previous: Path | None,
          dest: Path, why_not: str = "") -> dict[str, dict]:
    """Write the SJIT master to dest from the PPMP master's SJIT / FBM rows; per account: items, eligible,
    claims. sjit: account -> its SJIT tickets; out: raise_due_claims' sjit_out; previous: the last SJIT master."""
    from .engine import SHEETS
    book = read_book(ppmp)
    accounts = list(SHEETS) + sorted(a for a in set(sjit) | {p.name for p in (work / "sjit").glob("*") if p.is_dir()}
                                     if a not in SHEETS)
    head, per, transit = sjit_rows(book, accounts)
    transit_head = book.get(TRANSIT_SHEET, (head + ["ACCOUNT"], []))[0]
    old = read_book(previous) if previous else {}
    prev: dict[tuple[str, str], dict] = {}
    for name, (_, rows) in old.items():
        if name not in accounts and name != TRANSIT_SHEET:
            continue
        for r in rows:
            if _s(r.get("FACT CORE ITEM ID")) and _id(r.get("order_line_id")):
                prev[(_s(r.get("ACCOUNT")) or name, _id(r.get("order_line_id")))] = r
    items: dict[tuple[str, str], dict] = {}
    input_log = list(old.get("INPUT LOG", ([], []))[1])
    for account in accounts:
        folder = work / "sjit" / account
        for r in tk.sjit_returns(folder):
            items[(account, r["order_line_id"])] = r
        for p in sorted(folder.glob("*")) if folder.exists() else []:
            m = FILE_DATES.search(p.name)
            input_log.append({"ACCOUNT": account, "REPORT": "SJIT RETURNS (70)", "FROM": m.group(1) if m else None,
                              "TO": m.group(2) if m else None, "FILE": p.name, "PROCESSED ON": f"{today:%d-%m-%Y}"})
    tix = ticket_rows(sjit)
    by_key: dict[tuple[str, str], dict] = {}
    for t in sorted(tix, key=lambda t: t["TICKET ID"]):         # the newest claim of an item wins
        for k in (t["FACT CORE ITEM ID"], t["ORDER LINE ID"]):
            if k:
                by_key[(t["ACCOUNT"], k)] = t
    seen: set[tuple[str, str]] = set()
    rows_by_core: dict[tuple[str, str], dict] = {}

    def done(account, row):
        seen.add((account, _id(row.get("order_line_id"))))
        for k in (_s(row.get("FACT CORE ITEM ID")), _id(row.get("order_line_id"))):
            if k:
                rows_by_core[(account, k)] = row
        return row

    per = {a: [done(a, enrich(r, a, today, items, prev, out, by_key, why_not)) for r in per.get(a, [])] for a in accounts}
    transit = [done(_s(r.get("ACCOUNT")), enrich(r, _s(r.get("ACCOUNT")), today, items, prev, out, by_key, why_not))
               for r in transit]
    for (account, oli), item in items.items():                   # in the SJIT report, not on the master yet
        if (account, oli) not in seen:
            row = short_row(account, item, transit=False)
            per.setdefault(account, []).append(done(account, enrich(row, account, today, items, prev, out, by_key, why_not)))
    for (account, oli), old_row in prev.items():                 # a short row of an earlier run stays
        if (account, oli) not in seen:
            row = {k: v for k, v in old_row.items() if k != "ACCOUNT"}
            per.setdefault(account, []).append(done(account, enrich(row, account, today, items, prev, out, by_key, why_not)))
    per = {a: rows for a, rows in per.items() if rows or a in SHEETS}
    write(dest, head or transit_head[:-1], per, transit_head, transit, summaries(per, transit, tix, rows_by_core), tix,
          input_log)
    stats = {}
    for account in per:
        rows = per[account] + [r for r in transit if r.get("ACCOUNT") == account]
        stats[account] = {"rows": len(rows), "eligible": sum(r.get("CLAIM STATUS") == "ELIGIBLE" for r in rows),
                          "claims": sum(t["ACCOUNT"] == account for t in tix)}
    log.info("SJIT master: %s", stats)
    return stats


def publish(work: Path, today: date, sjit: dict[str, list[dict]], out: dict[str, dict], notes: list[str],
            upload: bool, why_not: str = "", ppmp: Path | None = None) -> Path | None:
    """Build the SJIT master from the PPMP master (ppmp, default the run's) on the previous one from Drive, and
    put it back there (upload); a line in notes."""
    from ..core.config import output_dir
    from ..core.drive import SPF_CLAIMS, XLSX, agent_folder
    dest = work / SJIT_MASTER
    prev = work / "previous_sjit" / SJIT_MASTER
    folder = agent_folder(SPF_CLAIMS) if upload else None
    try:
        if folder:
            folder.download(SJIT_MASTER, prev)
        stats = build(ppmp or work / "MYNTRA SPF MASTER.xlsx", work, today, sjit, out, prev, dest, why_not)
    except Exception as exc:  # noqa: BLE001 - the PPMP master still goes out
        log.exception("SJIT master not built")
        notes.append(f"SJIT SPF master not built: {str(exc)[:100]}")
        return None
    (output_dir("myntra_spf") / SJIT_MASTER).write_bytes(dest.read_bytes())
    if folder:
        try:
            folder.put(dest, XLSX)
        except Exception as exc:  # noqa: BLE001
            log.exception("SJIT master not uploaded")
            notes.append(f"SJIT SPF master not uploaded: {str(exc)[:100]}")
    notes.append(f"SJIT SPF master ({SPF_CLAIMS}/{SJIT_MASTER}): "
                 + ", ".join(f"{a} {s['rows']} returns, {s['eligible']} eligible, {s['claims']} SJIT claims"
                             for a, s in stats.items()))
    return dest
