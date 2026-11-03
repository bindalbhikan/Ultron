"""Portal sale report (the real sale): PORTAL SALE REPORT.xlsx, the layout of SALE REPORT.xlsx, but every
row is an ORDER date: that day's orders, and how many of those same orders were returned or cancelled,
whenever that happened. NET is what really stayed sold. The paper register plays no part.

It reuses what is already fetched: the PORTAL REPORTS month files, the Myntra order jobs the SPF working
asks for every morning. AJIO downloads and the OMSGuru order list answer at once. Only Flipkart has no
daily fetch to reuse: its Orders report is asked for once a day, with a short wait. That report runs about
two days behind, so its newest days come from OMSGuru (FLIPKART) and Seller Hub metrics (FBF) until it
reaches them.

A day's returns keep coming for weeks, so the daily run rewrites the last 60 days; the newest are not
final. A source that fails or stops short is left out and named: its cells stay as they are, never 0.
"""
from __future__ import annotations

import argparse
import calendar
import copy
import logging
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import csv_list, env, num, output_dir
from ..core.drive import API, DriveFile, DriveFolder
from ..core.files import replace_atomically
from ..sale.oms_sales import block_for
from ..sale.workbook import SaleWorkbook
from . import numbers as n

BOOK_NAME = "PORTAL SALE REPORT.xlsx"
ACCOUNTS = ("MAIN", "DBCC", "FMCC")
BLOCKS = ["AZ/FX/FBA", "COCOBLU", "MEESHO", "AJIO B2C", "FLIPKART", "FBF", "MYNTRA", "SJIT", "NYKAA"]
OMS_BLOCKS = {"AZ/FX/FBA", "COCOBLU", "MEESHO", "NYKAA"}
METRICS = ("GROSS", "RETURN", "CANCEL")
SUMMARY_SHEET, SOURCES_SHEET, CHECK_SHEET = "MONTHLY SUMMARY", "SOURCES", "PAPER CHECK"
OMS_TEXT = ("OMSGuru order list by order date: every line", "Return Init, Return Received, Partial Return Received",
            "Cancelled, Cancelled Before Shipping, Cancel Init, Cancelled Return Received")
SOURCE_ROWS = [
    ("MYNTRA", "Seller_Orders_Report, PPMP, MAIN + DBCC + FMCC, by created on", "an RTO or a return creation date", "status F"),
    ("SJIT", "The same report, FBM / SJIT lines", "an RTO or a return creation date", "status F"),
    ("AJIO B2C", "Dropship order report by order date: Order Qty", "RTV lines of those orders, without cancelled pickups", "Cancelled Qty"),
    ("FLIPKART", "Flipkart Orders, Non FBF, by order date", "RETURNED, RETURN_REQUESTED", "CANCELLED"),
    ("FBF", "Flipkart Orders, FBF, by order date", "RETURNED, RETURN_REQUESTED", "CANCELLED"),
    *((block, *OMS_TEXT) for block in ("AZ/FX/FBA", "COCOBLU", "MEESHO", "NYKAA")),
]
log = logging.getLogger("bindal.portal_sale")


