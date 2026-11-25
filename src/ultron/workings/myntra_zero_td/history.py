"""MYNTRA ZERO TD MASTER (owner, 25 Nov 2026): which style was live at MRP, how many times, on which days and in
which months. Drive AGENT WORK/MYNTRA/MYNTRA ZERO TD SHEETS/MYNTRA ZERO TD MASTER.xlsx, written anew every run from
its own LOG plus the run's styles at MRP (Drive keeps the old versions):

  STYLE SUMMARY  one row per style (ACCOUNTS: every account that has it): TIMES AT MRP (checks that found it at MRP), ZERO TD / PART ZERO TD
                 times, DAYS, FIRST / LAST AT MRP, LAST STATUS, MAX STOCK AT MRP, DATES (newest first), then the
                 times per month (NOV-26 ...); most times first
  DAY WISE       one row per style + day: TIMES that day, the check times, MAX STOCK AT MRP
  MONTH WISE     per month and (first) account: styles at MRP, times, checks run
  RUNS           every check: CHECKED AT, STYLES CHECKED, AT MRP (so a count can be read against the checks run)
  LOG            every style at MRP of every check (the source of the sheets above)

The first run with no master builds the LOG from every saved run workbook (MYNTRA ZERO TD SHEETS/<MON-YY>/<dd-mm-yy>/
ZERO TD dd-mm-yy hh.mm AM.xlsx); `run.py myntra-zero-td --rebuild-master` does it again.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import polars as pl

log = logging.getLogger("bindal.myntra_zero_td")

NAME = "MYNTRA ZERO TD MASTER.xlsx"
LOG_SCHEMA = {"CHECKED AT": pl.Datetime("us"), "ACCOUNT": pl.Utf8, "ACCOUNTS": pl.Utf8, "STYLE ID": pl.Int64, "BRAND": pl.Utf8,
              "SKU": pl.Utf8, "STATUS": pl.Utf8, "MRP": pl.Float64, "SELLING PRICE": pl.Float64,
              "SIZES AT MRP": pl.Utf8, "STOCK AT MRP": pl.Int64}
RUN_SCHEMA = {"CHECKED AT": pl.Datetime("us"), "STYLES CHECKED": pl.Int64, "AT MRP": pl.Int64}
FILE_TIME = re.compile(r"ZERO TD (\d{2}-\d{2}-\d{2}) (\d{2})\.(\d{2}) ([AP]M)", re.I)


def _typed(df: pl.DataFrame, schema: dict) -> pl.DataFrame:
    """df in schema's columns and types (a missing column empty; a date written as text parsed)."""
    out = []
    for c, t in schema.items():
        col = pl.col(c) if c in df.columns else pl.lit(None)
        if t == pl.Int64:
            col = col.cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False).cast(pl.Int64)
        elif t == pl.Float64:
            col = col.cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False)
        elif isinstance(t, pl.Datetime) and c in df.columns and df.schema[c] == pl.Utf8:
            col = col.str.to_datetime(strict=False)
        col = col.cast(t, strict=False)
        out.append(col.alias(c))
    return df.select(out)


