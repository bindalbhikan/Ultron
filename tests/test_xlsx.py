"""workings/core/xlsx.write_sheets (docs/CENTRALISE.md step 6): read back as the old openpyxl files are."""
from datetime import date, datetime

import pandas as pd
from openpyxl import Workbook, load_workbook

from ultron.workings.core.xlsx import sheet_name, write_sheets

HEAD = ["Order ID", "AWB", "Amount", "Qty", "Date", "Day", "Note", "Flag"]
ROWS = [
    {"Order ID": "FN1234567", "AWB": "0123456789", "Amount": 1999.5, "Qty": 2, "Date": datetime(2026, 11, 5, 14, 30),
     "Day": date(2026, 11, 5), "Note": "=not a formula", "Flag": True},
    {"Order ID": "FN7654321", "AWB": None, "Amount": float("nan"), "Qty": 0, "Date": None, "Day": None,
     "Note": "https://example.com/x", "Flag": False},
    {"Order ID": "42", "AWB": "00099", "Amount": -3, "Qty": None, "Date": pd.Timestamp("2026-11-06 09:00"),
     "Day": pd.NaT, "Note": "", "Flag": None},
]


def old_write(path, sheets):
    """ajio_spf.inputs.write_xlsx before the move (openpyxl, write_only)."""
    wb = Workbook(write_only=True)
    for name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(headers)
        for row in rows:
            ws.append([None if (isinstance(row.get(h), float) and row.get(h) != row.get(h)) or row.get(h) is pd.NaT
                       else row.get(h) for h in headers])
    wb.save(path)


def test_read_back_the_same_as_the_old_writer(tmp_path):
    old, new = tmp_path / "old.xlsx", tmp_path / "new.xlsx"
    old_write(old, {"Sheet1": (HEAD, ROWS)})
    write_sheets(new, {"Sheet1": (HEAD, ROWS)})
    for kw in ({}, {"dtype": str}):
        a = pd.read_excel(old, sheet_name=None, **kw)
        b = pd.read_excel(new, sheet_name=None, **kw)
        assert list(a) == list(b)
        # the one difference, on purpose: openpyxl made a text starting with "=" a formula (read back empty);
        # the new writer keeps it as the text it was
        assert pd.isna(a["Sheet1"].loc[0, "Note"]) and b["Sheet1"].loc[0, "Note"] == "=not a formula"
        a["Sheet1"].loc[0, "Note"] = b["Sheet1"].loc[0, "Note"]
        pd.testing.assert_frame_equal(a["Sheet1"], b["Sheet1"], check_dtype=False)


def test_text_stays_text_and_header_bold_frozen_wide(tmp_path):
    p = write_sheets(tmp_path / "a.xlsx", {"Sheet1": (HEAD, ROWS)}, bold_header=True, freeze=True, auto_width=True)
    ws = load_workbook(p)["Sheet1"]
    assert ws["B2"].value == "0123456789" and ws["G2"].value == "=not a formula" and ws["A4"].value == "42"
    assert ws["A1"].font.b and ws.freeze_panes == "A2"
    assert ws.column_dimensions["A"].width >= len("FN1234567")


def _old_report_xlsx(lists, path):
    """workings/core/telegram.write_xlsx before the move (openpyxl)."""
    import re as _re

    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    for block in lists:
        name, n = _re.sub(r"[\\/*?:\[\]]", "-", block.sheet)[:31] or "List", 2
        while name in wb.sheetnames:
            name, n = f"{block.sheet[:28]} {n}", n + 1
        ws = wb.create_sheet(name)
        cols = list(dict.fromkeys(k for r in block.rows for k in r))
        ws.append(cols)
        for r in block.rows:
            ws.append([r.get(c) for c in cols])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for i, c in enumerate(cols, 1):
            width = max(len(str(c)), *(len(str(r.get(c) if r.get(c) is not None else "")) for r in block.rows))
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(width + 2, 60)
    wb.save(path)


def test_telegram_report_excel_same_as_before(tmp_path):
    from ultron.workings.core import telegram
    def listing(sheet, rows):
        return telegram.Listing(title=sheet, lines=[], rows=rows, sheet=sheet)
    lists = [listing("Pending pickup", [{"AWB": "0012", "Courier": "XB", "Days": 3},
                                        {"AWB": "0034", "Courier": "Delhivery long name", "Days": None}]),
             listing("Pending pickup", [{"Order": "FN1", "When": datetime(2026, 11, 5, 10, 0)}]),
             listing("Lost: [AJIO]", [{"Order": "FN2"}])]
    old, new = tmp_path / "old.xlsx", telegram.write_xlsx([*lists, "text block"], tmp_path / "new.xlsx")
    _old_report_xlsx(lists, old)
    a, b = load_workbook(old), load_workbook(new)
    assert a.sheetnames == b.sheetnames
    for name in a.sheetnames:
        wa, wb_ = a[name], b[name]
        assert [[c.value for c in r] for r in wa.iter_rows()] == [[c.value for c in r] for r in wb_.iter_rows()]
        assert wb_["A1"].font.b and wb_.freeze_panes == "A2"
        for col in wa.column_dimensions:
            assert abs(wa.column_dimensions[col].width - wb_.column_dimensions[col].width) < 1


def test_sheet_names_cut_cleaned_and_unique():
    taken = set()
    a = sheet_name("Pickup / pending: [AJIO] couriers of the whole week", taken)
    taken.add(a)
    b = sheet_name("Pickup / pending: [AJIO] couriers of the whole week", taken)
    assert len(a) <= 31 and not set("/:[]") & set(a) and a != b
