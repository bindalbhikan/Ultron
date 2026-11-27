"""MasterSheet (1 AM daily): MASTER DATA of Drive AGENT WORK/MASTER SHEET/MasterSheet.xlsx updated by the owner's own
OMSGuru mapping tool (legacy.py = G:/My Drive/BINDAL EXPORTS/OMSGURU MAPPING/update_master.py, line for line; owner,
26 Nov 2026: "ye old tool he same to same use kar lo").

Its input/ folder = the files in AGENT WORK/MASTER SHEET/PORTAL SHEET + OMSGuru's channel listing mapping export,
pulled fresh; its supporting/ files = the owner's sheets in the workbook (MASTER SKU = Final Sku Sheet, FABRIC CODE,
LAUNCH DATE & SIZE COUNT). The one rule on top (owner): a listing in OMSGuru's export stays in MASTER DATA (also one
the tool used to park for having no sized SKU); a listing not in it is kept and marked UNMAPPED in REMARK. Nothing
else. The workbook is written anew (xlsxwriter): MASTER DATA, PORTAL COMBINED, then the owner's sheets cell for cell
with their merged cells. Drive keeps the old versions. Every working reads the file through workings/core/master_sheet.py.

No sheet on a guess: OMSGuru's export failing, empty, or far smaller than the sheet (MASTER_SHEET_MIN_SHARE, 0.7)
fails the run with nothing written.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..core import clients, telegram
from ..core import master_sheet as ms
from ..core.app import run_bot
from ..core.config import num, output_dir
from ..core.xlsx import ACCENT2_HEADER, write_sheets
from . import legacy as L
from .xlcompat import load_workbook

log = logging.getLogger("bindal.master_sheet")

REMARK = "REMARK"
UNMAPPED = "UNMAPPED"
# the owner's names for the tool's two FINAL columns (24 Nov 2026), and its supporting files
SHEET_NAME = {"FINAL SKU": "MASTER SKU", "FINAL MY SKU": "MASTER STYLE CODE"}
TOOL_NAME = {v: k for k, v in SHEET_NAME.items()}
SUPPORTING = {"MASTER SKU": ("Final Sku Sheet.xlsx", {"MASTER SKU": "FINAL SIZE SKU", "MASTER STYLE CODE": "FINAL MY SKU"}),
              "FABRIC CODE": ("Fabric Code.xlsx", {}),
              "LAUNCH DATE & SIZE COUNT": ("Launch Dates.xlsx", {})}
OWN_SHEETS = ("MASTER SKU", "FABRIC CODE", "LAUNCH DATE & SIZE COUNT")
MADE = (ms.SHEET, ms.OLD_SHEET, "PORTAL COMBINED", ms.REMOVED, ms.UNMAPPED, ms.NEED)


def master_rows(path: Path) -> list[list]:
    """MASTER DATA (or the tool's own sheet Master) as the tool's read_master gives it: rows in MASTER_COLUMNS
    order, read by header, values as openpyxl had them."""
    wb = load_workbook(path)
    name = ms.sheet_of(wb.sheetnames, ms.SHEET) or ms.sheet_of(wb.sheetnames, ms.OLD_SHEET)
    if name is None:
        raise RuntimeError(f"{path.name} has no {ms.SHEET} sheet (sheets: {', '.join(wb.sheetnames)})")
    rows = wb[name].iter_rows(values_only=True)
    headers = [TOOL_NAME.get(L.text(v), L.text(v)) for v in next(rows, ())]
    if headers[:len(L.BASE_COLUMNS)] != list(L.BASE_COLUMNS):
        raise RuntimeError(f"Unexpected {name} columns: {headers}")
    target = {n: i for i, n in enumerate(L.MASTER_COLUMNS)}
    moves = [(s, target[n]) for s, n in enumerate(headers) if n in target]
    data = []
    for values in rows:
        row = [None] * len(L.MASTER_COLUMNS)
        for s, d in moves:
            if s < len(values):
                row[d] = values[s]
        data.append(row)
    wb.close()
    return data


def own_sheets(path: Path) -> list[tuple[str, list, list, list]]:
    """The owner's sheets of the workbook (every sheet the run does not make), cell for cell: (NAME IN CAPITALS,
    headers, rows, merged ranges)."""
    from python_calamine import CalamineWorkbook
    out = []
    with CalamineWorkbook.from_path(str(path)) as wb:
        for name in wb.sheet_names:
            if any(ms.sheet_of([name], m) for m in MADE):
                continue
            sheet = wb.get_sheet_by_name(name)
            raw = sheet.to_python(skip_empty_area=False)
            while raw and all(v in ("", None) for v in raw[-1]):
                raw.pop()
            headers = [("" if v is None else v) for v in raw[0]] if raw else []
            out.append((name.upper(), headers, raw[1:], list(sheet.merged_cell_ranges or [])))
    return out


def supporting_files(sheets, folder: Path, notes: list[str]) -> None:
    """The owner's MASTER SKU / FABRIC CODE / LAUNCH DATE sheets as the tool's supporting/ files (merges kept: a
    fabric code merged over a SKU group counts for every row)."""
    have = {name: (headers, rows, merges) for name, headers, rows, merges in sheets}
    for name, (file, rename) in SUPPORTING.items():
        if name not in have:
            notes.append(f"{ms.FILE} has no {name} sheet: the tool leaves those values as they are")
            continue
        headers, rows, merges = have[name]
        write_sheets(folder / file, [("Sheet1", [rename.get(str(h).strip().upper(), h) for h in headers], rows)],
                     merges={"Sheet1": merges})


def portal_inputs(folder: Path, notes: list[str]) -> list[str]:
    """The files in AGENT WORK/MASTER SHEET/PORTAL SHEET, into the tool's input/ folder; their names."""
    from ..core.drive import agent_folder
    portal = agent_folder(ms.FOLDER, ms.PORTAL_FOLDER, create=True)
    names = []
    for name, meta in sorted(portal.children().items()):
        if Path(name).suffix.lower() not in L.SUPPORTED_PORTAL_SUFFIXES | {".zip"}:
            continue
        try:
            got = portal.cached(name, folder, meta)
            if got and got.name != name:
                shutil.move(got, folder / name)
            names.append(name)
        except Exception as exc:  # noqa: BLE001 - the other files still count
            notes.append(f"PORTAL SHEET {name} not read: {str(exc)[:80]}")
    return names


