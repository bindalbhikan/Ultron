"""Myntra zero TD (every 2 hours 7 AM - 7 PM, Monday to Saturday): which styles of the MYNTRA ZERO TD
UPDATE SHEET are live on the buyer side (www.myntra.com) with stock and selling at MRP, i.e. with
no trade discount on.

The sheet (Drive AGENT WORK/MYNTRA/MYNTRA ZERO TD UPDATE SHEET.xlsx) has one tab per account and month,
"MAIN-SEP-26", "DBCC-SEP-26", "FMCC-SEP-26" (ARTICLE TYPE, BRAND, STYLE ID, MY SKU, FINAL SKU, COST,
LIQ STYLES); the last tab of each account is the one read. Every style is looked up on the buyer
side (spider.py). A style is
  ZERO TD       every size in stock sells at MRP
  PART ZERO TD  some sizes in stock sell at MRP, others with a discount
  DISCOUNTED    every size in stock sells below MRP
  OUT OF STOCK  no size can be bought
  NOT FOUND     not on Myntra
Telegram gets one message (per account the zero TD styles and their stock, the biggest ones) and
one workbook: a tab per account with its ZERO TD and PART ZERO TD styles, SUMMARY, and NOT CHECKED
when some styles had no answer. The workbook is also kept on Drive:
AGENT WORK/MYNTRA/MYNTRA ZERO TD SHEETS/OCT-26/26-10-26/ZERO TD 26-10-26 10.00 AM.xlsx.

Tables are Polars: the sheet read by pl.read_excel (calamine), the checks joined on STYLE ID; the workbook
written by xlsxwriter (a style id is a link to its page).
"""
from __future__ import annotations

from ..portals.myntra import ACCOUNTS as MYNTRA_ACCOUNTS  # the one account list
import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

import polars as pl

from ..core import telegram
from ..core.app import run_bot
from ..core.config import csv_list, env, num, output_dir

log = logging.getLogger("bindal.myntra_zero_td")

AREA = "MYNTRA"   # the agent's folder is kept by portal: AGENT WORK/MYNTRA (since 29 Oct 2026)
SOURCE = "MYNTRA ZERO TD UPDATE SHEET.xlsx"
FOLDER = "MYNTRA ZERO TD SHEETS"   # AGENT WORK/MYNTRA/<FOLDER>/<OCT-26>/<26-10-26>/ZERO TD 26-10-26 10.00 AM.xlsx
ACCOUNTS = list(MYNTRA_ACCOUNTS)
SHEET_COLUMNS = ["ARTICLE TYPE", "BRAND", "STYLE ID", "MY SKU", "FINAL SKU", "COST", "LIQ STYLES"]
CHECK_COLUMNS = ["STATUS", "MRP", "SELLING PRICE", "SIZES AT MRP", "STOCK AT MRP", "TOTAL STOCK",
                 "SELLER", "LINK"]
CHECK_SCHEMA = {"STYLE ID": pl.Int64, "STATUS": pl.Utf8, "MRP": pl.Float64, "SELLING PRICE": pl.Float64,
                "SIZES AT MRP": pl.Utf8, "STOCK AT MRP": pl.Int64, "TOTAL STOCK": pl.Int64, "SELLER": pl.Utf8,
                "LINK": pl.Utf8, "ERROR": pl.Utf8}
FLAGGED = ("ZERO TD", "PART ZERO TD")
ALL_TAB = "ALL ACCOUNTS"
TOP = 5               # styles named per account in the message
MAX_UNCHECKED = 0.05  # more styles than this without an answer fails the run
SKU = pl.coalesce("FINAL SKU", "MY SKU").alias("SKU")


def read_source(path: Path, accounts: list[str]) -> dict[str, pl.DataFrame]:
    """{account: its tab's rows (SHEET_COLUMNS), one per style id}; the last tab of each account wins."""
    tabs = pl.read_excel(path, sheet_id=0, engine="calamine", raise_if_empty=False)
    out: dict[str, pl.DataFrame] = {}
    for title, df in tabs.items():
        account = str(title).split("-")[0].strip().upper()
        if account not in accounts:
            continue
        df = df.rename({c: str(c).strip().upper() for c in df.columns})
        if "STYLE ID" not in df.columns:
            log.warning("Tab %s has no STYLE ID column: skipped", title)
            continue
        sid = pl.col("STYLE ID").cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False).cast(pl.Int64)
        df = (df.with_columns(sid.alias("STYLE ID")).filter(pl.col("STYLE ID").is_not_null())
                .unique("STYLE ID", keep="first", maintain_order=True))
        out[account] = df.select(*[pl.col(c) if c in df.columns else pl.lit(None).alias(c) for c in SHEET_COLUMNS])
        log.info("%s: %d styles from tab %s", account, out[account].height, title)
    missing = [a for a in accounts if a not in out]
    if len(missing) == len(accounts):
        raise RuntimeError(f"{SOURCE} has no tab of {', '.join(accounts)} (tabs: {', '.join(map(str, tabs))})")
    for a in missing:
        log.warning("%s has no %s tab", SOURCE, a)
    return out


