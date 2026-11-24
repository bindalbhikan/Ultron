"""MasterSheet (1 AM daily): MasterData of Drive AGENT WORK/MASTER SHEET/MasterSheet.xlsx rebuilt from OMSGuru's
channel listings, the portal ids filled (build.py). The owner's other sheets (Master Sku, Fabric Code, Launch Date &
Size Count, anything else) are written back as they are; the workbook is written anew (xlsxwriter), Drive keeps the
old versions. Every working reads the file through workings/core/master_sheet.py.

No sheet on a guess: when OMSGuru's export fails or has far fewer listings than the sheet (MASTER_SHEET_MIN_SHARE,
0.7), nothing is written and the run fails. When the Myntra listing reports cannot be read, the Myntra ids stay as
they were and the report names it.
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from ..core import clients, telegram
from ..core import master_sheet as ms
from ..core.app import run_bot
from ..core.config import num, output_dir
from ..core.tables import read_excel_text, read_text_csv
from ..core.xlsx import ACCENT2_HEADER, write_sheets
from . import build

log = logging.getLogger("bindal.master_sheet")

DATE_COLUMNS = {"LAUNCH DATE", "PORTAL LISTING DATE", build.REMOVED_ON, "DATE"}
DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T]00:00:00)?$")
WHOLE = re.compile(r"^[1-9]\d{0,14}$")


def typed(header: str, value):
    """A cell as the sheet had it: a day as a date in the date columns, a whole number (no leading 0, at most 15
    digits so Excel keeps it exact) as a number, anything else as text."""
    if value is None:
        return None
    if header in DATE_COLUMNS:
        m = DAY.match(value)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
    return int(value) if WHOLE.match(value) else value


def rows_of(df: pl.DataFrame) -> list[list]:
    heads = df.columns
    return [[typed(h, v) for h, v in zip(heads, row)] for row in df.iter_rows()]


def omsguru_listings(notes: list[str]) -> pl.DataFrame:
    """OMSGuru's mapped channel listings of its Active channels only (owner, 24 Nov 2026: a Paused / Disabled
    channel's listings go to REMOVED LISTINGS). The warehouse is chosen first, as the listing pages show its listings."""
    client = clients.omsguru()
    channels = client.channels(every=True)
    active = {c["id"] for c in channels if c["active"]}
    if not active:
        raise RuntimeError("OMSGuru's channel list gave no Active channel (nothing written)")
    warehouses = list(client.warehouses())
    if warehouses:
        client.set_warehouse(warehouses[0])
    df = read_text_csv(client.export_listings(wait_minutes=num("LISTING_EXPORT_WAIT_MINUTES", 15)))
    if not df.height:
        raise RuntimeError("OMSGuru's channel listing export came back empty")
    off = df.filter(~pl.col("Channel ID").str.strip_chars().is_in(sorted(active)))
    if off.height:
        status = {c["id"]: c["status"] for c in channels}
        names = (off.group_by("Channel ID").len().sort("Channel ID").rows())
        notes.append("Not active in OMSGuru, left out: " + ", ".join(
            f"{build.channel_of(cid, '')} {status.get(cid, '?').lower()} ({n:,})" for cid, n in names))
    return df.filter(pl.col("Channel ID").str.strip_chars().is_in(sorted(active)))