def run_rows(checked: dict[str, pl.DataFrame], when: datetime, flagged: tuple[str, ...]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(LOG rows: this check's styles at MRP, RUNS row) of one check."""
    frames = []
    for account, df in checked.items():
        sku = [c for c in ("FINAL SKU", "MASTER STYLE CODE", "MY SKU") if c in df.columns]
        frames.append(df.filter(pl.col("STATUS").is_in(flagged)).with_columns(
            pl.lit(when).alias("CHECKED AT"), pl.lit(account).alias("ACCOUNT"),
            (pl.coalesce(*sku) if sku else pl.lit(None, pl.Utf8)).cast(pl.Utf8).alias("SKU")))
    rows = _typed(pl.concat(frames, how="diagonal_relaxed"), LOG_SCHEMA) if frames else pl.DataFrame(schema=LOG_SCHEMA)
    # each style once per check (owner, 25 Nov 2026): under its first account, ACCOUNTS = every account that has it
    # (an old check had a style on several account tabs)
    names = rows.with_columns(pl.coalesce("ACCOUNTS", "ACCOUNT").str.split(", ").alias("_a")).group_by(
        "STYLE ID", maintain_order=True).agg(pl.col("_a").explode().unique(maintain_order=True).str.join(", ").alias("_all"))
    rows = (rows.unique("STYLE ID", keep="first", maintain_order=True).join(names, on="STYLE ID", how="left")
                .with_columns(pl.col("_all").alias("ACCOUNTS")).select(list(LOG_SCHEMA)))
    run = pl.DataFrame([{"CHECKED AT": when, "STYLES CHECKED": sum(df.height for df in checked.values()),
                         "AT MRP": rows.height}], schema=RUN_SCHEMA)
    return rows, run


def when_of(name: str) -> datetime | None:
    """The check time in a run workbook's name ("ZERO TD 25-11-26 05.15 PM.xlsx")."""
    m = FILE_TIME.search(name)
    return datetime.strptime(f"{m[1]} {m[2]}:{m[3]} {m[4].upper()}", "%d-%m-%y %I:%M %p") if m else None


def workbook_rows(path: Path, accounts: list[str], flagged: tuple[str, ...]) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """(LOG rows, RUNS row) of one saved run workbook (its account tabs hold only the styles at MRP)."""
    when = when_of(path.name)
    if when is None:
        return None
    tabs = pl.read_excel(path, sheet_id=0, engine="calamine", raise_if_empty=False)
    checked = {}
    for name, df in tabs.items():
        df = df.rename({c: str(c).strip().upper() for c in df.columns})
        if str(name).upper() in accounts and "STATUS" in df.columns:
            checked[str(name).upper()] = df.with_columns(pl.col("STATUS").cast(pl.Utf8))
    rows, run = run_rows(checked, when, flagged)
    summary = tabs.get("SUMMARY")
    if summary is not None and "STYLES" in summary.columns:
        styles = summary["STYLES"].cast(pl.Utf8).cast(pl.Float64, strict=False).sum()
        run = run.with_columns(pl.lit(int(styles or 0)).cast(pl.Int64).alias("STYLES CHECKED"))
    return rows, run


def read(path: Path | None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(LOG, RUNS) of the master at path; empty when there is none."""
    if path is None or not Path(path).exists():
        return pl.DataFrame(schema=LOG_SCHEMA), pl.DataFrame(schema=RUN_SCHEMA)
    tabs = pl.read_excel(path, sheet_id=0, engine="calamine", raise_if_empty=False)
    get = {str(k).upper(): v for k, v in tabs.items()}
    return (_typed(get.get("LOG", pl.DataFrame()), LOG_SCHEMA), _typed(get.get("RUNS", pl.DataFrame()), RUN_SCHEMA))


def merge(old: tuple[pl.DataFrame, pl.DataFrame], new: tuple[pl.DataFrame, pl.DataFrame]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """LOG and RUNS with the new rows; a check already there (same CHECKED AT) is not counted twice."""
    seen = set(old[1]["CHECKED AT"].to_list())
    fresh = [t for t in new[1]["CHECKED AT"].to_list() if t not in seen]
    rows = pl.concat([old[0], new[0].filter(pl.col("CHECKED AT").is_in(fresh))])
    runs = pl.concat([old[1], new[1].filter(pl.col("CHECKED AT").is_in(fresh))])
    return (rows.sort("CHECKED AT", maintain_order=True).unique(["CHECKED AT", "STYLE ID"], keep="first",
                                                                  maintain_order=True),
            runs.sort("CHECKED AT").unique("CHECKED AT", keep="first", maintain_order=True))


def _month(col: str) -> pl.Expr:
    return pl.col(col).dt.strftime("%b-%y").str.to_uppercase()


def sheets(rows: pl.DataFrame, runs: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """The master's sheets from LOG and RUNS."""
    rows = rows.with_columns(pl.col("CHECKED AT").dt.date().alias("DATE"), _month("CHECKED AT").alias("MONTH"))
    key = ["STYLE ID"]                 # a style once, whatever accounts have it (owner, 25 Nov 2026)
    accounts = pl.col("ACCOUNTS").str.split(", ").explode().unique().sort().str.join(", ").alias("ACCOUNTS")
    last = rows.sort("CHECKED AT").group_by(key).agg(
        accounts, pl.col("BRAND").drop_nulls().last(), pl.col("SKU").drop_nulls().last(), pl.col("STATUS").last().alias("LAST STATUS"))
    summary = rows.group_by(key).agg(
        pl.len().alias("TIMES AT MRP"),
        (pl.col("STATUS") == "ZERO TD").sum().alias("ZERO TD TIMES"),
        (pl.col("STATUS") == "PART ZERO TD").sum().alias("PART ZERO TD TIMES"),
        pl.col("DATE").n_unique().alias("DAYS"),
        pl.col("CHECKED AT").min().alias("FIRST AT MRP"), pl.col("CHECKED AT").max().alias("LAST AT MRP"),
        pl.col("STOCK AT MRP").max().alias("MAX STOCK AT MRP"),
        pl.col("DATE").unique().sort(descending=True).dt.strftime("%d-%m-%y").str.join(", ").alias("DATES"))
    months = sorted(rows["MONTH"].unique().to_list(), key=lambda m: datetime.strptime(m, "%b-%y"))
    if months:
        per = rows.group_by(key).agg(*[(pl.col("MONTH") == m).sum().alias(m) for m in months])
        summary = summary.join(per, on=key, how="left")
    summary = (summary.join(last, on=key, how="left")
                      .select(*key, "ACCOUNTS", "BRAND", "SKU", "TIMES AT MRP", "ZERO TD TIMES", "PART ZERO TD TIMES", "DAYS",
                              "FIRST AT MRP", "LAST AT MRP", "LAST STATUS", "MAX STOCK AT MRP", "DATES", *months)
                      .sort(["TIMES AT MRP", "LAST AT MRP"], descending=True))
    day = (rows.sort("CHECKED AT").group_by([*key, "DATE"], maintain_order=True)
               .agg(accounts, pl.col("BRAND").drop_nulls().last(), pl.col("SKU").drop_nulls().last(),
                    pl.len().alias("TIMES"),
                    pl.col("CHECKED AT").dt.strftime("%I:%M %p").str.join(", ").alias("CHECK TIMES"),
                    pl.col("STOCK AT MRP").max().alias("MAX STOCK AT MRP"))
               .select("DATE", *key, "ACCOUNTS", "BRAND", "SKU", "TIMES", "CHECK TIMES", "MAX STOCK AT MRP")
               .sort(["DATE", "TIMES"], descending=True))
    checks = runs.group_by(_month("CHECKED AT").alias("MONTH")).agg(pl.len().alias("CHECKS RUN"))
    month = (rows.group_by("MONTH", "ACCOUNT").agg(pl.col("STYLE ID").n_unique().alias("STYLES AT MRP"),
                                                    pl.len().alias("TIMES AT MRP"))
                 .join(checks, on="MONTH", how="left")
                 .sort(pl.col("MONTH").str.to_datetime("%b-%y", strict=False), "ACCOUNT", descending=[True, False]))
    return {"STYLE SUMMARY": summary, "DAY WISE": day, "MONTH WISE": month,
            "RUNS": runs.sort("CHECKED AT", descending=True),
            "LOG": rows.drop("DATE", "MONTH").sort("CHECKED AT", descending=True)}


def write(path: Path, rows: pl.DataFrame, runs: pl.DataFrame) -> Path:
    """The master workbook (xlsxwriter): red headers, frozen, filtered, a style id a link to its page."""
    import xlsxwriter
    from datetime import date
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "strings_to_formulas": False,
                                         "strings_to_urls": False, "nan_inf_to_errors": True})
    head = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#C0392B", "pattern": 1})
    link = wb.add_format({"font_color": "#0563C1", "underline": 1})
    stamp, day = wb.add_format({"num_format": "dd-mm-yy hh:mm AM/PM"}), wb.add_format({"num_format": "dd-mm-yy"})
    for name, df in sheets(rows, runs).items():
        ws = wb.add_worksheet(name)
        widths = [len(c) + 2 for c in df.columns]
        ws.write_row(0, 0, df.columns, head)
        for i, row in enumerate(df.iter_rows(), start=1):
            for j, v in enumerate(row):
                if v is None:
                    continue
                if i < 300:
                    widths[j] = max(widths[j], min(len(str(v)), 60) + 2)
                if df.columns[j] == "STYLE ID":
                    ws.write_url(i, j, f"https://www.myntra.com/{v}", link, string=str(v))
                elif isinstance(v, datetime):
                    ws.write_datetime(i, j, v, stamp)
                elif isinstance(v, date):
                    ws.write_datetime(i, j, datetime(v.year, v.month, v.day), day)
                elif isinstance(v, (int, float)):
                    ws.write_number(i, j, v)
                else:
                    ws.write_string(i, j, str(v))
        for j, w in enumerate(widths):
            ws.set_column(j, j, min(60, max(10, w)))
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, max(df.height, 1), max(df.width - 1, 0))
    wb.close()
    return path