def lookup(ids: list[int]) -> dict[int, dict | str]:
    """Each style's buyer-side answer: straight from www.myntra.com, and through the ULTRON app's Agent mode
    (core/phone.py, the Android app on a mobile line) when myntra.com refuses this machine (403 on
    GitHub's runners) or MYNTRA_ZERO_TD_VIA=phone. The phone answers the same "style" object,
    cut down to what check() reads."""
    from ..core import phone
    from .spider import fetch
    via = (env("MYNTRA_ZERO_TD_VIA") or "").lower()
    answers: dict[int, dict | str] = {}
    if via != "phone":
        answers = fetch(ids, num("MYNTRA_ZERO_TD_CONCURRENCY", 8))
        refused = sum(1 for a in answers.values() if a == "HTTP 403")
        if refused < len(ids) / 2:
            return answers
        log.warning("www.myntra.com refused this machine (%d of %d styles HTTP 403): asking the ULTRON app's Agent mode",
                    refused, len(ids))
    wait = num("MYNTRA_ZERO_TD_PHONE_MINUTES", 40)
    deadline = time.monotonic() + wait * 60
    got = phone.run_job("myntra_style", ids, wait_minutes=wait)
    answers = {i: got.get(str(i), "no answer from the phone") for i in ids}
    # the phone's line drops for a while (UnknownHostException) or myntra.com refuses a burst
    # (HTTP 403): the styles without an answer are asked for again after a pause
    for again in range(int(num("MYNTRA_ZERO_TD_PHONE_RETRIES", 2))):
        missing = [i for i, a in answers.items() if not isinstance(a, dict) and a != "NOT FOUND"]
        if not missing:
            break
        pause = 60 * (again + 1)
        if deadline - time.monotonic() <= pause:
            log.warning("Phone retry skipped: the shared lookup time budget is exhausted")
            break
        log.warning("%d styles without an answer from the phone: asking again in %d s", len(missing), pause)
        time.sleep(pause)
        try:
            got = phone.run_job("myntra_style", missing, wait_minutes=(deadline - time.monotonic()) / 60)
        except phone.PhoneUnavailable as exc:
            log.warning("Phone retry not done: %s", exc)
            break
        answers.update({i: got[str(i)] for i in missing if str(i) in got})
    return answers


def check(answer: dict | str) -> dict:
    """The CHECK_COLUMNS of one style from its buyer-side answer."""
    from .spider import sizes_in_stock
    if not isinstance(answer, dict):
        return {"STATUS": answer if answer == "NOT FOUND" else "NOT CHECKED", "ERROR": answer}
    sizes = sizes_in_stock(answer)
    at_mrp = [s for s in sizes if s["price"] >= s["mrp"] > 0]
    if not sizes:
        status = "OUT OF STOCK"
    elif len(at_mrp) == len(sizes):
        status = "ZERO TD"
    elif at_mrp:
        status = "PART ZERO TD"
    else:
        status = "DISCOUNTED"
    sellers = ", ".join(sorted({str(s.get("displayName") or s.get("sellerName") or "").strip()
                                for s in answer.get("sellers") or []} - {""}))
    return {"STATUS": status,
            "MRP": max((s["mrp"] for s in sizes), default=answer.get("mrp")),
            "SELLING PRICE": min((s["price"] for s in sizes), default=None),
            "SIZES AT MRP": ", ".join(s["size"] for s in at_mrp),
            "STOCK AT MRP": sum(s["stock"] for s in at_mrp),
            "TOTAL STOCK": sum(s["stock"] for s in sizes),
            "SELLER": sellers,
            "LINK": f"https://www.myntra.com/{answer.get('id')}"}


def with_checks(sheets: dict[str, pl.DataFrame], found: dict[int, dict]) -> dict[str, pl.DataFrame]:
    """Each style's sheet row with its check (CHECK_COLUMNS and ERROR; a field it has none of is empty)."""
    checks = pl.DataFrame([{"STYLE ID": i, **c} for i, c in found.items()], schema=CHECK_SCHEMA, strict=False)
    return {a: df.join(checks, on="STYLE ID", how="left", maintain_order="left") for a, df in sheets.items()}


def flagged_of(df: pl.DataFrame) -> pl.DataFrame:
    """The zero TD / part zero TD styles, most stock at MRP first (equal stock: the sheet's order)."""
    return df.filter(pl.col("STATUS").is_in(FLAGGED)).sort("STOCK AT MRP", descending=True, nulls_last=True,
                                                         maintain_order=True)