def portal_sheets(dest: Path, notes: list[str]) -> pl.DataFrame | None:
    """The owner's files in AGENT WORK/MASTER SHEET/PORTAL SHEET (xlsx, every sheet, or csv; columns named as
    MasterData's, the NEED DATA sheet filled in works as it is), oldest first so a newer file's row wins."""
    from ..core.drive import agent_folder
    folder = agent_folder(ms.FOLDER, ms.PORTAL_FOLDER, create=True)
    files = sorted(((name, meta) for name, meta in folder.children().items()
                    if name.lower().endswith((".xlsx", ".csv"))), key=lambda f: f[1].get("modifiedTime") or "")
    frames = []
    for name, meta in files:
        try:
            path = folder.cached(name, dest, meta)
            if name.lower().endswith(".csv"):
                frames.append(read_text_csv(path))
            else:
                from python_calamine import CalamineWorkbook
                frames += [read_excel_text(path, s) for s in CalamineWorkbook.from_path(str(path)).sheet_names]
        except Exception as exc:  # noqa: BLE001 - the other files still count
            notes.append(f"PORTAL SHEET {name} not read: {str(exc)[:80]}")
    given = build.given_rows(frames)
    if files:
        notes.append(f"PORTAL SHEET: {len(files)} file(s), {0 if given is None else given.height:,} listings")
    return given


def myntra_reports(dest: Path, notes: list[str]) -> dict[str, pl.DataFrame] | None:
    """Each Myntra account's listing report (the 9:30 AM myntra-reports job reused), or None when none was got."""
    from ..myntra_grouping.pipeline import latest_listings
    try:
        got = latest_listings(dest)
    except Exception as exc:  # noqa: BLE001 - the sheet still goes out, the Myntra ids as they were
        log.warning("Myntra listing reports not read: %s", exc)
        notes.append(f"Myntra listing reports not read ({str(exc)[:80]}): Myntra style ids / SKU codes left as they were")
        return None
    return {acc: read_text_csv(path) for acc, path in got.items()}


def flipkart_listing_file(dest: Path, notes: list[str]) -> pl.DataFrame | None:
    """The newest FLIPKART LISTING FILE <dd-MON-yy>.xlsx (flipkart-listing-file, 11 AM) of this or last month."""
    from ..core.drive import agent_folder
    from ..flipkart_price.listing_file import FOLDER
    try:
        root = agent_folder(*FOLDER)
        today = date.today()
        months = [today.replace(day=1), (today.replace(day=1) - timedelta(days=1)).replace(day=1)]
        best = None
        for m in months:
            folder = root.subfolder(f"{m:%b-%y}") if root else None
            for name, meta in (folder.children() if folder else {}).items():
                made = re.search(r"(\d{2}-[A-Z]{3}-\d{2})\.xlsx$", name, re.I)
                when = datetime.strptime(made[1].title(), "%d-%b-%y").date() if made else None
                if when and (best is None or when > best[0]):
                    best = (when, folder, name, meta)
            if best:
                break
        if best is None:
            raise RuntimeError("no listing file in AGENT WORK/FLIPKART/LISTING FILE")
        path = best[1].cached(best[2], dest, best[3])
        return read_excel_text(path, 0)
    except Exception as exc:  # noqa: BLE001 - the FSNs then come from the sheet and OMSGuru
        log.warning("Flipkart listing file not read: %s", exc)
        notes.append(f"Flipkart listing file not read ({str(exc)[:80]}): FSN from the sheet / OMSGuru")
        return None


