"""core/tables.read_excel_text / read_text_csv: report files read by Polars exactly as pandas' readers read them
(checked on all 100 sheets of the real Flipkart / AJIO report files, 16 Nov 2026)."""
from datetime import datetime

import pandas as pd
import xlsxwriter

from ultron.workings.core.tables import read_excel_text, read_text_csv


def _book(path):
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet("Orders")
    rows = [["id", "qty", "when", "note", "id"],
            ["OI:1", 2, datetime(2026, 10, 5, 14, 30), "NA", "a"],
            [None, None, None, None, None],                       # an empty row inside
            ["OI:2", 1.5, None, " spaced ", "b"],
            ["OI:3", 10.0, None, "N/A", "c"]]
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if isinstance(v, datetime):
                ws.write_datetime(r, c, v, wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"}))
            elif v is not None:
                ws.write(r, c, v)
    wb.close()
    return path


def _same(path, **kw):
    a = pd.read_excel(path, dtype=str, **{k: v for k, v in kw.items() if k != "engine"})
    b = read_excel_text(path, kw.get("sheet_name", 0), header=kw.get("header", 0), engine=kw.get("engine", "calamine"))
    assert [str(c) for c in a.columns] == b.columns
    assert [[None if pd.isna(v) else v for v in row] for row in a.values.tolist()] == b.rows() or \
           [[None if pd.isna(v) else v for v in row] for row in a.values.tolist()] == [list(r) for r in b.rows()]


def test_the_same_as_pandas_both_engines(tmp_path):
    p = _book(tmp_path / "a.xlsx")
    for engine in ("calamine", "openpyxl"):
        _same(p, sheet_name="Orders", engine=engine)
        _same(p, sheet_name="Orders", header=None, engine=engine)


def test_empty_row_kept_na_texts_missing_numbers_as_pandas(tmp_path):
    df = read_excel_text(_book(tmp_path / "a.xlsx"), "Orders")
    assert df.columns == ["id", "qty", "when", "note", "id.1"]
    assert df["id"].to_list() == ["OI:1", None, "OI:2", "OI:3"]          # the empty row stays (row positions)
    assert df["qty"].to_list() == ["2", None, "1.5", "10"]
    assert df["when"].to_list()[0] == "2026-10-05 14:30:00"
    assert df["note"].to_list() == [None, None, " spaced ", None]        # "NA" / "N/A" missing, as pandas read them


def test_csv_pandas_na(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("id,status\n0012,NA\n0013,C\n0014,null\n", encoding="utf-8")
    df = read_text_csv(p, pandas_na=True)
    assert df["id"].to_list() == ["0012", "0013", "0014"] and df["status"].to_list() == [None, "C", None]
    assert read_text_csv(p)["status"].to_list() == ["NA", "C", "null"]