def write_tab(wb, name: str, df: pl.DataFrame, link: str | None, head, link_f, when_f):
    """One tab: a red header, the rows, the style id as a link to its page, filter, frozen header, widths."""
    ws = wb.add_worksheet(name)
    widths = [len(c) + 2 for c in df.columns]
    for j, c in enumerate(df.columns):
        ws.write_string(0, j, c, head)
    for i, row in enumerate(df.iter_rows(), start=1):
        for j, v in enumerate(row):
            if i < 200:
                widths[j] = max(widths[j], len(str(v or "")) + 2)
            if v is None or (isinstance(v, float) and v != v):
                continue
            if df.columns[j] == link:
                ws.write_url(i, j, f"https://www.myntra.com/{v}", link_f, string=str(v))
            elif isinstance(v, datetime):
                ws.write_datetime(i, j, v, when_f)
            elif isinstance(v, bool):
                ws.write_boolean(i, j, v)
            elif isinstance(v, (int, float)):
                ws.write_number(i, j, v)
            else:
                ws.write_string(i, j, str(v))
    for j, w in enumerate(widths):
        ws.set_column(j, j, min(45, max(10, w)))
    ws.freeze_panes(1, 0)
    if df.width:
        ws.autofilter(0, 0, df.height, df.width - 1)
    return ws


