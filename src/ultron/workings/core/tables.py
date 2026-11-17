"""Table helpers every working needs (docs/CENTRALISE.md step 5), in one place.

    col(df, "order status")   a column by name whatever its case / spaces in the file; empty when missing
    clean_id(value)           an id read from Excel / CSV as text: "19170.0" -> "19170" (a value or a column)

Written for pandas today; the Polars move (docs/libraries/06-polars.md) changes them here, once.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl


def col(df: "pd.DataFrame", name: str) -> "pd.Series":
    """The column `name` (matched without case or outer spaces) as stripped text; an empty column of the
    frame's length when the report has no such column."""
    import pandas as pd
    want = name.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == want:
            return df[c].astype(str).str.strip()
    return pd.Series(dtype=str, index=df.index)


def read_text_csv(data, pandas_na: bool = False) -> "pl.DataFrame":
    """A report's CSV (bytes or a path) as Polars, every column text (ids keep their leading zeros, nothing
    guessed). pandas_na: "NA", "N/A", "NULL", "nan" ... read as missing too, as pandas' read_csv did (for code
    whose numbers must stay those of the pandas version)."""
    import io

    import polars as pl
    src = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else str(data)
    df = pl.read_csv(src, infer_schema=False)
    if pandas_na:
        df = df.with_columns(pl.when(pl.col(c).is_in(sorted(PANDAS_NA))).then(None).otherwise(pl.col(c)).alias(c)
                             for c in df.columns)
    return df


# the texts pandas reads as missing by default (its na_values): the old reports read "NA" etc. as empty
PANDAS_NA = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>",
             "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null"}


def _cell_text(v) -> str | None:
    """A cell as the text pandas' read_excel(dtype=str) gave: whole numbers without ".0", dates as
    "YYYY-MM-DD HH:MM:SS", empty and pandas' missing texts ("NA", "N/A", "NULL" ...) as missing."""
    from datetime import date, datetime, time
    if v is None or (isinstance(v, str) and v in PANDAS_NA):
        return None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return f"{v:%Y-%m-%d} 00:00:00"
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    return str(v)


def read_excel_text(path, sheet: str | int = 0, header: int | None = 0, engine: str = "calamine") -> "pl.DataFrame":
    """One sheet of an xlsx as Polars text columns, read the way pandas' read_excel(dtype=str, header=header)
    read it: the header row `header` (0-based; None: no header, columns "0", "1" ...), repeated names numbered
    ".1", ".2" ..., empty rows inside kept and trailing empty rows / columns left out. engine "calamine" (Rust, fast; checked the same as pandas on every Flipkart report sheet) or "openpyxl"
    (the engine pandas used): AJIO's files write texts with outer spaces without xml:space="preserve", which
    calamine trims and pandas kept ("TOP " / " "), so AJIO is read with openpyxl to stay the same."""
    import polars as pl
    if engine == "openpyxl":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
        ws.reset_dimensions()           # AJIO's files state a wrong size (pandas does the same)
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_path(str(path))
        name = wb.sheet_names[sheet] if isinstance(sheet, int) else sheet
        rows = wb.get_sheet_by_name(name).to_python(skip_empty_area=False)
    cells = [[_cell_text(v) for v in r] for r in rows]
    while cells and all(v is None for v in cells[-1]):      # trailing empty rows go; empty rows inside stay,
        cells.pop()                                          # as in pandas (row positions matter to some readers)
    width = max((len(r) for r in cells), default=0)
    while width and all(len(r) < width or r[width - 1] is None for r in cells):
        width -= 1                                           # trailing empty columns go too
    if header is None:
        head = [str(i) for i in range(width)]
        body = cells
    else:
        if len(cells) <= header:
            return pl.DataFrame()
        head, seen = [], {}
        for i in range(width):
            h = cells[header][i] if i < len(cells[header]) else None
            h = f"Unnamed: {i}" if h is None else h
            n = seen.get(h, 0)
            seen[h] = n + 1
            head.append(h if n == 0 else f"{h}.{n}")
        body = cells[header + 1:]
    body = [(r + [None] * width)[:width] for r in body]
    return pl.DataFrame({h: [r[i] for r in body] for i, h in enumerate(head)}, schema={h: pl.Utf8 for h in head})


