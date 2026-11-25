"""MYNTRA SJIT SPF MASTER.xlsx: the SJIT / FBM returns and their SPF claims, in their own file (owner, 25 Nov 2026:
not in the PPMP master), Drive AGENT WORK/SPF CLAIMS, rebuilt by every myntra-spf run.

  SUMMARY  per account: items, still out of Myntra's stock, claims raised / open / paid / rejected, amount paid
  ITEMS    one row per item (Fact Core Item ID) of the SJIT returns reports read so far: its return / RTO, what
           Myntra's SJIT tool said of it (MYNTRA STOCK), what the bot did (BOT RESULT) and its claim
  TICKETS  every SJIT claim on the portal

An item read once stays on ITEMS (its claim followed) after it leaves the report window. The bot owns the file:
an edit made on Drive is not kept.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from . import tickets as tk

log = logging.getLogger(__name__)

SJIT_MASTER = "MYNTRA SJIT SPF MASTER.xlsx"
ITEM_COLS = ["ACCOUNT", "FACT CORE ITEM ID", "ORDER LINE ID", "TYPE", "RETURN / RTO DATE", "AGE (DAYS)",
             "REPORT STATUS", "MYNTRA STOCK", "LAST CHECKED", "BOT RESULT", "BOT JOB", "TICKET ID", "CATEGORY",
             "CLAIM STATUS", "CLAIM CREATED", "CLAIM UPDATED", "COMPENSATION", "UTR"]
TICKET_COLS = ["ACCOUNT", "TICKET ID", "FACT CORE ITEM ID", "ORDER LINE ID", "CATEGORY", "STATUS", "CREATED",
               "LAST UPDATED", "COMPENSATION", "UTR"]
SUMMARY_COLS = ["ACCOUNT", "ITEMS", "IN CLAIM WINDOW", "OUT OF MYNTRA STOCK", "RAISED TODAY", "DUE NOT RAISED",
                "CLAIMS", "OPEN", "PAID", "REJECTED", "AMOUNT PAID"]
PAID = {"PAYMENT_COMPLETED", "PAYMENT_INITIATED", "INVOICE_CREATED", "INVOICE_INITIATED"}
CLOSED = {"REJECT", "CLOSED"} | PAID


def _s(v) -> str:
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


def _amount(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ticket_row(account: str, t: dict) -> dict:
    return {"ACCOUNT": account, "TICKET ID": _s(t.get("ticketId")), "FACT CORE ITEM ID": _s(t.get("factCoreId")),
            "ORDER LINE ID": _s(t.get("orderLineId")),
            "CATEGORY": tk.CATEGORY_NAME.get(t.get("issueCategory"), _s(t.get("issueCategory"))),
            "STATUS": _s(t.get("status")), "CREATED": tk._when(tk._utc(t.get("createdOn"))),
            "LAST UPDATED": tk._when(tk._utc(t.get("lastModifiedOn"))),
            "COMPENSATION": _amount(t.get("compensationAmount")), "UTR": _s(t.get("utr"))}


def read_previous(path: Path) -> dict[tuple[str, str], dict]:
    """The previous file's ITEMS rows by (account, core id); none when there is no file."""
    import polars as pl
    if not path.exists():
        return {}
    try:
        df = pl.read_excel(path, sheet_name="ITEMS", infer_schema_length=0)
    except Exception as exc:  # noqa: BLE001 - a fresh file then
        log.warning("Previous SJIT master not read: %s", exc)
        return {}
    return {(_s(r.get("ACCOUNT")), _s(r.get("FACT CORE ITEM ID"))): r for r in df.iter_rows(named=True)
            if _s(r.get("FACT CORE ITEM ID"))}


