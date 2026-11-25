"""Myntra zero TD on Polars: the styles read from the MasterSheet, one row per style, the workbook and message."""
from datetime import datetime

import xlsxwriter
from python_calamine import CalamineWorkbook

from ultron.workings.myntra_zero_td import pipeline


def _master(path):
    """A MasterSheet.xlsx in the owner's layout (MASTER DATA + a REMOVED LISTINGS row that must not be read)."""
    wb = xlsxwriter.Workbook(str(path))
    head = ["Channel Listing SKU Code", "Channel Name", "Brand", "MY SKU", "MASTER STYLE CODE", "MYNTRA STYLE ID", "COLOR"]
    ws = wb.add_worksheet("MASTER DATA")
    ws.write_row(0, 0, head)
    rows = [["A-S", "MYNTRA", None, "A", None, "11", "Red"],          # MAIN, its brand from another size
            ["A-M", "MYNTRA PPMP", "Fashfun", "A", None, "11", None],
            ["B-S", "MYNTRA", "Leia", "B", "FB", "12.0", "Blue"],
            ["C-S", "MYNTRA DBCC", "Murcia", "C", None, "13", None],    # another account
            ["D-S", "FLIPKART", "Fashfun", "D", None, "14", None],      # not Myntra
            ["E-S", "MYNTRA", "Fashfun", "E", None, "x", None]]         # no style id
    for r, row in enumerate(rows, 1):
        ws.write_row(r, 0, row)
    removed = wb.add_worksheet("REMOVED LISTINGS")
    removed.write_row(0, 0, head)
    removed.write_row(1, 0, ["F-S", "MYNTRA", "Fashfun", "F", None, "15", None])
    wb.close()
    return path


def test_master_rows_checks_workbook_and_message(tmp_path):
    sheets = pipeline.read_source(_master(tmp_path / "MasterSheet.xlsx"), ["MAIN"])
    assert list(sheets) == ["MAIN"]
    assert sheets["MAIN"].select("STYLE ID", "BRAND", "MY SKU", "MASTER STYLE CODE", "COLOR").rows() == [
        (11, "Fashfun", "A", None, "Red"), (12, "Leia", "B", "FB", "Blue")]

    found = {11: {"STATUS": "ZERO TD", "MRP": 999, "STOCK AT MRP": 4, "LINK": "https://www.myntra.com/11"},
             12: {"STATUS": "NOT CHECKED", "ERROR": "HTTP 500"}}
    checked = pipeline.with_checks(sheets, found)
    assert pipeline.summarise("MAIN", checked["MAIN"])["STOCK AT MRP"] == 4
    out = pipeline.write_workbook(tmp_path / "out.xlsx", checked, datetime(2026, 10, 26, 10))
    book = CalamineWorkbook.from_path(str(out))
    assert book.sheet_names == ["SUMMARY", "ALL ACCOUNTS", "MAIN", "NOT CHECKED"]
    main = book.get_sheet_by_name("MAIN").to_python()
    assert main[0][1] == "STYLE ID" and main[1][1] == "11"                  # an id is text
    assert book.get_sheet_by_name("ALL ACCOUNTS").to_python()[1][1] == "A"   # MASTER STYLE CODE empty: MY SKU
    text = pipeline.message(checked, datetime(2026, 10, 26, 10))
    assert "1 styles live at MRP" in text and "1 styles not checked" in text


def test_every_account_from_the_master(tmp_path):
    sheets = pipeline.read_source(_master(tmp_path / "MasterSheet.xlsx"), ["MAIN", "DBCC", "FMCC"])
    assert {a: df["STYLE ID"].to_list() for a, df in sheets.items()} == {"MAIN": [11, 12], "DBCC": [13]}
