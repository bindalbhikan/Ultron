"""Myntra zero TD on Polars: the sheet read typed, one row per style, the workbook and message."""
from datetime import datetime

import openpyxl
import xlsxwriter

from ultron.workings.myntra_zero_td import pipeline


def test_sheet_rows_checks_workbook_and_message(tmp_path):
    src = tmp_path / "sheet.xlsx"
    wb = xlsxwriter.Workbook(str(src))
    ws = wb.add_worksheet("MAIN-OCT-26")
    ws.write_row(0, 0, [" style id", "MY SKU", "FINAL SKU", "COST"])
    for r, row in enumerate([[11, "A", None, 100], ["12", "B", "FB", 120.5], ["x", "C", None, 1], [11, "D", None, 9]], 1):
        ws.write_row(r, 0, row)
    wb.close()
    sheets = pipeline.read_source(src, ["MAIN"])
    assert sheets["MAIN"].select("STYLE ID", "MY SKU", "COST").rows() == [(11, "A", 100.0), (12, "B", 120.5)]

    found = {11: {"STATUS": "ZERO TD", "MRP": 999, "STOCK AT MRP": 4, "LINK": "https://www.myntra.com/11"},
             12: {"STATUS": "NOT CHECKED", "ERROR": "HTTP 500"}}
    checked = pipeline.with_checks(sheets, found)
    assert pipeline.summarise("MAIN", checked["MAIN"])["STOCK AT MRP"] == 4
    out = pipeline.write_workbook(tmp_path / "out.xlsx", checked, datetime(2026, 10, 26, 10))
    book = openpyxl.load_workbook(out)
    assert book.sheetnames == ["SUMMARY", "ALL ACCOUNTS", "MAIN", "NOT CHECKED"]
    cell = book["MAIN"]["C2"]
    assert cell.value == "11" and cell.hyperlink.target == "https://www.myntra.com/11"     # an id is text
    assert book["ALL ACCOUNTS"]["B2"].value == "A"                        # FINAL SKU empty: MY SKU
    text = pipeline.message(checked, datetime(2026, 10, 26, 10))
    assert "1 styles live at MRP" in text and "1 styles not checked" in text
