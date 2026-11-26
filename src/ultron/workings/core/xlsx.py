"""New xlsx files written in one place (docs/CENTRALISE.md step 6), on xlsxwriter (docs/libraries: the fast
streaming writer, built for a big seller's rows). openpyxl stays only to edit an existing workbook in place.

    write_sheets(path, {"Sheet1": (headers, rows)}, bold_header=True, freeze=True, auto_width=True)

rows: dicts (read by header) or lists. Dates and times come out as Excel dates (yyyy-mm-dd hh:mm:ss); None and
NaN as empty cells; text is never turned into a number or a link. A sheet name is cut to Excel's 31
characters without the characters it refuses.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path

BAD = re.compile(r"[\\/*?:\[\]]")


# Excel's "Accent2" cell style (100% fill of the Office theme's Accent 2, which xlsxwriter's workbooks use) with bold
# white text: the owner's header style (24 Nov 2026)
ACCENT2_HEADER = {"bold": True, "font_color": "#FFFFFF", "bg_color": "#C0504D", "border": 1}


def sheet_name(name: str, taken: set[str]) -> str:
    """An Excel sheet name for `name`: refused characters out, 31 characters, unique in the workbook."""
    base = BAD.sub("-", str(name))[:31] or "Sheet"
    out, n = base, 2
    while out.lower() in {t.lower() for t in taken}:
        out, n = f"{base[:28]} {n}", n + 1
    return out


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (type(v).__name__ in ("NaTType", "NAType"))


URL_LIMIT = 65_530                   # xlsxwriter's (Excel's) most links in one sheet; the rest stay text


def write_sheets(path, sheets: dict | list, *, bold_header: bool = False, freeze: bool | tuple[int, int] = False,
                 auto_width: bool = False, max_width: int = 60, autofilter: bool = False,
                 column_widths: list[tuple[int, int, float]] | None = None, links: bool = False,
                 header_format: dict | None = None, constant_memory: bool = False) -> Path:
    """{sheet: (headers, rows)} or [(sheet, headers, rows), ...] (a name may repeat) -> one xlsx at path (its
    folder made); the path. header_format: the header row's xlsxwriter format (e.g. ACCENT2_HEADER), else bold_header
    makes it bold. freeze: True = the header row, or (rows, columns); autofilter over the header and rows;
    column_widths: (first column, last column, width) each; links: a text starting with http(s):// as a clickable link."""
    import xlsxwriter
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path), {"constant_memory": constant_memory, "strings_to_numbers": False, "strings_to_formulas": False,
                                         "strings_to_urls": False, "nan_inf_to_errors": True})
    head = (wb.add_format(header_format) if header_format else wb.add_format({"bold": True}) if bold_header else None)
    when = wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    day = wb.add_format({"num_format": "yyyy-mm-dd"})
    taken: set[str] = set()
    items = [(n, h, r) for n, (h, r) in sheets.items()] if isinstance(sheets, dict) else list(sheets)
    for name, headers, rows in items:
        ws = wb.add_worksheet(sheet_name(name, taken))
        taken.add(ws.get_name())
        headers = list(headers)
        widths = [len(str(h)) for h in headers]
        for c, h in enumerate(headers):
            ws.write_string(0, c, str(h), head) if head else ws.write_string(0, c, str(h))
        n_links, last = 0, 0
        for r, row in enumerate(rows, 1):
            last = r
            values = [row.get(h) for h in headers] if isinstance(row, dict) else list(row)
            for c, v in enumerate(values):
                if _blank(v):
                    continue
                if isinstance(v, datetime):
                    ws.write_datetime(r, c, v.replace(tzinfo=None), when)
                elif isinstance(v, date):
                    ws.write_datetime(r, c, datetime(v.year, v.month, v.day), day)
                elif isinstance(v, bool):
                    ws.write_boolean(r, c, v)
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    ws.write_number(r, c, v)
                elif links and isinstance(v, str) and v.startswith(("http://", "https://")) and n_links < URL_LIMIT \
                        and len(v) <= 2079:
                    ws.write_url(r, c, v)
                    n_links += 1
                else:
                    ws.write_string(r, c, str(v))
                if auto_width and c < len(widths):
                    widths[c] = max(widths[c], len(str(v)))
        if freeze:
            ws.freeze_panes(*(freeze if isinstance(freeze, tuple) else (1, 0)))
        if autofilter and headers:
            ws.autofilter(0, 0, last, len(headers) - 1)
        if auto_width:
            for c, w in enumerate(widths):
                ws.set_column(c, c, min(w + 2, max_width))
        for first, end, width in column_widths or ():
            ws.set_column(first, end, width)
    wb.close()
    return path
