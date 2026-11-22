"""core/tables.read_excel_text / read_text_csv: report files read as text, ids and numbers as written."""
from datetime import datetime

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


EXPECTED = [["OI:1", "2", "2026-10-05 14:30:00", None, "a"], [None, None, None, None, None],
            ["OI:2", "1.5", None, " spaced ", "b"], ["OI:3", "10", None, None, "c"]]


def test_both_engines_read_the_same_text(tmp_path):
    """The values pandas' read_excel(dtype=str) gave (checked on all 100 sheets of the real Flipkart / AJIO
    report files, 16 Nov 2026): whole numbers without ".0", dates as text, "NA" / "N/A" missing, a repeated
    header ".1", an empty row inside kept."""
    p = _book(tmp_path / "a.xlsx")
    for engine in ("calamine", "openpyxl"):
        df = read_excel_text(p, "Orders", engine=engine)
        assert df.columns == ["id", "qty", "when", "note", "id.1"]
        assert [list(r) for r in df.rows()] == EXPECTED
        raw = read_excel_text(p, "Orders", header=None, engine=engine)
        assert raw.columns == ["0", "1", "2", "3", "4"]
        assert [list(r) for r in raw.rows()] == [["id", "qty", "when", "note", "id"], *EXPECTED]


def test_empty_row_kept_na_texts_missing(tmp_path):
    df = read_excel_text(_book(tmp_path / "a.xlsx"), "Orders")
    assert df.columns == ["id", "qty", "when", "note", "id.1"]
    assert df["id"].to_list() == ["OI:1", None, "OI:2", "OI:3"]          # the empty row stays (row positions)
    assert df["qty"].to_list() == ["2", None, "1.5", "10"]
    assert df["when"].to_list()[0] == "2026-10-05 14:30:00"
    assert df["note"].to_list() == [None, None, " spaced ", None]        # "NA" / "N/A" missing


def test_csv_na_words(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("id,status\n0012,NA\n0013,C\n0014,null\n", encoding="utf-8")
    df = read_text_csv(p, na_words=True)
    assert df["id"].to_list() == ["0012", "0013", "0014"] and df["status"].to_list() == [None, "C", None]
    assert read_text_csv(p)["status"].to_list() == ["NA", "C", "null"]