def build(work: Path, today: date, sjit: dict[str, list[dict]], out: dict[str, dict],
          previous: dict[tuple[str, str], dict], dest: Path, why_not: str = "") -> dict[str, dict]:
    """Write the SJIT master to dest; the SUMMARY numbers per account. sjit: account -> its SJIT tickets (the
    accounts read this run); out: raise_due_claims' sjit_out; why_not: why no item was checked today."""
    from ..core.xlsx import write_sheets
    lo, hi = tk.sjit_window()
    items: dict[tuple[str, str], dict] = {}
    for key, old in previous.items():                      # what earlier runs knew, then today's report on top
        items[key] = {c: old.get(c) for c in ITEM_COLS}
        items[key]["RETURN / RTO DATE"] = _day(old.get("RETURN / RTO DATE"))
    accounts = sorted(set(sjit) | {a for a, _ in items} | {p.name for p in (work / "sjit").glob("*") if p.is_dir()})
    for account in accounts:
        done = out.get(account, {})
        reasons, results = done.get("reasons", {}), done.get("results", {})
        for r in tk.sjit_returns(work / "sjit" / account):
            key = (account, r["core_item_id"])
            row = items.setdefault(key, {c: None for c in ITEM_COLS})
            row.update({"ACCOUNT": account, "FACT CORE ITEM ID": r["core_item_id"], "ORDER LINE ID": r["order_line_id"],
                        "TYPE": r["type"], "RETURN / RTO DATE": r["created"], "REPORT STATUS": r["status"]})
            if r["core_item_id"] in results:
                res = results[r["core_item_id"]]
                row.update({"BOT RESULT": res.get("result"), "MYNTRA STOCK": res.get("stock") or row.get("MYNTRA STOCK"),
                            "LAST CHECKED": res.get("checked") or row.get("LAST CHECKED")})
                if res.get("job"):
                    row["BOT JOB"] = str(res["job"])
            elif reasons.get(r["core_item_id"]):
                row["BOT RESULT"] = reasons[r["core_item_id"]]
            elif why_not:
                row["BOT RESULT"] = f"NOT CHECKED TODAY ({why_not})"
    # claims: from the portal's SJIT tickets, newest per item
    ticket_rows = []
    by_core: dict[tuple[str, str], dict] = {}
    for account, rows in sjit.items():
        for t in sorted(rows, key=lambda t: _s(t.get("createdOn"))):
            tr = ticket_row(account, t)
            ticket_rows.append(tr)
            for k in (tr["FACT CORE ITEM ID"], tr["ORDER LINE ID"]):
                if k:
                    by_core[(account, k)] = tr
    for (account, core), row in items.items():
        tr = by_core.get((account, core)) or by_core.get((account, _s(row.get("ORDER LINE ID"))))
        if tr:
            row.update({"TICKET ID": tr["TICKET ID"], "CATEGORY": tr["CATEGORY"], "CLAIM STATUS": tr["STATUS"],
                        "CLAIM CREATED": tr["CREATED"], "CLAIM UPDATED": tr["LAST UPDATED"],
                        "COMPENSATION": tr["COMPENSATION"], "UTR": tr["UTR"]})
        d = row.get("RETURN / RTO DATE")
        row["AGE (DAYS)"] = (today - d).days if isinstance(d, date) else None
    # per account, newest return first
    rows = sorted(items.values(), key=lambda r: (_s(r["ACCOUNT"]), r["AGE (DAYS)"] if r["AGE (DAYS)"] is not None
                                                 else 10**6, _s(r["FACT CORE ITEM ID"])))
    summary: dict[str, dict] = {}
    for r in rows:
        s = summary.setdefault(r["ACCOUNT"], {c: 0 for c in SUMMARY_COLS[1:]})
        s["ITEMS"] += 1
        age = r["AGE (DAYS)"]
        s["IN CLAIM WINDOW"] += bool(age is not None and lo <= age <= hi)
        s["OUT OF MYNTRA STOCK"] += _s(r.get("MYNTRA STOCK")) == "SHIPPED"
        s["RAISED TODAY"] += r.get("BOT RESULT") == tk.SJIT_RAISED and _s(r.get("LAST CHECKED")).startswith(f"{today:%d-%b-%Y}")
        s["DUE NOT RAISED"] += r.get("BOT RESULT") in (tk.SJIT_DUE, tk.SJIT_NOT_RAISED)
    for tr in ticket_rows:
        s = summary.setdefault(tr["ACCOUNT"], {c: 0 for c in SUMMARY_COLS[1:]})
        s["CLAIMS"] += 1
        s["OPEN"] += tr["STATUS"] not in CLOSED
        s["PAID"] += tr["STATUS"] in PAID
        s["REJECTED"] += tr["STATUS"] == "REJECT"
        s["AMOUNT PAID"] += (tr["COMPENSATION"] or 0) if tr["STATUS"] in PAID else 0
    write_sheets(dest, {
        "SUMMARY": (SUMMARY_COLS, [{"ACCOUNT": a, **s} for a, s in sorted(summary.items())]),
        "ITEMS": (ITEM_COLS, rows),
        "TICKETS": (TICKET_COLS, sorted(ticket_rows, key=lambda t: t["TICKET ID"], reverse=True)),
    }, bold_header=True, freeze=True, autofilter=True, auto_width=True, max_width=40)
    log.info("SJIT master: %d items, %d SJIT claims", len(rows), len(ticket_rows))
    return summary


def publish(work: Path, today: date, sjit: dict[str, list[dict]], out: dict[str, dict], notes: list[str],
            upload: bool, why_not: str = "") -> Path | None:
    """Build the SJIT master on the previous one from Drive and put it back there (upload); a line in notes."""
    from ..core.config import output_dir
    from ..core.drive import SPF_CLAIMS, XLSX, agent_folder
    dest = work / SJIT_MASTER
    prev = work / "previous_sjit" / SJIT_MASTER
    folder = agent_folder(SPF_CLAIMS) if upload else None
    try:
        if folder:
            folder.download(SJIT_MASTER, prev)
        summary = build(work, today, sjit, out, read_previous(prev), dest, why_not)
    except Exception as exc:  # noqa: BLE001 - the PPMP master still goes out
        log.exception("SJIT master not built")
        notes.append(f"SJIT SPF master not built: {str(exc)[:100]}")
        return None
    out_dir = output_dir("myntra_spf")
    (out_dir / SJIT_MASTER).write_bytes(dest.read_bytes())
    if folder:
        try:
            folder.put(dest, XLSX)
        except Exception as exc:  # noqa: BLE001
            log.exception("SJIT master not uploaded")
            notes.append(f"SJIT SPF master not uploaded: {str(exc)[:100]}")
    claims = sum(s["CLAIMS"] for s in summary.values())
    out_of_stock = sum(s["OUT OF MYNTRA STOCK"] for s in summary.values())
    notes.append(f"SJIT SPF master ({SPF_CLAIMS}/{SJIT_MASTER}): {sum(s['ITEMS'] for s in summary.values())} items, "
                 f"{out_of_stock} out of Myntra stock, {claims} SJIT claims")
    return dest
