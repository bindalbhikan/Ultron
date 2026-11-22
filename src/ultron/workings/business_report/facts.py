"""The agent's business facts: one small Parquet per portal, written with each business report.

    AGENT WORK/BUSINESS FACTS/<PORTAL>.parquet   one row per order line of the report's RAW DATA

Columns: PORTAL, ACCOUNT, ORDER DATE, ORDER MONTH, BRAND, CATEGORY, DESIGN-NO, QTY, VALUE (the sale value the
report uses; null where the portal gives none), FINAL STATUS, RETURN MONTH. No order ids, customer, address or
phone: the agent answers sale / return / GMV questions from it (tools/business.py) with the report's own
definitions, so its numbers are the report's numbers.
"""
from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

log = logging.getLogger("ultron")

FOLDER = "BUSINESS FACTS"
COLUMNS = ["PORTAL", "ACCOUNT", "ORDER DATE", "ORDER MONTH", "BRAND", "CATEGORY", "DESIGN-NO", "QTY", "VALUE",
           "FINAL STATUS", "RETURN MONTH"]


def facts(rep) -> pl.DataFrame:
    """The report's order lines, cut to the columns above (a missing one is null)."""
    raw: pl.DataFrame = rep.raw

    def col(name: str, dtype) -> pl.Expr:
        return (pl.col(name) if name in raw.columns else pl.lit(None)).cast(dtype, strict=False).alias(name)

    value = (pl.col(rep.value).cast(pl.Float64, strict=False) if rep.value and rep.value in raw.columns
             else pl.lit(None, dtype=pl.Float64)).alias("VALUE")
    return raw.select(
        pl.lit(rep.portal).alias("PORTAL"),
        col("ACCOUNT", pl.Utf8),
        pl.col("ORDER DATE").cast(pl.Date, strict=False).alias("ORDER DATE"),
        pl.col("ORDER MONTH").cast(pl.Date, strict=False).alias("ORDER MONTH"),
        col("BRAND", pl.Utf8), col("CATEGORY", pl.Utf8), col("DESIGN-NO", pl.Utf8),
        pl.col("QTY").cast(pl.Float64, strict=False).fill_null(0.0).alias("QTY"),
        value,
        pl.col("FINAL STATUS").cast(pl.Utf8).alias("FINAL STATUS"),
        col("RETURN MONTH", pl.Date),
    ).select(COLUMNS)


def upload(rep, out_dir: Path) -> None:
    """The portal's facts to Drive AGENT WORK/BUSINESS FACTS (replaced in place); a failure is logged, the report stands."""
    from ..core.drive import DriveFolder
    from ..core.config import agent_work_id
    try:
        path = out_dir / f"{rep.portal}.parquet"
        facts(rep).write_parquet(path, compression="zstd")
        DriveFolder(agent_work_id()).subfolder(FOLDER, create=True).put(path, "application/vnd.apache.parquet")
        log.info("Business facts of %s: %s (Drive AGENT WORK/%s)", rep.portal, path.name, FOLDER)
    except Exception:  # noqa: BLE001 - the agent's facts are extra; the workbook is the report
        log.exception("Business facts of %s not uploaded", rep.portal)