def write_workbook(path: Path, checked: dict[str, pl.DataFrame], when: datetime) -> Path:
    """The workbook sent on Telegram: SUMMARY, ALL ACCOUNTS (every account's zero TD styles together:
    STYLE ID, SKU, SELLING PRICE, each style once), a tab per account (its zero TD styles, most
    stock at MRP first) and NOT CHECKED."""
    import xlsxwriter
    summary = pl.DataFrame([summarise(a, df) for a, df in checked.items()])
    flagged = {a: flagged_of(df).select(SHEET_COLUMNS + CHECK_COLUMNS) for a, df in checked.items()}
    merged = (pl.concat(list(flagged.values()), how="diagonal_relaxed")
              .select("STYLE ID", SKU, "SELLING PRICE").unique("STYLE ID", keep="first", maintain_order=True))
    unchecked = pl.concat([df.filter(pl.col("STATUS") == "NOT CHECKED")
                             .select(pl.lit(a).alias("ACCOUNT"), "STYLE ID", "MY SKU", "ERROR")
                           for a, df in checked.items()], how="diagonal_relaxed")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "strings_to_formulas": False,
                                         "strings_to_urls": False, "nan_inf_to_errors": True})
    looks = (wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#C0392B", "pattern": 1}),
             wb.add_format({"font_color": "#0563C1", "underline": 1}), wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"}))
    ws = write_tab(wb, "SUMMARY", summary, None, *looks)
    ws.write_string(summary.height + 2, 0, f"Checked on www.myntra.com at {when:%d %b %Y %I:%M %p} IST")
    write_tab(wb, ALL_TAB, merged, "STYLE ID", *looks)
    for account, df in flagged.items():
        write_tab(wb, account, df, "STYLE ID", *looks)
    if unchecked.height:
        write_tab(wb, "NOT CHECKED", unchecked, None, *looks)
    wb.close()
    return path


def summarise(account: str, df: pl.DataFrame) -> dict:
    status = dict(df.group_by("STATUS").len().iter_rows())
    return {"ACCOUNT": account, "STYLES": df.height, "ZERO TD": status.get("ZERO TD", 0),
            "PART ZERO TD": status.get("PART ZERO TD", 0), "STOCK AT MRP": int(df["STOCK AT MRP"].fill_null(0).sum()),
            "DISCOUNTED": status.get("DISCOUNTED", 0), "OUT OF STOCK": status.get("OUT OF STOCK", 0),
            "NOT FOUND": status.get("NOT FOUND", 0), "NOT CHECKED": status.get("NOT CHECKED", 0)}


def message(checked: dict[str, pl.DataFrame], when: datetime) -> str:
    rows = [summarise(a, df) for a, df in checked.items()]
    flagged = sum(r["ZERO TD"] + r["PART ZERO TD"] for r in rows)
    out = [f"🏷 <b>Myntra zero TD · {when:%d %b, %I:%M %p}</b>", ""]
    out.append(f"⚠️ {flagged} styles live at MRP" if flagged else "✅ No style live at MRP")
    for r, (account, df) in zip(rows, checked.items()):
        n = r["ZERO TD"] + r["PART ZERO TD"]
        out += ["", f"<b>{account}</b>: {n} at MRP" + (f" ({r['PART ZERO TD']} some sizes)" if r["PART ZERO TD"] else "")
                + (f", {r['STOCK AT MRP']:,} pcs" if n else "")]
        for s in flagged_of(df).with_columns(SKU).head(TOP).iter_rows(named=True):
            sku = telegram.esc(str(s["SKU"] or "")[:22])
            out.append(f'• <a href="{s["LINK"]}">{s["STYLE ID"]}</a> {sku}: ₹{s["MRP"]:,.0f}, {int(s["STOCK AT MRP"]):,} pcs')
    checked_n = sum(r["STYLES"] - r["NOT CHECKED"] for r in rows)
    unchecked = sum(r["NOT CHECKED"] for r in rows)
    out += ["", f"🔎 {checked_n:,} styles checked on myntra.com"]
    if unchecked:
        out.append(f"⚠️ {unchecked} styles not checked (no answer)")
    if flagged:
        out.append("👉 Put the TD on these styles (sheet attached)")
    return "\n".join(out)


def file_name(when: datetime) -> str:
    """ZERO TD 26-10-26 10.00 AM.xlsx (no ":" - Windows does not allow it in a file name)."""
    return f"ZERO TD {when:%d-%m-%y %I.%M %p}.xlsx"


def save_to_drive(path: Path, when: datetime) -> str:
    """The workbook into AGENT WORK/MYNTRA/MYNTRA ZERO TD SHEETS/OCT-26/26-10-26/; the folder's link."""
    from ..core.drive import XLSX, agent_folder
    root = agent_folder(AREA, create=True)
    folder = (root.subfolder(FOLDER, create=True).subfolder(f"{when:%b-%y}".upper(), create=True)
              .subfolder(f"{when:%d-%m-%y}", create=True))
    folder.put(path, XLSX)
    return f"https://drive.google.com/drive/folders/{folder.folder_id}"


def run(args) -> int:
    import tempfile
    from collections import Counter
    accounts = [a.upper() for a in (csv_list("MYNTRA_ZERO_TD_ACCOUNTS") or ACCOUNTS)]
    if args.source:
        source = Path(args.source)
    else:
        from ..core.drive import agent_folder
        source = agent_folder(AREA, create=True).download(
            SOURCE, Path(tempfile.mkdtemp(prefix="zero_td_")) / SOURCE)
        if source is None:
            raise RuntimeError(f"{SOURCE} not found in AGENT WORK/MYNTRA on Drive")
    sheets = read_source(source, accounts)
    if args.limit:
        sheets = {a: df.head(args.limit) for a, df in sheets.items()}

    ids = sorted({i for df in sheets.values() for i in df["STYLE ID"].to_list()})
    log.info("Looking up %d styles on www.myntra.com", len(ids))
    answers = lookup(ids)
    found = {i: check(a) for i, a in answers.items()}
    unchecked = sum(1 for c in found.values() if c["STATUS"] == "NOT CHECKED")
    if unchecked == len(ids):
        errors = Counter(c["ERROR"] for c in found.values()).most_common(3)
        raise RuntimeError("www.myntra.com answered no style: " + "; ".join(f"{e} x{n}" for e, n in errors))

    checked = with_checks(sheets, found)
    when = datetime.now()
    path = write_workbook(output_dir("myntra-zero-td") / file_name(when), checked, when)
    msg = message(checked, when)
    if args.no_upload:
        log.info("Not saved to Drive (test run): %s", path)
    else:
        try:
            month = f"{when:%b-%y}".upper()
            msg += f'\n📁 <a href="{save_to_drive(path, when)}">{FOLDER} / {month} / {when:%d-%m-%y}</a>'
        except Exception as exc:  # noqa: BLE001 - the message and the sheet still go out on Telegram
            log.exception("%s not saved to Drive", path.name)
            msg += f"\n⚠️ Not saved to Drive: {telegram.esc(str(exc)[:150])}"
    if args.no_telegram:
        print(msg, f"\n{path}", sep="")
    else:
        telegram.send(msg)
        telegram.send_document(path, f"🏷 Myntra zero TD · {when:%d %b, %I:%M %p}")
    if unchecked > MAX_UNCHECKED * len(ids):
        log.error("%d of %d styles not checked", unchecked, len(ids))
        return 1
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py myntra-zero-td",
                                description="Styles live on www.myntra.com with stock at MRP (no TD), per account")
    p.add_argument("--source", help="a local copy of the sheet instead of the one on Drive")
    p.add_argument("--limit", type=int, default=0, help="only the first N styles of each account (a test)")
    p.add_argument("--no-upload", action="store_true", help="keep the workbook in output/, not on Drive")
    p.add_argument("--no-telegram", action="store_true", help="print the message instead of sending it")
    return run_bot("Myntra zero TD", p, run, argv)