def from_saved_runs(folder, work: Path, accounts: list[str], flagged: tuple[str, ...]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(LOG, RUNS) from every run workbook saved in the zero TD folder (<MON-YY>/<dd-mm-yy>/ZERO TD ....xlsx)."""
    parts = []
    for mname, m in folder.children().items():
        if m["mimeType"] != folder.FOLDER:
            continue
        month = folder.__class__(m["id"], folder.http)
        for dname, d in month.children().items():
            if d["mimeType"] != folder.FOLDER:
                continue
            for path in month.__class__(d["id"], folder.http).download_all(work / mname / dname):
                got = workbook_rows(path, accounts, flagged)
                if got:
                    parts.append(got)
    log.info("%s: %d saved checks read", NAME, len(parts))
    if not parts:
        return pl.DataFrame(schema=LOG_SCHEMA), pl.DataFrame(schema=RUN_SCHEMA)
    empty = (pl.DataFrame(schema=LOG_SCHEMA), pl.DataFrame(schema=RUN_SCHEMA))
    return merge(empty, (pl.concat([p[0] for p in parts]), pl.concat([p[1] for p in parts])))


def this_month(rows: pl.DataFrame, when: datetime) -> dict[int, int]:
    """style id -> times at MRP in when's month."""
    m = rows.filter((pl.col("CHECKED AT").dt.year() == when.year) & (pl.col("CHECKED AT").dt.month() == when.month))
    return dict(m.group_by("STYLE ID").len().iter_rows())