@dataclass
class Numbers:
    """One source's units per order day, and the days each of its blocks can be trusted for."""
    values: dict[str, Counter] = field(default_factory=lambda: {m: Counter() for m in METRICS})
    covered: dict[str, set[date]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    blank: set[tuple[date, str, str]] = field(default_factory=set)      # (day, block, metric) the source cannot know

    def add(self, counted: dict[str, Counter]) -> None:
        for metric, counter in counted.items():
            self.values[metric].update(counter)

    def cover(self, blocks, days) -> None:
        for block in blocks:
            self.covered.setdefault(block, set()).update(days)


def span(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def month_chunks(first: date, last: date) -> list[tuple[date, date]]:
    """first..last cut at the month ends."""
    out, start = [], first
    while start <= last:
        end = min(start.replace(day=calendar.monthrange(start.year, start.month)[1]), last)
        out.append((start, end))
        start = end + timedelta(days=1)
    return out


def pieces(first: date, last: date, days: int = 30) -> list[tuple[date, date]]:
    """first..last in pieces of at most `days` (AJIO's and Myntra's limit), ending at last."""
    out, stop = [], last
    while stop >= first:
        start = max(first, stop - timedelta(days=days - 1))
        out.append((start, stop))
        stop = start - timedelta(days=1)
    return list(reversed(out))


def month_file(portal: str, kind: str, first: date, last: date, dest: Path, account: str = "",
               partial_ok: bool = False) -> Path | None:
    """The month's report from Drive PORTAL REPORTS, for a whole closed month; PARTIAL only on request."""
    whole = (first.day == 1 and (first.year, first.month) == (last.year, last.month)
             and last.day == calendar.monthrange(last.year, last.month)[1] and last < date.today())
    if not whole:
        return None
    files = pr.load(portal, first, kind, dest, account)
    if not files or ("PARTIAL" in files[0].name and not partial_ok):
        return None
    return files[0]


# ------------------------------------------------------------------ sources

def myntra_source(chunks, work: Path) -> Numbers:
    """All three accounts or nothing: one missing account would show MYNTRA too low. A job already on
    the portal for the same dates is only downloaded (the SPF working asks for the daily ones)."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    wait = int(num("RETURNS_WAIT_MINUTES", 45))

    def one_account(account: str) -> list[dict[str, Counter]]:
        dest = work / "myntra" / account
        dest.mkdir(parents=True, exist_ok=True)
        portal, got = None, []
        for first, last in chunks:
            path = month_file("MYNTRA", "sale", first, last, dest, account)
            if path is None:
                portal = portal or myntra_portal(account)
                name, data = portal.collect_or_regenerate(portal.ensure(mp.REPORT_ID, first, last), wait)
                path = dest / f"{first}_{Path(name).name}"
                path.write_bytes(data)
            got.append(n.myntra_orders(n.read_report(path, "order status")))
        if portal:
            mp.save_to_worker(env, portal.cookies(), account)
        log.info("Myntra %s read", account)
        return got

    out = Numbers()
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as pool:
        for got in pool.map(one_account, ACCOUNTS):         # raises when an account failed
            for counted in got:
                out.add(counted)
    out.cover(("MYNTRA", "SJIT"), [d for first, last in chunks for d in span(first, last)])
    return out


def ajio_source(chunks, returns_to: date, work: Path) -> Numbers:
    """The RTV files run on to the latest day: the returns of an order come after it."""
    from ..portals.ajio import AjioClient
    out = Numbers()
    dest = work / "ajio"
    dest.mkdir(parents=True, exist_ok=True)
    client = None

    def report(kind: str, fetch: str, first: date, last: date) -> Path:
        nonlocal client
        have = month_file("AJIO", kind, first, last, dest)
        if have:
            return have
        if client is None:
            client = AjioClient(env("AJIO_USERNAME"), env("AJIO_PASSWORD"))
            client.login()
        path = dest / f"{kind}_{first}.xlsx"
        path.write_bytes(getattr(client, fetch)(first, last))
        return path

    start = min(first for first, _ in chunks)
    whole = month_chunks(start, returns_to) if start.day == 1 else pieces(start, returns_to)
    rtv = pd.concat([n.read_report(report("return", "rtv_report", a, b), "return created date") for a, b in whole])
    days = []
    for first, last in chunks:
        orders = n.read_report(report("sale", "order_report", first, last), "cancelled qty")
        out.add(n.ajio_orders(orders, rtv))
        days += span(first, last)
    out.cover(("AJIO B2C",), days)
    return out


def flipkart_source(chunks, work: Path, live: bool) -> Numbers:
    """Back-fill: only saved files, PARTIAL up to its last day. Daily (live): no other working fetches
    Orders, so it is asked for once with a short wait; a failure is named, not waited out."""
    from ..return_analysis.sources import flipkart_client
    wait = int(num("PORTAL_SALE_FLIPKART_WAIT", 30))
    out = Numbers()
    dest = work / "flipkart"
    dest.mkdir(parents=True, exist_ok=True)
    client = None
    for first, last in chunks:
        path = month_file("FLIPKART", "sale", first, last, dest, partial_ok=not live)
        if path is None and live:
            client = client or flipkart_client()
            name, data = client.report("Orders", first, last, wait)
            path = dest / f"{first}_{Path(name).name}"
            path.write_bytes(data)
        if path is None:
            out.notes.append(f"Flipkart Orders {first:%b-%y}: no file, left out")
            continue
        counted = n.flipkart_orders(n.read_report(path, "order_item_status"))
        out.add(counted)
        seen = n.last_day(counted)
        if seen is None or seen < first:
            out.notes.append(f"Flipkart Orders {first:%b-%y}: no rows, left out")
            continue
        through = min(seen, last)
        if through < last:
            out.notes.append(f"Flipkart Orders {first:%d %b} to {last:%d %b} stops at {through:%d %b}")
        out.cover(("FLIPKART", "FBF"), span(first, through))
    return out


def day_range(days: list[date]) -> str:
    return f"{days[0]:%d %b}" if len(days) == 1 else f"{days[0]:%d %b} to {days[-1]:%d %b}"


def flipkart_latest(src: Numbers, write_days: list[date], notes: list[str]) -> None:
    """The days after the Orders report's last one: FLIPKART from OMSGuru, FBF from Seller Hub metrics, which
    has no returns (those cells stay empty). A day with no units is left out, not shown as 0. The next run
    overwrites these once the Orders report reaches them. Run after the other sources: OMSGuru gets one login at a time."""
    covered = src.covered.get("FLIPKART")
    days = [d for d in write_days if covered and d > max(covered)]
    if not days:
        return
    try:
        oms = oms_source(days, {"FLIPKART"})
        got = [d for d in days if oms.values["GROSS"][(d, "FLIPKART")] > 0]
        for metric in METRICS:
            src.values[metric].update({(d, "FLIPKART"): oms.values[metric][(d, "FLIPKART")] for d in got})
        src.cover(("FLIPKART",), got)
        if got:
            notes.append(f"FLIPKART {day_range(got)}: from OMSGuru until the Orders report reaches it")
    except Exception as exc:  # noqa: BLE001 - these days stay left out and named
        log.exception("Flipkart's latest days from OMSGuru failed")
        notes.append(f"FLIPKART latest days from OMSGuru failed: {str(exc)[:120]}")
    try:
        from ..return_analysis.sources import flipkart_client
        gross, cancel = flipkart_client().fbf_units(days, csv_list("FBF_LOCATIONS") or None)
        got = [d for d in days if gross[d] > 0]
        src.values["GROSS"].update({(d, "FBF"): gross[d] for d in got})
        src.values["CANCEL"].update({(d, "FBF"): cancel[d] for d in got})
        src.blank.update((d, "FBF", "RETURN") for d in got)
        src.cover(("FBF",), got)
        if got:
            notes.append(f"FBF {day_range(got)}: gross and cancel from Seller Hub, return empty until the Orders report reaches it")
    except Exception as exc:  # noqa: BLE001 - these days stay left out and named
        log.exception("FBF's latest days from Seller Hub failed")
        notes.append(f"FBF latest days from Seller Hub failed: {str(exc)[:120]}")


def oms_source(days: list[date], blocks: set[str] = OMS_BLOCKS) -> Numbers:
    from ultron.portals.omsguru import OmsGuruClient
    from ultron.portals.omsguru_orders import channel_names, order_lines_range
    out = Numbers()
    client = OmsGuruClient.from_env()
    client.login()
    client.set_warehouse(next(iter(client.warehouses())))       # the channel list needs a warehouse chosen
    names = channel_names(client)
    wanted = [cid for cid, name in names.items() if block_for(name) in blocks]
    keep = set(days)
    for first, last in month_chunks(min(days), max(days)):
        for line in order_lines_range(client, first, last, wanted):
            if line["day"] not in keep:
                continue
            block = block_for(names.get(line["channel"], ""))
            if block not in blocks:
                continue
            out.values["GROSS"][(line["day"], block)] += line["qty"]
            metric = n.oms_metric(line["status"])
            if metric:
                out.values[metric][(line["day"], block)] += line["qty"]
    out.cover(blocks, days)
    return out


# ------------------------------------------------------------------ workbook

def sale_folder(sale: DriveFile) -> DriveFolder:
    """The folder SALE REPORT.xlsx sits in: the portal report lives next to it."""
    r = sale.http.get(f"{API}/{sale.file_id}", params={"fields": "parents", "supportsAllDrives": "true"}, timeout=60)
    sale._check(r, "parents")
    return DriveFolder(r.json()["parents"][0], sale.http)


def new_book(sale_path: Path, path: Path) -> SaleWorkbook:
    """A new workbook with only the newest full 31-day sheet of SALE REPORT, emptied: the layout every
    month is copied from."""
    book = SaleWorkbook(sale_path)
    sheets = sorted(book._month_sheets(), key=lambda x: x[0], reverse=True)
    key, template = next((k, ws) for k, ws in sheets if len(book._day_rows(ws)) >= 31 and "COCOBLU" in book.layout(ws)[0])
    for ws in list(book.wb.worksheets):
        if ws is not template:
            book.wb.remove(ws)
    for name in list(book.wb.defined_names):
        del book.wb.defined_names[name]
    layout, _, _ = book.layout(template)
    for r in book._day_rows(template):
        for block, metrics in layout.items():
            if block != "TOTAL":
                for metric in METRICS:
                    if metric in metrics:
                        template.cell(r, metrics[metric]).value = None
    book.path = path
    log.info("New %s from the %04d-%02d layout of SALE REPORT", BOOK_NAME, *key)
    return book


def target_column(ws) -> int | None:
    return next((c for c in range(1, ws.max_column + 1) if str(ws.cell(3, c).value or "").strip().upper() == "TARGET"), None)


def copy_target(book: SaleWorkbook, sale: SaleWorkbook, year: int, month: int) -> None:
    """The month's total TARGET spread over its days, as SALE REPORT's sheet of that month has it."""
    src = dict(sale._month_sheets()).get((year, month))
    ws = book.month_sheet(year, month)
    col = target_column(ws)
    if not col:
        return
    _, rows, total = book.layout(ws)
    src_col = target_column(src) if src is not None else None
    month_target = None
    if src_col:
        _, _, src_total = sale.layout(src)
        month_target = src.cell(src_total, src_col).value if src_total else None
    for r in rows.values():
        ws.cell(r, col).value = f"={month_target}/{len(rows)}" if isinstance(month_target, (int, float)) else None
    if total:
        ws.cell(total, col).value = month_target if isinstance(month_target, (int, float)) else None


def write_source(book: SaleWorkbook, src: Numbers, days: list[date], notes: list[str]) -> None:
    for block, covered in sorted(src.covered.items()):
        left = []
        for day in days:
            if day in covered:
                for metric in METRICS:
                    if (day, block, metric) not in src.blank:
                        book.write(day, block, metric, src.values[metric][(day, block)])
            else:
                left.append(day)
        if left:
            notes.append(f"{block} left out: {left[0]:%d %b} to {left[-1]:%d %b} ({len(left)} days)")


def month_totals(book: SaleWorkbook, ws, block: str) -> dict[str, int]:
    """GROSS / RETURN / CANCEL of the numbers typed in a month sheet's day rows."""
    layout, rows, _ = book.layout(ws)
    out = {}
    for metric in METRICS:
        col = layout.get(block, {}).get(metric)
        cells = [ws.cell(r, col).value for r in rows.values()] if col else []
        out[metric] = int(sum(v for v in cells if isinstance(v, (int, float))))
    return out


def write_summary(book: SaleWorkbook) -> None:
    """MONTHLY SUMMARY: a month sheet's layout with one row per month; every number links to that month's
    Total row."""
    wb = book.wb
    if SUMMARY_SHEET in wb.sheetnames:
        wb.remove(wb[SUMMARY_SHEET])
    months = sorted(book._month_sheets(), key=lambda x: x[0])
    ws = wb.copy_worksheet(months[-1][1])
    ws.title = SUMMARY_SHEET
    ws["A1"].value = "MONTHLY SUMMARY: sale, return, cancel and net of each month's orders"
    ws["A1"].number_format = "General"
    layout, rows, total_row = book.layout(months[-1][1])
    first = min(rows.values())
    target = target_column(ws)
    columns = [c for metrics in layout.values() for c in metrics.values()] + ([target] if target else [])
    last_row = first + len(months)          # the Total row
    styles = {c: copy.copy(ws.cell(total_row, c)._style) for c in range(1, ws.max_column + 1)}
    for r in range(first, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None
    for r, (_, month_ws) in zip(range(first, last_row), months):
        ws.cell(r, 1).value = month_ws.title
        ws.cell(r, 1).number_format = "General"
        month_total = book.layout(month_ws)[2]
        for c in columns:
            ws.cell(r, c).value = f"='{month_ws.title}'!{get_column_letter(c)}{month_total}"
    ws.cell(last_row, 1).value = "Total"
    for c in columns:
        ws.cell(last_row, c).value = f"=SUM({get_column_letter(c)}{first}:{get_column_letter(c)}{last_row - 1})"
    for c, style in styles.items():
        ws.cell(last_row, c)._style = style
    if ws.max_row > last_row:
        ws.delete_rows(last_row + 1, ws.max_row - last_row)
    ws.freeze_panes = f"B{first}"


def write_info_sheets(book: SaleWorkbook, sale: SaleWorkbook) -> None:
    """SOURCES (where each number comes from) and PAPER CHECK (month totals beside SALE REPORT's)."""
    wb = book.wb
    for name in (SOURCES_SHEET, CHECK_SHEET):
        if name in wb.sheetnames:
            wb.remove(wb[name])
    bold = Font(bold=True)
    ws = wb.create_sheet(SOURCES_SHEET)
    ws.append(["Channel", "GROSS", "RETURN", "CANCEL"])
    for row in SOURCE_ROWS:
        ws.append(list(row))
    ws.append([])
    ws.append(["Dates", "Every row is an order date: the orders of that day and what later happened to those same orders."])
    ws.append(["Not final", "Returns keep coming for weeks, so recent days rise until they settle. The daily run rewrites the last 60 days."])
    ws.append(["Latest days", "Flipkart's Orders report runs about two days behind: until it reaches a day, FLIPKART is from OMSGuru and FBF from Seller Hub metrics (gross and cancel, return empty)."])
    ws.append(["Empty cell", "The source failed or stopped short for that day: left out on purpose, not 0."])
    ws.append(["SALE REPORT", "Its RETURN and CANCEL are by the day a parcel came back, so PAPER CHECK differs by design; compare GROSS."])
    for cell in ws[1]:
        cell.font = bold
    for col, width in zip("ABCD", (14, 62, 62, 62)):
        ws.column_dimensions[col].width = width

    ws = wb.create_sheet(CHECK_SHEET)
    ws.append(["Month", "Channel", "SALE REPORT GROSS", "Real GROSS", "Difference", "Paper RETURN", "Real RETURN", "Paper CANCEL", "Real CANCEL"])
    for cell in ws[1]:
        cell.font = bold
    ours, theirs = dict(book._month_sheets()), dict(sale._month_sheets())
    for key, sheet in sorted(ours.items()):
        paper_sheet = theirs.get(key)
        totals = [0] * 6
        for block in BLOCKS:
            real = month_totals(book, sheet, block)
            paper = month_totals(sale, paper_sheet, block) if paper_sheet is not None else dict.fromkeys(METRICS, 0)
            line = [paper["GROSS"], real["GROSS"], paper["RETURN"], real["RETURN"], paper["CANCEL"], real["CANCEL"]]
            ws.append([sheet.title, block, line[0], line[1], line[1] - line[0], *line[2:]])
            totals = [a + b for a, b in zip(totals, line)]
        ws.append([sheet.title, "Total", totals[0], totals[1], totals[1] - totals[0], *totals[2:]])
        for cell in ws[ws.max_row]:
            cell.font = bold
    for col, width in zip("ABCDEFGHI", (10, 12, 18, 11, 11, 13, 12, 13, 12)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"


def tidy(book: SaleWorkbook) -> None:
    """Months in order, then the summary and info sheets; the newest month open."""
    wb = book.wb
    months = sorted(book._month_sheets(), key=lambda x: x[0])
    wb._sheets = [ws for _, ws in months] + [wb[name] for name in (SUMMARY_SHEET, SOURCES_SHEET, CHECK_SHEET)]
    for ws in wb.worksheets:
        ws.sheet_view.tabSelected = False
    wb.active = len(months) - 1
    wb.worksheets[len(months) - 1].sheet_view.tabSelected = True
    for _, ws in months:
        ws.freeze_panes = "B4"
        total = book.layout(ws)[2]
        for row in ws.iter_rows(min_row=(total or ws.max_row) + 1):     # the % row: Cocoblu had no sale before Oct 2026
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("=") and not cell.value.startswith("=IFERROR"):
                    cell.value = f"=IFERROR({cell.value[1:]},0)"


# ------------------------------------------------------------------ telegram

def report_text(book: SaleWorkbook, day: date, notes: list[str]) -> str:
    ws = dict(book._month_sheets()).get((day.year, day.month))
    lines = [f"{'Channel':<10}{'Gross':>6}{'Ret':>6}{'Cncl':>6}{'Net':>6}"]
    total = Counter()
    for block in BLOCKS:
        t = month_totals(book, ws, block)
        net = t["GROSS"] - t["RETURN"] - t["CANCEL"]
        total.update({**t, "NET": net})
        lines.append(f"{block[:10]:<10}{t['GROSS']:>6}{t['RETURN']:>6}{t['CANCEL']:>6}{net:>6}")
    lines.append(f"{'Total':<10}{total['GROSS']:>6}{total['RETURN']:>6}{total['CANCEL']:>6}{total['NET']:>6}")
    text = [f"🧾 <b>Real sale · {day:%B %Y}</b>", "<i>this month's orders and their returns + cancels so far (not final)</i>",
            "", "<pre>" + telegram.esc("\n".join(lines)) + "</pre>"]
    if notes:
        text += ["", "⚠️ <b>Notes</b>", *(f"• {telegram.esc(x)}" for x in notes)]
    return "\n".join(text)


# ------------------------------------------------------------------ main

def run(args) -> int:
    today = date.today()
    yesterday = today - timedelta(days=1)
    if args.from_date:
        start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.to_date, "%Y-%m-%d").date() if args.to_date else yesterday
        write_days, chunks, live = span(start, end), month_chunks(start, end), False
    else:
        from ..myntra_spf.pipeline import _windows
        from ..portals import myntra as mp
        chunks = _windows(today)[mp.REPORT_ID]      # the jobs the SPF working already asked for this morning
        write_days, live = span(chunks[0][0], chunks[-1][1]), True
    log.info("Writing %s..%s", write_days[0], write_days[-1])

    work = Path(tempfile.mkdtemp(prefix="portal_sale_"))
    sale_file = DriveFile(env("SALE_DRIVE_FILE_ID"))
    sale_path = sale_file.download(work / "SALE REPORT.xlsx")
    sale = SaleWorkbook(sale_path)
    folder = sale_folder(sale_file)
    path = work / BOOK_NAME
    book = SaleWorkbook(path) if folder.download(BOOK_NAME, path) else new_book(sale_path, path)

    months = sorted({(d.year, d.month) for d in write_days})
    for year, month in months:
        book.month_sheet(year, month)
        copy_target(book, sale, year, month)

    notes: list[str] = []
    flipkart_chunks = chunks if not live else [(write_days[0], write_days[-1])]
    tasks = {"Myntra": (myntra_source, (chunks, work)), "AJIO": (ajio_source, (chunks, yesterday, work)),
             "Flipkart": (flipkart_source, (flipkart_chunks, work, live)), "OMSGuru": (oms_source, (write_days,))}
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        running = {name: pool.submit(fn, *a) for name, (fn, a) in tasks.items()}
    done = 0
    for name, future in running.items():
        try:
            src = future.result()
        except Exception as exc:  # noqa: BLE001 - the others are still written; this one is named
            log.exception("%s failed", name)
            notes.append(f"{name} left out: {str(exc)[:160]}")
            continue
        notes += src.notes
        if name == "Flipkart" and live:
            flipkart_latest(src, write_days, notes)
        write_source(book, src, write_days, notes)
        done += 1
    if not done:
        raise RuntimeError("no source could be read; workbook left unchanged: " + "; ".join(notes))

    for year, month in months:
        book.repair_formulas(book.month_sheet(year, month))
    write_summary(book)
    write_info_sheets(book, sale)
    tidy(book)
    if args.no_upload:
        keep = output_dir("portal_sale") / BOOK_NAME
        replace_atomically(book.save, keep)
        log.info("Test run: saved %s, Drive not changed", keep)
    else:
        replace_atomically(book.save, path)
        folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        log.info("%s saved on Drive", BOOK_NAME)
    text = report_text(book, write_days[-1], notes)
    print(text) if args.no_telegram else telegram.send(text)
    for x in notes:
        log.warning(x)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py portal-sale", description="Portal sale report (order date, real sale)")
    p.add_argument("--from", dest="from_date", help="back-fill from saved files: first day, YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", help="back-fill: last day, YYYY-MM-DD (default yesterday)")
    p.add_argument("--no-upload", action="store_true", help="test run: saved under output/, Drive not changed")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    return run_bot("Portal sale report", p, run, argv)
