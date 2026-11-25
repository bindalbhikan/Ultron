"""Myntra zero TD on Polars: the sheet read typed, brand / SKU from the MasterSheet, every style checked once,
the workbook, the message and MYNTRA ZERO TD SUMMARY SHEET (the history)."""
from datetime import datetime

import polars as pl
import xlsxwriter
from python_calamine import CalamineWorkbook

from ultron.workings.myntra_zero_td import history, pipeline


def _sheet(path):
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet("MAIN")
    ws.write_row(0, 0, [" style id", "BRAND", "MY SKU", "FINAL SKU", "COST"])
    for r, row in enumerate([[11, "old", "A", None, 100], ["12", None, "B", "FB", 120.5], ["x", None, "C", None, 1],
                             [11, None, "D", None, 9]], 1):
        ws.write_row(r, 0, row)
    ws = wb.add_worksheet("FMCC")
    ws.write_row(0, 0, ["STYLE ID", "MY SKU"])
    ws.write_row(1, 0, [12, "B"])          # also on MAIN: checked once, under MAIN
    ws.write_row(2, 0, [13, "E"])
    wb.close()
    return path


def _master(path):
    """A MasterSheet.xlsx in the owner's layout (MASTER DATA + a REMOVED LISTINGS row that must not be read)."""
    wb = xlsxwriter.Workbook(str(path))
    head = ["Channel Listing SKU Code", "Channel Name", "Brand", "MY SKU", "MASTER STYLE CODE", "MYNTRA STYLE ID"]
    ws = wb.add_worksheet("MASTER DATA")
    ws.write_row(0, 0, head)
    rows = [["A-S", "MYNTRA", None, "A", None, "11"], ["A-M", "MYNTRA PPMP", "Fashfun", "A", "MA", "11"],
            ["G-S", "MYNTRA EXIM", "Corsica", "G", None, "21"], ["D-S", "FLIPKART", "Fashfun", "D", None, "14"]]
    for r, row in enumerate(rows, 1):
        ws.write_row(r, 0, row)
    removed = wb.add_worksheet("REMOVED LISTINGS")
    removed.write_row(0, 0, head)
    removed.write_row(1, 0, ["F-S", "MYNTRA EXIM", "Corsica", "F", None, "15"])
    wb.close()
    return path


def test_sheet_master_merge_workbook_message_and_history(tmp_path):
    accounts = ["MAIN", "DBCC", "FMCC", "EXIM"]
    sheets = pipeline.read_source(_sheet(tmp_path / "sheet.xlsx"), accounts)
    assert sheets["MAIN"].select("STYLE ID", "MY SKU", "COST").rows() == [(11, "A", 100.0), (12, "B", 120.5)]

    master = pipeline.master_styles(_master(tmp_path / "MasterSheet.xlsx"), accounts)
    assert {a: df["STYLE ID"].to_list() for a, df in master.items()} == {"MAIN": [11], "EXIM": [21]}
    sheets = pipeline.merge_accounts(pipeline.with_master(sheets, master), accounts)
    main = sheets["MAIN"]
    assert main.select("STYLE ID", "BRAND", "FINAL SKU", "ACCOUNTS").rows() == [
        (11, "Fashfun", "MA", "MAIN"),          # the master's brand / SKU beat the sheet's
        (12, None, "FB", "MAIN, FMCC")]         # the master lacks it: the sheet's own; on two accounts, checked once
    assert sheets["FMCC"]["STYLE ID"].to_list() == [13]
    assert sheets["EXIM"]["STYLE ID"].to_list() == [21]   # no tab: every style the master has for EXIM

    found = {11: {"STATUS": "ZERO TD", "MRP": 999, "STOCK AT MRP": 4, "LINK": "https://www.myntra.com/11"},
             12: {"STATUS": "PART ZERO TD", "MRP": 500, "STOCK AT MRP": 2, "LINK": "https://www.myntra.com/12"},
             13: {"STATUS": "NOT CHECKED", "ERROR": "HTTP 500"}, 21: {"STATUS": "DISCOUNTED"}}
    checked = pipeline.with_checks(sheets, found)
    assert pipeline.summarise("MAIN", checked["MAIN"])["STOCK AT MRP"] == 6
    out = pipeline.write_workbook(tmp_path / "ZERO TD 26-10-26 10.00 AM.xlsx", checked, datetime(2026, 10, 26, 10))
    book = CalamineWorkbook.from_path(str(out))
    assert book.sheet_names == ["SUMMARY", "ALL ACCOUNTS", "MAIN", "FMCC", "EXIM", "NOT CHECKED"]
    tab = book.get_sheet_by_name("MAIN").to_python()
    assert tab[0][2] == "STYLE ID" and tab[1][2] == "11" and tab[2][3] == "MAIN, FMCC"
    assert book.get_sheet_by_name("ALL ACCOUNTS").to_python()[1][1] == "MA"
    text = pipeline.message(checked, datetime(2026, 10, 26, 10), {11: 3})
    assert "2 styles live at MRP" in text and "1 styles not checked" in text and "3x in Oct" in text

    # the history: a saved check read back like a new one, a check never counted twice
    first = history.workbook_rows(out, accounts, pipeline.FLAGGED)
    assert first[0].select("STYLE ID", "ACCOUNTS").rows() == [(11, "MAIN"), (12, "MAIN, FMCC")]
    second = history.run_rows(checked, datetime(2026, 11, 2, 9), pipeline.FLAGGED)
    empty = (pl.DataFrame(schema=history.LOG_SCHEMA), pl.DataFrame(schema=history.RUN_SCHEMA))
    rows, runs = history.merge(history.merge(empty, first), second)
    rows, runs = history.merge((rows, runs), second)
    assert rows.height == 4 and runs.height == 2
    path = history.write(tmp_path / history.NAME, rows, runs)
    again = history.read(path)
    assert again[0].height == 4 and again[1]["STYLES CHECKED"].to_list() == [4, 4]
    summary = history.sheets(*again)["STYLE SUMMARY"]
    row = summary.filter(pl.col("STYLE ID") == 12).row(0, named=True)
    assert (row["TIMES AT MRP"], row["PART ZERO TD TIMES"], row["DAYS"], row["OCT-26"], row["NOV-26"]) == (2, 2, 2, 1, 1)
    assert row["DATES"] == "02-11-26, 26-10-26" and row["ACCOUNTS"] == "FMCC, MAIN"
    assert history.this_month(again[0], datetime(2026, 11, 5)) == {11: 1, 12: 1}
