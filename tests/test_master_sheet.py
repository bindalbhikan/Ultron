"""MasterSheet = the owner's OMSGuru mapping tool (legacy.py) + REMARK UNMAPPED (owner, 26 Nov 2026)."""
from datetime import date, datetime

from python_calamine import CalamineWorkbook

from ultron.workings.core.xlsx import write_sheets
from ultron.workings.master_sheet import legacy as L
from ultron.workings.master_sheet import pipeline as P
from ultron.workings.master_sheet.xlcompat import load_workbook, open_workbook


def test_values_come_back_as_openpyxl_and_xlrd_gave_them(tmp_path):
    path = write_sheets(tmp_path / "a.xlsx", [("S", ["A", "B", "C"], [[12, "x", date(2024, 1, 25)], [1.5, None, None]])])
    ws = load_workbook(path).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    assert rows[1] == (12, "x", datetime(2024, 1, 25)) and isinstance(rows[1][0], int)
    assert rows[2] == (1.5, None, None)
    assert next(ws.iter_rows(min_row=2, max_row=2, values_only=True)) == rows[1]
    xls = open_workbook(path).sheet_by_index(0)        # xlrd: numbers as float, empty as ""
    assert xls.cell_value(1, 0) == 12.0 and isinstance(xls.cell_value(1, 0), float) and xls.cell_value(2, 1) == ""


def test_merged_cells_are_kept_and_read_for_every_row(tmp_path):
    rows = [["RU-1-M24", "D2"], ["UI-1-M24", ""], ["COORD-HP-A17", "D-129"]]
    path = write_sheets(tmp_path / "f.xlsx", [("Sheet1", ["SKU", "FABRCI CODE"], rows)],
                        merges={"Sheet1": [((1, 1), (2, 1))]})
    assert CalamineWorkbook.from_path(str(path)).get_sheet_by_name("Sheet1").merged_cell_ranges == [((1, 1), (2, 1))]
    got = L.read_sku_sheet(path, ("FABRIC CODE", "FABRCI CODE"))
    assert got == {"RU-1-M24": "D2", "UI-1-M24": "D2", "COORD-HP-A17": "D-129"}


def _row(sku, lid, channel):
    r = [None] * len(L.MASTER_COLUMNS)
    r[0], r[1], r[2] = sku, lid, channel
    return r


def test_a_listing_not_in_omsguru_is_unmapped():
    oms = [(2, "E-18-M", "111", "BINDAL EXPORTS LIMITED - Myntra PPMP", "E-18-M"),
           (3, "B0X", "B0X", "Amazon", "E-19-L")]
    rows = [_row("E-18-M", "111", "MYNTRA PPMP"),          # by listing id
            _row("b0x", "999", "AMAZON"),                 # listing id gone, its SKU code still there
            _row("E-20-S", "555", "FLIPKART")]            # only on the portal / old: UNMAPPED
    assert P.unmapped(rows, [(i, s, lid, L.CHANNEL_ENTITY_PREFIX.sub("", c), p) for i, s, lid, c, p in oms]) == \
        ["", "", "UNMAPPED"]


def test_master_rows_read_the_owners_column_names(tmp_path):
    head = [P.SHEET_NAME.get(c, c) for c in L.MASTER_COLUMNS] + ["REMARK"]
    row = [None] * len(head)
    row[:3], row[7] = ["E-18-M", 111, "MYNTRA"], "E-18-M"
    path = write_sheets(tmp_path / "m.xlsx", [("MASTER DATA", head, [row])])
    got = P.master_rows(path)
    assert len(got) == 1 and len(got[0]) == len(L.MASTER_COLUMNS)
    assert got[0][L.MASTER_COLUMNS.index("FINAL SKU")] == "E-18-M" and got[0][1] == 111