def omsguru_export(folder: Path) -> Path:
    """OMSGuru's channel listing mapping export (every mapped listing, every channel), pulled fresh."""
    data = clients.omsguru().export_listings(wait_minutes=num("LISTING_EXPORT_WAIT_MINUTES", 15))
    if not data:
        raise RuntimeError("OMSGuru's channel listing export came back empty (nothing written)")
    path = folder / ("OMSGURU-MAPPING.zip" if data[:2] == b"PK" else "omsguru-channel_listing_mapping.csv")
    path.write_bytes(data)
    return path


def update(existing: list[list], inputs: Path, supporting: Path) -> dict:
    """The tool's run (update_master.main), step for step, plus the owner's rule: parked rows (in OMSGuru, no sized
    SKU) join MASTER DATA, a row OMSGuru does not carry is UNMAPPED. {rows, remarks, combined, counts}."""
    finals = L.FinalSkus(supporting / "Final Sku Sheet.xlsx")
    mapped, oms_rows = L.resolve_listings(inputs)
    new_rows, parked = L.build_master_rows(mapped, existing, finals)
    colors = L.ColorIndex(inputs)
    L.refresh_mapped_columns(existing, mapped)
    width = len(L.MASTER_COLUMNS)
    rows = existing + new_rows + [list(r) + [None] * (width - len(r)) for r in parked]
    L.sync_product_reference(rows, oms_rows)
    L.enforce_sku_rules(rows)
    L.apply_final_skus(rows, finals)
    L.apply_supporting_sheets(rows, supporting / "Fabric Code.xlsx", supporting / "Launch Dates.xlsx")
    L.fill_derived_columns(rows, inputs, colors)
    combined, _ = L.combined_portal_rows(inputs, colors)
    remarks = unmapped(rows, oms_rows)
    lid = L.MASTER_COLUMNS.index("Channel Listing Id")
    for row in rows:
        row[lid] = L.listing_id_value(row[lid])
    counts = {"listings": len(rows), "existing": len(existing), "new": len(new_rows), "parked": len(parked),
              "unmapped": sum(1 for r in remarks if r), "oms": len(oms_rows), "combined": len(combined)}
    return {"rows": rows, "remarks": remarks, "combined": combined, "counts": counts}


def unmapped(rows: list[list], oms_rows) -> list[str]:
    """REMARK per row: UNMAPPED when OMSGuru's export does not carry the listing, found as the tool finds a row in
    it (sync_product_reference): Channel Name + Channel Listing Id, else Channel Name + Channel Listing SKU Code."""
    ids, codes = set(), defaultdict(int)
    for _row, channel_sku, listing_id, channel, _product in oms_rows:
        label = L.channel_label(channel)
        ids.add(L.row_key(label, listing_id))
        if L.text(channel_sku):
            codes[(label, L.text(channel_sku).upper())] += 1
    out = []
    for row in rows:
        key = L.row_key(row[2], row[1])
        found = key in ids or (L.text(row[0]) and (key[0], L.text(row[0]).upper()) in codes)
        out.append("" if found else UNMAPPED)
    return out


