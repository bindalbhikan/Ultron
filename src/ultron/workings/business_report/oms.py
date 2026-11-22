"""OMSGuru's order lines in the Flipkart and AJIO analysis (owner's rule, 3 Nov 2026: OMSGuru's sale and return status).

  OMSGURU REPORT  one file a month in PORTAL REPORTS: every line of the channels Flipkart, Ajio and Ajio Api (Ajio up to
                  Feb-26, Ajio Api after), by order date: order id, SKU (the FINAL SKU of MasterSheet), qty, status, value.

Checked against the portals' own reports, Jan-26 to Sep-26, on 43,000 one-line orders: Delivered, Cancelled and Cancelled
Before Shipping mean the same; Return Init / Return Received = customer return; Cancelled Return Received and Cancel
Init = RTO. It is not whole: Flipkart FBF orders are not in it, and most orders cancelled before shipping are not.
So it corrects a line the reports have, and adds a line only in a month with no fuller report.

Polars (docs/libraries/06-polars.md). An OMSGuru table carries `_i`, its row number: a raw line's match is that number.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

FINAL = {"cancelled": "Cancelled", "cancelled before shipping": "Cancelled",
         "cancelled return received": "RTO", "partial cancelled return received": "RTO", "cancel init": "RTO",
         "return init": "Customer Return", "return received": "Customer Return", "partial return received": "Customer Return",
         "delivered": "Delivered"}
COLUMNS = ["DAY", "CHANNEL", "ORDER", "SKU", "QTY", "STATUS", "VALUE"]
SCHEMA = {"DAY": pl.Datetime("us"), "CHANNEL": pl.Utf8, "ORDER": pl.Utf8, "SKU": pl.Utf8, "QTY": pl.Float64,
          "STATUS": pl.Utf8, "VALUE": pl.Float64, "_file": pl.Utf8, "FINAL": pl.Utf8, "_i": pl.Int64}


def rows_of(lines: list[dict], names: dict[str, str]) -> list[list]:
    """OMSGuru order list lines (ultron.portals.omsguru_orders) as one row per SKU (COLUMNS), exact repeats once."""
    out, seen = [], set()
    for r in lines:
        for sku, qty in (r["skus"] or [("", r["qty"])]):
            row = [r["day"], names.get(r["channel"], r["channel"]), r["order"], sku.upper(), qty, r["status"].strip(), r["value"]]
            key = (row[1], row[2], row[3], row[0], row[4], row[5])
            if key not in seen:
                seen.add(key)
                out.append(row)
    return out


def write(path: Path, rows: list[list]) -> Path:
    """An OMSGURU REPORT file (one sheet: COLUMNS)."""
    from ..core.xlsx import write_sheets
    return write_sheets(path, {"Sheet1": (COLUMNS, rows)})


def _day(e: pl.Expr) -> pl.Expr:
    s = e.cast(pl.Utf8).str.strip_chars().str.slice(0, 19)
    return pl.coalesce(s.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False, time_unit="us"),
                       s.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us"))).dt.truncate("1d")


def read(files: list[Path]) -> pl.DataFrame:
    from ..core.tables import pnum, read_excel_text
    frames = [read_excel_text(f, 0).with_columns(_file=pl.lit(f.name)) for f in files]
    frames = [f for f in frames if f.height]
    if not frames:
        return pl.DataFrame(schema=SCHEMA)
    df = pl.concat(frames, how="diagonal_relaxed")
    for c in COLUMNS:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
    return df.select(
        _day(pl.col("DAY")).alias("DAY"), "CHANNEL",
        pl.col("ORDER").fill_null("nan").str.strip_chars().alias("ORDER"),
        pl.col("SKU").fill_null("").str.strip_chars().str.to_uppercase().alias("SKU"),
        pnum(pl.col("QTY")).fill_null(1).alias("QTY"), "STATUS", pnum(pl.col("VALUE")).alias("VALUE"), "_file",
        pl.col("STATUS").str.strip_chars().str.to_lowercase().replace_strict(FINAL, default="In Transit").alias("FINAL"),
    ).with_row_index("_i").with_columns(pl.col("_i").cast(pl.Int64)).select(list(SCHEMA))


def match(raw: pl.DataFrame, id_col: str, oms: pl.DataFrame) -> tuple[pl.Series, set]:
    """For every raw line its OMSGuru row (`_i`, -1 = none), and the rows used. By order id + FINAL SKU, the nth line with
    the nth; then a line left over with the only row left of its order (a SKU spelled otherwise in the master)."""
    a = raw.select(i=pl.col(id_col).cast(pl.Utf8).fill_null("nan").str.strip_chars(),
                   s=pl.col("FINAL SKU").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase()) \
           .with_row_index("_r").with_columns(n=pl.int_range(pl.len()).over(["i", "s"]))
    b = oms.select("_i", i="ORDER", s="SKU").with_columns(n=pl.int_range(pl.len()).over(["i", "s"]))
    first = a.join(b, on=["i", "s", "n"], how="left", maintain_order="left").with_columns(pl.col("_i").fill_null(-1))
    used = set(first.filter(pl.col("_i") >= 0)["_i"].to_list())
    left = oms.filter(~pl.col("_i").is_in(list(used)))
    alone = left.filter(pl.len().over("ORDER") == 1).select(i="ORDER", _alone="_i")
    waiting = first.filter(pl.col("_i") < 0)
    single = waiting.filter(pl.len().over("i") == 1).join(alone, on="i", how="inner").select("_r", "_alone")
    out = first.join(single, on="_r", how="left", maintain_order="left").select(pl.coalesce("_alone", "_i"))
    used |= set(single["_alone"].to_list())
    return out.to_series().alias("_m"), used


def status_of(raw: pl.DataFrame, found: pl.Series, oms: pl.DataFrame) -> tuple[pl.Series, pl.Series]:
    """(OMSGuru's status, its final status) of every raw line, blank when it has none."""
    got = pl.DataFrame({"_i": found}).join(oms.select("_i", "STATUS", "FINAL"), on="_i", how="left", maintain_order="left")
    has = (found >= 0)
    text = pl.select(pl.when(has).then(got["STATUS"]).otherwise(pl.lit(""))).to_series()
    final = pl.select(pl.when(has).then(got["FINAL"]).otherwise(pl.lit(""))).to_series()
    return text, final


def corrected(current: pl.Series, final: pl.Series, keep: pl.Series) -> pl.Series:
    """The final status after OMSGuru: a cancellation it shows replaces Delivered, In Transit or Return Type Pending; its
    Delivered replaces In Transit. keep: lines a return report has settled are not touched."""
    open_line = current.is_in(["Delivered", "In Transit", "Return Type Pending"]) & ~keep
    # a return or an RTO only from the portal's returns report (owner, 16 Nov 2026), never from OMSGuru
    hit = (open_line & (final == "Cancelled")).fill_null(False)
    done = ((current == "In Transit") & (final == "Delivered")).fill_null(False)
    return pl.select(pl.when(hit).then(final).when(done).then(pl.lit("Delivered")).otherwise(current)).to_series()
