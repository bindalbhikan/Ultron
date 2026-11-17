"""GROSS, RETURN and CANCEL units per ORDER date and report block: the sale of a day against what later
happened to those same orders. Every function gives {metric: Counter[(order day, block)]}.

  Myntra    Seller_Orders_Report by created on, a line = 1 unit. CANCEL = status F; RETURN = an RTO (status
            RTO or an RTO date) or a return creation date. po_type FBM / SJIT = block SJIT, else MYNTRA
  Flipkart  Orders by order_date. RETURN = RETURNED, RETURN_REQUESTED; CANCEL = CANCELLED.
            fulfilment type FBF = block FBF, else FLIPKART
  AJIO      Dropship order report by Cust Order Date: Order Qty, Cancelled Qty. RETURN = the RTV lines of those
            customer orders (any return date), without cancelled pickups
  OMSGuru   the order list's line status by order date (for the channels with no portal client)
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import polars as pl

SJIT_MODELS = {"FBM", "SJIT"}
OMS_RETURN = {"return init", "return received", "partial return received"}
OMS_CANCEL = {"cancelled", "cancelled before shipping", "removed before shipping", "cancel init",
              "cancelled return received", "partial cancelled return received"}


def read_report(path: Path, needed: str) -> "pl.DataFrame":
    """A report's rows as text (Polars), headers in lower case; for a workbook the first sheet with column
    `needed` (Flipkart's start with a Help sheet). Raises when no sheet has it: the report changed. Read as pandas
    read them: pandas' missing texts empty, a workbook by openpyxl (AJIO's texts keep their outer spaces)."""
    from ..core.tables import read_excel_text, read_text_csv, sheet_names
    if path.suffix.lower() == ".csv":
        sheets = [lambda: read_text_csv(path, pandas_na=True)]
    else:
        sheets = [lambda s=s: read_excel_text(path, s, engine="openpyxl") for s in sheet_names(path)]
    for read in sheets:
        df = read()
        names = [str(c).strip().casefold() for c in df.columns]
        if needed.casefold() in names:
            return df.rename(dict(zip(df.columns, _unique(names))))
    raise ValueError(f"{path.name}: no column {needed!r}")


def _unique(names: list[str]) -> list[str]:
    """Column names made unique (a repeated name: the later one ".1")."""
    seen: dict[str, int] = {}
    out = []
    for n in names:
        out.append(n if n not in seen else f"{n}.{seen[n]}")
        seen[n] = seen.get(n, 0) + 1
    return out


# The counting is Polars (docs/libraries/06-polars.md); the reports may come as pandas or Polars frames.

def _count(frame: "pl.DataFrame", qty: "pl.Expr", block: "pl.Expr | str") -> Counter:
    """Counter[(order day, block)] of qty, the frame having a date column "_day"; days missing or qty 0 left out."""
    import polars as pl
    blk = pl.lit(block) if isinstance(block, str) else block
    f = (frame.select(pl.col("_day"), qty.cast(pl.Float64).alias("_q"), blk.alias("_b"))
              .filter(pl.col("_day").is_not_null() & (pl.col("_q") != 0))
              .group_by(["_day", "_b"]).agg(pl.col("_q").sum()))
    out: Counter = Counter()
    for day, blk_value, value in f.iter_rows():
        out[(day, blk_value)] += int(value)
    return out


def _qty(column: str, default: int = 1) -> "pl.Expr":
    import polars as pl
    return pl.col(column).cast(pl.Float64, strict=False).fill_null(default)


def _iso(column: str) -> "pl.Expr":
    """Dates that start with YYYY-MM-DD."""
    import polars as pl
    return pl.col(column).cast(pl.Utf8).str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)


def _ajio_date(column: str) -> "pl.Expr":
    """AJIO writes 'Wed Sep 30 23:21:44 IST 2026'."""
    import polars as pl
    return (pl.col(column).cast(pl.Utf8).str.replace(" IST ", " ", literal=True)
              .str.to_datetime("%a %b %d %H:%M:%S %Y", strict=False).dt.date())


def _text(column: str) -> "pl.Expr":
    """The column as stripped upper text; a missing value as "" (never equal to a status)."""
    import polars as pl
    return pl.col(column).cast(pl.Utf8).str.strip_chars().str.to_uppercase().fill_null("")


def myntra_orders(df) -> dict[str, Counter]:
    import polars as pl

    from ..core.tables import to_polars
    d = to_polars(df).with_columns(_iso("created on").alias("_day"))
    block = pl.when(_text("po_type").is_in(sorted(SJIT_MODELS))).then(pl.lit("SJIT")).otherwise(pl.lit("MYNTRA"))
    status = _text("order status")
    cancel = status == "F"
    rto = ~cancel & (pl.col("rto creation date").is_not_null() | (status == "RTO"))
    returned = ~cancel & (rto | pl.col("return creation date").is_not_null())
    one = pl.lit(1)
    return {"GROSS": _count(d, one, block), "RETURN": _count(d, pl.when(returned).then(1).otherwise(0), block),
            "CANCEL": _count(d, pl.when(cancel).then(1).otherwise(0), block)}


def flipkart_orders(df) -> dict[str, Counter]:
    import polars as pl

    from ..core.tables import to_polars
    d = to_polars(df).with_columns(_iso("order_date").alias("_day"))
    qty = _qty("quantity")
    kind = pl.col("fulfilment_type").cast(pl.Utf8).fill_null("nan").str.replace_all(r"[\s_]", "").str.to_uppercase()
    block = pl.when(kind == "FBF").then(pl.lit("FBF")).otherwise(pl.lit("FLIPKART"))
    status = _text("order_item_status")
    return {"GROSS": _count(d, qty, block),
            "RETURN": _count(d, pl.when(status.is_in(["RETURNED", "RETURN_REQUESTED"])).then(qty).otherwise(0), block),
            "CANCEL": _count(d, pl.when(status == "CANCELLED").then(qty).otherwise(0), block)}


def ajio_orders(orders, rtv) -> dict[str, Counter]:
    import polars as pl

    from ..core.tables import to_polars
    o = to_polars(orders).with_columns(_ajio_date("cust order date").alias("_day"))
    first_day = (o.select(pl.col("cust order no"), pl.col("_day")).drop_nulls()
                  .group_by("cust order no").agg(pl.col("_day").min()))
    r = to_polars(rtv)
    r = r.filter(~pl.col("3pl delivery status").cast(pl.Utf8).fill_null("nan").str.to_lowercase().str.contains("cancel"))
    r = r.unique(subset=["return order number", "seller sku"], keep="first", maintain_order=True)
    matched = r.join(first_day, on="cust order no", how="inner")
    return {"GROSS": _count(o, _qty("order qty"), "AJIO B2C"),
            "CANCEL": _count(o, _qty("cancelled qty", 0), "AJIO B2C"),
            "RETURN": _count(matched, _qty("return qty"), "AJIO B2C")}


def oms_metric(status: str) -> str | None:
    """RETURN / CANCEL for an OMSGuru line status; None for a line still sold."""
    low = status.strip().casefold()
    if low in OMS_RETURN:
        return "RETURN"
    if low in OMS_CANCEL:
        return "CANCEL"
    return None


def last_day(counted: dict[str, Counter]) -> date | None:
    return max((day for day, _ in counted["GROSS"]), default=None)
