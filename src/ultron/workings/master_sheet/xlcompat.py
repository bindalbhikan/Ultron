"""The few openpyxl / xlrd read calls the owner's mapping tool (legacy.py) makes, served by python-calamine, so its
logic runs line for line on the project's reader (owner, 26 Nov 2026: the old tool same to same; no openpyxl / xlrd
in new code). Values come back as those libraries gave them: openpyxl (xlsx) a whole number as int, a day as
datetime, an empty cell as None; xlrd (xls) every number and day as float. A merged range keeps its value in the top
left cell only, as openpyxl does; merged_cells.ranges lists the ranges (1-based, inclusive)."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from python_calamine import CalamineWorkbook

EXCEL_EPOCH = datetime(1899, 12, 30)


def _xlsx_value(v):
    if v == "":
        return None
    if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 53:
        return int(v)
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    return v


def _xls_value(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return float(v)
    if isinstance(v, datetime):
        return (v - EXCEL_EPOCH).total_seconds() / 86400
    if isinstance(v, date):
        return float((datetime(v.year, v.month, v.day) - EXCEL_EPOCH).days)
    if isinstance(v, time):
        return (v.hour * 3600 + v.minute * 60 + v.second) / 86400
    return v


class _Range:
    def __init__(self, start, end):
        (self.min_row, self.min_col), (self.max_row, self.max_col) = (start[0] + 1, start[1] + 1), (end[0] + 1, end[1] + 1)


class _Merged:
    def __init__(self, ranges):
        self.ranges = [_Range(a, b) for a, b in ranges or []]


class _Cell:
    def __init__(self, value):
        self.value = value


class Worksheet:
    """openpyxl's worksheet, read side: title, iter_rows(min_row, max_row, values_only=True), cell(), max_row."""

    def __init__(self, sheet):
        self.title = sheet.name
        self._rows = [tuple(_xlsx_value(v) for v in row) for row in sheet.to_python(skip_empty_area=False)]
        while self._rows and all(v is None for v in self._rows[-1]):
            self._rows.pop()
        self.merged_cells = _Merged(sheet.merged_cell_ranges)
        self.column_dimensions: dict = {}

    @property
    def max_row(self) -> int:
        return len(self._rows)

    def iter_rows(self, min_row: int = 1, max_row: int | None = None, values_only: bool = True):
        stop = len(self._rows) if max_row is None else min(max_row, len(self._rows))
        for i in range(min_row - 1, stop):
            yield self._rows[i]

    def cell(self, row: int, column: int) -> _Cell:
        values = self._rows[row - 1] if 0 < row <= len(self._rows) else ()
        return _Cell(values[column - 1] if 0 < column <= len(values) else None)


class Workbook:
    def __init__(self, path):
        self._book = CalamineWorkbook.from_path(str(path))
        self.sheetnames = list(self._book.sheet_names)
        self._sheets: dict[str, Worksheet] = {}

    def __getitem__(self, name: str) -> Worksheet:
        if name not in self._sheets:
            self._sheets[name] = Worksheet(self._book.get_sheet_by_name(name))
        return self._sheets[name]

    @property
    def worksheets(self) -> list[Worksheet]:
        return [self[n] for n in self.sheetnames]

    @property
    def active(self) -> Worksheet:
        return self[self.sheetnames[0]]

    def close(self) -> None:
        self._book.close()


def load_workbook(path, read_only: bool = False, data_only: bool = True) -> Workbook:
    return Workbook(Path(path))


class XlsSheet:
    """xlrd's sheet: name, nrows, ncols, cell_value(row, col) (0-based), numbers as float."""

    def __init__(self, sheet):
        self.name = sheet.name
        self._rows = [[_xls_value(v) for v in row] for row in sheet.to_python(skip_empty_area=False)]
        self.nrows = len(self._rows)
        self.ncols = max((len(r) for r in self._rows), default=0)

    def cell_value(self, row: int, col: int):
        values = self._rows[row]
        return values[col] if col < len(values) else ""


class XlsBook:
    def __init__(self, path):
        self._book = CalamineWorkbook.from_path(str(path))

    def sheet_by_index(self, index: int) -> XlsSheet:
        return XlsSheet(self._book.get_sheet_by_index(index))

    def sheet_names(self) -> list[str]:
        return list(self._book.sheet_names)

    def release_resources(self) -> None:
        self._book.close()


def open_workbook(path, on_demand: bool = False) -> XlsBook:
    return XlsBook(Path(path))