def to_polars(df) -> "pl.DataFrame":
    """A pandas frame (the bridge while both live side by side) or a Polars one, as Polars text columns."""
    import pandas as pd
    import polars as pl
    if isinstance(df, pl.DataFrame):
        return df
    cols = [str(c) for c in df.columns]
    return pl.DataFrame({c: [None if pd.isna(v) else str(v) for v in df[orig]] for c, orig in zip(cols, df.columns)},
                        schema={c: pl.Utf8 for c in cols})


def to_pandas(df: "pl.DataFrame") -> "pd.DataFrame":
    """Polars -> pandas for the code not moved yet (the bridge; no pyarrow needed): every value as it is,
    missing values as NaN / NaT / None."""
    import pandas as pd
    import polars as pl

    def values(s):
        if s.dtype == pl.Utf8:               # a missing text as NaN, as pandas' readers gave it (never "None")
            return [float("nan") if v is None else v for v in s.to_list()]
        return s.to_list()
    return pd.DataFrame({c: values(df[c]) for c in df.columns}, columns=list(df.columns))


def pcol(df: "pl.DataFrame", name: str) -> "pl.Expr":
    """Polars: the column `name` (matched without case / outer spaces) as stripped text; nulls when missing."""
    import polars as pl
    want = name.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == want:
            return pl.col(c).cast(pl.Utf8).str.strip_chars()
    return pl.lit(None, dtype=pl.Utf8)


def sheet_names(path) -> list[str]:
    """The sheet names of an xlsx (python-calamine; no pandas)."""
    from python_calamine import CalamineWorkbook
    return list(CalamineWorkbook.from_path(str(path)).sheet_names)


def pany_date(expr: "pl.Expr") -> "pl.Expr":
    """Polars: a date of a hand-made file (the owner's monthly files): an Excel day number, AJIO's
    "Wed Sep 30 23:21:44 IST 2026", or ISO text (YYYY-MM-DD [HH:MM:SS]); anything else -> null."""
    import polars as pl
    s = expr.cast(pl.Utf8).str.strip_chars()
    n = s.cast(pl.Float64, strict=False)
    serial = pl.datetime(1899, 12, 30, time_unit="us") + pl.duration(milliseconds=(n * 86_400_000).round(0).cast(pl.Int64))
    txt = s.str.replace(" IST", "", literal=True)
    iso = txt.str.slice(0, 19)
    return pl.coalesce(pl.when(n.is_not_null()).then(serial),
                       txt.str.to_datetime("%a %b %d %H:%M:%S %Y", strict=False, time_unit="us"),
                       iso.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False, time_unit="us"),
                       iso.str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False, time_unit="us"),
                       iso.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us")))


def unread_dates(df: "pl.DataFrame", text: str, parsed: str, what: str, log=None) -> int:
    """How many rows have a date text that pany_date could not read (logged): never dropped silently."""
    import polars as pl
    bad = df.filter(pl.col(text).is_not_null() & (pl.col(text).str.strip_chars() != "") & pl.col(parsed).is_null())
    if bad.height and log is not None:
        log.warning("%s: %d dates not read (e.g. %s)", what, bad.height, bad[text].head(3).to_list())
    return bad.height


def pnum(expr: "pl.Expr") -> "pl.Expr":
    """Polars: a number from text (outer spaces out); anything else -> null (pandas' to_numeric(errors="coerce"))."""
    import polars as pl
    return expr.cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False)


def pclean_id(expr: "pl.Expr") -> "pl.Expr":
    """Polars: an id column without the ".0" a number read from a sheet gets; nulls stay null."""
    return expr.str.replace(r"\.0$", "")


@overload
def clean_id(value: "pd.Series") -> "pd.Series": ...
@overload
def clean_id(value: Any) -> str: ...
def clean_id(value):
    """An id as text without the ".0" a number read from a sheet gets: a column (pandas Series of text) or one
    value. In a column a missing value (None / NaN) stays missing — never the text "None" / "nan"; turn a
    column of numbers into text first (.astype(str)). One value is also stripped of outer spaces; None / NaN
    give ""."""
    try:
        import pandas as pd
        if isinstance(value, pd.Series):
            return value.str.replace(r"\.0$", "", regex=True)
        if value is None or (not isinstance(value, str) and pd.isna(value)):
            return ""
    except ImportError:
        if value is None:
            return ""
    return str(value).strip().removesuffix(".0")
