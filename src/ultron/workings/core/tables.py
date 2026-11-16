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


def read_text_csv(data: bytes) -> "pl.DataFrame":
    """A report's CSV as Polars, every column text (ids keep their leading zeros, nothing guessed)."""
    import io

    import polars as pl
    return pl.read_csv(io.BytesIO(data), infer_schema=False)


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
    return pd.DataFrame({c: df[c].to_list() for c in df.columns}, columns=list(df.columns))


def pcol(df: "pl.DataFrame", name: str) -> "pl.Expr":
    """Polars: the column `name` (matched without case / outer spaces) as stripped text; nulls when missing."""
    import polars as pl
    want = name.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == want:
            return pl.col(c).cast(pl.Utf8).str.strip_chars()
    return pl.lit(None, dtype=pl.Utf8)


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