def run(args) -> int:
    work = Path(tempfile.mkdtemp(prefix="master_sheet_"))
    notes: list[str] = []
    today = date.today()
    src = ms.download(work / "drive") if not args.file else Path(args.file)
    from python_calamine import CalamineWorkbook
    names = CalamineWorkbook.from_path(str(src)).sheet_names
    main, gone_sheet = ms.sheet_of(names, ms.SHEET), ms.sheet_of(names, ms.REMOVED)
    if main is None:
        raise RuntimeError(f"{ms.FILE} has no {ms.SHEET} sheet (sheets: {', '.join(names)})")
    old = read_excel_text(src, main)
    removed = read_excel_text(src, gone_sheet) if gone_sheet else None
    made = {ms.sheet_of(names, n) for n in (ms.SHEET, ms.REMOVED, ms.UNMAPPED, ms.NEED)}
    # the owner's own sheets, by their names in capitals (owner, 24 Nov 2026: "MASTER SKU", "FABRIC CODE" ...)
    own = {n: n.upper() for n in names if n not in made}
    others = {own[n]: read_excel_text(src, n) for n in own}
    log.info("%s: %d MASTER DATA rows, %d removed listings, sheets %s", ms.FILE, old.height,
             0 if removed is None else removed.height, list(others))

    export = omsguru_listings(notes)
    oms = build.from_omsguru(export)
    share = oms.height / max(old.height, 1)
    if share < num("MASTER_SHEET_MIN_SHARE", 0.7):
        raise RuntimeError(f"OMSGuru gave {oms.height} listings, the sheet has {old.height}: too few to rebuild on "
                           "(nothing written)")
    unknown = sorted({c for c in oms["Channel Name"].unique().to_list() if c not in build.CHANNELS.values()})
    if unknown:
        notes.append("New OMSGuru channels, named by OMSGuru: " + ", ".join(unknown))
    reports = myntra_reports(work / "myntra", notes)
    myntra = build.myntra_ids(reports) if reports is not None else None
    flipkart = flipkart_listing_file(work / "flipkart", notes)
    given = portal_sheets(work / "portal", notes) if not args.file else None
    data, gone, loose, counts = build.rebuild(old, removed, oms, others, myntra, today, flipkart, given)
    need = build.need_data(data)
    counts["need"] = need.height
    log.info("MasterData: %s", counts)

    out = output_dir("master_sheet") / ms.FILE
    sheets = [(ms.SHEET, data.columns, rows_of(data)), (ms.NEED, need.columns, rows_of(need)),
              (ms.UNMAPPED, loose.columns, rows_of(loose)), (ms.REMOVED, gone.columns, rows_of(gone))]
    # the owner's own sheets go back cell for cell, as their types were (a text "5" stays a text)
    for n, upper in own.items():
        raw = CalamineWorkbook.from_path(str(src)).get_sheet_by_name(n).to_python(skip_empty_area=False)
        while raw and all(v in ("", None) for v in raw[-1]):
            raw.pop()
        if raw:
            sheets.append((upper, [("" if v is None else v) for v in raw[0]], raw[1:]))
    write_sheets(work / ms.FILE, sheets, header_format=ACCENT2_HEADER, freeze=True, autofilter=True,
                 column_widths=[(0, 25, 20)])
    shutil.copy2(work / ms.FILE, out)
    if not args.no_upload and not args.file:
        from ..core.drive import XLSX, agent_folder
        agent_folder(ms.FOLDER).put(work / ms.FILE, XLSX)
    text = message(counts, notes, datetime.now())
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
    return 0


def message(c: dict, notes: list[str], now: datetime) -> str:
    lines = [f"🗂 MasterSheet updated from OMSGuru · {now:%d %b %Y %I:%M %p}",
             f"MasterData: {c['listings']:,} listings ({c['new']:,} new, {c['back']:,} back)",
             f"Removed from OMSGuru today: {c['removed_today']:,} (REMOVED LISTINGS: {c['removed_total']:,})",
             f"In a portal's listing file, not in OMSGuru: {c['unmapped']:,} (UNMAPPED LISTINGS)"]
    if c["no_brand"]:
        lines.append(f"Listings without a brand: {c['no_brand']:,}")
    if c.get("need"):
        lines.append(f"NEED DATA: {c['need']:,} listings with a value missing (fill them, drop the file in "
                     f"MASTER SHEET / {ms.PORTAL_FOLDER})")
    if c["new_no_design"]:
        lines.append(f"New listings without DESIGN-NO: {c['new_no_design']:,} (add the style to Fabric Code)")
    lines += notes
    lines.append(f"📁 Drive: AGENT WORK / {ms.FOLDER} / {ms.FILE}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py master-sheet", description="MasterData of the SKU master from OMSGuru")
    p.add_argument("--no-upload", action="store_true", help="build it, do not save it on Drive")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    p.add_argument("--file", help="a local MasterSheet.xlsx to build on (nothing saved on Drive)")
    return run_bot("MasterSheet", p, run, argv)