def write(path: Path, result: dict, sheets) -> None:
    """MASTER DATA (the tool's columns under the owner's names + REMARK), PORTAL COMBINED, the owner's sheets."""
    headers = [SHEET_NAME.get(c, c) for c in L.MASTER_COLUMNS] + [REMARK]
    data = (row + [remark or None] for row, remark in zip(result["rows"], result["remarks"]))
    out = [(ms.SHEET, headers, data), ("PORTAL COMBINED", list(L.COMBINED_COLUMNS), result["combined"])]
    out += [(name, h, rows) for name, h, rows, _ in sheets]
    write_sheets(path, out, header_format=ACCENT2_HEADER, freeze=True, autofilter=True, date_format="mm-dd-yy",
                 column_widths=[(0, len(headers) - 1, 20)], merges={name: m for name, _, _, m in sheets if m})


def run(args) -> int:
    work = Path(tempfile.mkdtemp(prefix="master_sheet_"))
    inputs, supporting = work / "input", work / "supporting"
    inputs.mkdir()
    supporting.mkdir()
    notes: list[str] = []
    target = None
    if args.file:
        src = Path(args.file)
    elif args.no_upload:
        src = ms.download(work / "drive")
    else:
        from ..core.drive import DriveFile, agent_folder
        folder = agent_folder(ms.FOLDER)
        target = DriveFile(folder.children()[ms.FILE]["id"], folder.http)
        src = target.download(work / "drive" / ms.FILE, need_edit=True)
    base = Path(args.base) if args.base else src
    existing = master_rows(base)
    sheets = own_sheets(Path(args.sheets) if args.sheets else src)
    supporting_files(sheets, supporting, notes)
    log.info("%s: %d MASTER DATA rows (from %s), owner's sheets %s", ms.FILE, len(existing), base.name,
             [s[0] for s in sheets])

    files = portal_inputs(inputs, notes) if not args.inputs else []
    if args.inputs:
        for f in Path(args.inputs).iterdir():
            if f.is_file():
                shutil.copy2(f, inputs / f.name)
    else:
        omsguru_export(inputs)
    result = update(existing, inputs, supporting)
    counts = result["counts"]
    # a short export would mark most of the sheet UNMAPPED: OMSGuru's listings against the sheet's rows
    if counts["oms"] < num("MASTER_SHEET_MIN_SHARE", 0.7) * max(len(existing), 1):
        raise RuntimeError(f"OMSGuru gave {counts['oms']:,} listings, the sheet has {len(existing):,}: too few to "
                           "update on (nothing written)")
    if counts["listings"] >= 1_048_576:
        raise ValueError("MASTER DATA exceeds the Excel worksheet size limit")
    log.info("MasterSheet: %s", counts)

    out = work / ms.FILE
    write(out, result, sheets)
    from python_calamine import CalamineWorkbook
    with CalamineWorkbook.from_path(str(out)) as wb:
        if wb.get_sheet_by_name(ms.SHEET).height != counts["listings"] + 1:
            raise ValueError("Written MASTER DATA rows differ from the updated listings")
    shutil.copy2(out, output_dir("master_sheet") / ms.FILE)
    if target is not None:
        target.upload(out)
    text = message(counts, files, notes, datetime.now())
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
    return 0


def message(c: dict, files: list[str], notes: list[str], now: datetime) -> str:
    lines = [f"🗂 MasterSheet updated (OMSGuru mapping tool) · {now:%d %b %Y %I:%M %p}",
             f"MASTER DATA: {c['listings']:,} listings ({c['new'] + c['parked']:,} new, "
             f"{c['parked']:,} of them without a sized SKU)",
             f"OMSGuru export: {c['oms']:,} listings",
             f"Marked UNMAPPED (not in OMSGuru): {c['unmapped']:,}",
             f"PORTAL SHEET files: {len(files)}"]
    lines += notes
    lines.append(f"📁 Drive: AGENT WORK / {ms.FOLDER} / {ms.FILE}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py master-sheet", description="MASTER DATA from the OMSGuru mapping tool")
    p.add_argument("--no-upload", action="store_true", help="build it, do not save it on Drive")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    p.add_argument("--file", help="a local MasterSheet.xlsx to build on (nothing saved on Drive)")
    p.add_argument("--base", help="take MASTER DATA from this workbook (its MASTER DATA or Master sheet) instead")
    p.add_argument("--sheets", help="take the owner's sheets (MASTER SKU, FABRIC CODE ...) from this workbook instead")
    p.add_argument("--inputs", help="a local input/ folder (portal files + OMSGuru export) instead of Drive + OMSGuru")
    return run_bot("MasterSheet", p, run, argv)
