"""The Final TP update master sheet (owner, 14 Nov 2026): Drive AGENT WORK > FLIPKART > TP UPDATE MASTER >
"FLIPKART TP UPDATE MASTER.xlsx", one sheet per month (NOV-26 ...):

    FSN | SKU | Final TP | <date> (merged over two columns) ...
                         | Old TP | New TP

One row per listing the update has worked on (it is added the first time and kept). Every run writes
its day's pair: Old TP = the settlement before the day's first run, New TP = the settlement after the
day's last run. This file goes to Telegram after every run. It sits outside PRICE UPDATE, whose newest
.xlsx is taken as the Final TP file.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

log = logging.getLogger("bindal.flipkart_price")

FOLDER = ("FLIPKART", "TP UPDATE MASTER")
NAME = "FLIPKART TP UPDATE MASTER.xlsx"
HEAD = Font(bold=True)
FILL = PatternFill("solid", fgColor="DDEBF7")
CENTER = Alignment(horizontal="center", vertical="center")


def sheet_name(day: date) -> str:
    return f"{day:%b-%y}".upper()


def _sheet(wb, day: date):
    name = sheet_name(day)
    if name in wb.sheetnames:
        return wb[name]
    ws = wb.create_sheet(name)
    for col, head in enumerate(("FSN", "SKU", "Final TP"), start=1):
        ws.cell(1, col, head)
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        c = ws.cell(1, col)
        c.font, c.fill, c.alignment = HEAD, FILL, CENTER
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 10
    ws.freeze_panes = "D3"
    return ws


def _day_col(ws, day: date) -> int:
    """The column of the day's Old TP (New TP is the next one); added at the right when new."""
    label = f"{day:%d-%m-%Y}"
    col = 4
    while ws.cell(1, col).value not in (None, ""):
        if str(ws.cell(1, col).value) == label:
            return col
        col += 2
    ws.cell(1, col, label)
    ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 1)
    ws.cell(2, col, "Old TP")
    ws.cell(2, col + 1, "New TP")
    for c in (ws.cell(1, col), ws.cell(2, col), ws.cell(2, col + 1)):
        c.font, c.fill, c.alignment = HEAD, FILL, CENTER
    for c in (col, col + 1):
        ws.column_dimensions[get_column_letter(c)].width = 9
    return col


def update(path: Path, day: date, rows: list[dict]) -> int:
    """Write the day's pair for every row {fsn, sku, tp, old, new} into the workbook at path (made
    when missing). Old TP is kept from the day's first run; New TP is replaced. Returns rows written."""
    if path.exists():
        wb = load_workbook(path)
    else:
        wb = Workbook()
        wb.remove(wb.active)
    ws = _sheet(wb, day)
    col = _day_col(ws, day)
    where = {(str(ws.cell(r, 1).value), str(ws.cell(r, 2).value)): r for r in range(3, ws.max_row + 1)
             if ws.cell(r, 2).value not in (None, "")}
    nxt = max(where.values(), default=2) + 1
    for x in rows:
        key = (str(x["fsn"]), str(x["sku"]))
        r = where.get(key)
        if r is None:
            r = where[key] = nxt
            nxt += 1
            ws.cell(r, 1, x["fsn"])
            ws.cell(r, 2, x["sku"])
        ws.cell(r, 3, x["tp"])
        if ws.cell(r, col).value in (None, ""):
            ws.cell(r, col, x["old"])
        ws.cell(r, col + 1, x["new"])
    wb._sheets.sort(key=lambda s: _month_key(s.title))
    wb.save(path)
    return len(rows)


def _month_key(title: str):
    from datetime import datetime
    try:
        return datetime.strptime(title, "%b-%y")
    except ValueError:
        return datetime.max


def sync(day: date, rows: list[dict], dest: Path) -> tuple[Path, str]:
    """Download the master from Drive (when there), write the day, put it back. (local path, link)."""
    from ..core.config import agent_work_id
    from ..core.drive import DriveFile, DriveFolder
    folder = DriveFolder(agent_work_id())
    for part in FOLDER:
        folder = folder.subfolder(part, create=True)
    path = dest / NAME
    if path.exists():
        path.unlink()
    folder.download(NAME, path)
    n = update(path, day, rows)
    fid = folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    log.info("TP update master: %d listings written for %s", n, day)
    return path, DriveFile(fid).url
