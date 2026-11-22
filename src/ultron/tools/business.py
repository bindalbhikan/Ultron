"""Business numbers for the agent: sale, cancellations, RTO, returns, net sale and GMV, by portal, for any dates.

The facts are the business report's own order lines (workings/business_report/facts.py: one Parquet per portal
in Drive AGENT WORK/BUSINESS FACTS, refreshed with each report), so every number here is the report's number:

    Gross (sale)    every order line                       GMV = gross value
    Cancelled       FINAL STATUS Cancelled
    RTO             FINAL STATUS RTO                       RTO %    of dispatched (gross - cancelled)
    Customer return FINAL STATUS Customer Return           Return % of delivered + customer returns
    Net sale        FINAL STATUS Delivered (net qty, net value)

Dates are ORDER dates (what happened to the orders placed then), as in the report. A portal whose facts are not
there is named, never counted as 0. business_query answers anything else (brand, category, design, top N ...).
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path

from ..core.llm import tool

log = logging.getLogger("ultron")
PORTALS = ("MYNTRA", "FLIPKART", "AJIO")
_frames: dict = {}


def _facts():
    """Every portal's facts (Polars), from the local copy while it is Drive's file; {portal: frame}, and the missing."""
    import polars as pl

    from ..core.paths import output_root
    from ..workings.business_report.facts import FOLDER
    from ..workings.core.config import agent_work_id
    from ..workings.core.drive import DriveFolder
    cache = output_root() / "cache" / "business_facts"
    cache.mkdir(parents=True, exist_ok=True)
    folder = DriveFolder(agent_work_id()).subfolder(FOLDER)
    found, missing = {}, []
    children = folder.children() if folder else {}
    for p in PORTALS:
        path = folder.cached(f"{p}.parquet", cache, children.get(f"{p}.parquet")) if folder else None
        if path is None:
            missing.append(p)
            continue
        stamp = (str(path), Path(path).stat().st_mtime)
        if _frames.get(p, (None,))[0] != stamp:
            _frames[p] = (stamp, pl.read_parquet(path))
        found[p] = _frames[p][1]
    return found, missing


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def span(text: str) -> tuple[date, date]:
    """A period in plain words: "Oct-26", "oct 2026", "2026-10", "2026-10-05 to 2026-10-20", "last month", "this month",
    "yesterday", "last 7 days", or one date."""
    t = text.strip().lower()
    today = date.today()
    first = today.replace(day=1)
    if t in ("this month", "is mahine"):
        return first, today
    if t in ("last month", "pichle mahine", "previous month"):
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    if t in ("yesterday", "kal"):
        return today - timedelta(days=1), today - timedelta(days=1)
    if t in ("today", "aaj"):
        return today, today
    m = re.fullmatch(r"last (\d+) days?", t)
    if m:
        return today - timedelta(days=int(m.group(1))), today - timedelta(days=1)
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", t)
    if len(dates) == 2:
        return date.fromisoformat(dates[0]), date.fromisoformat(dates[1])
    if len(dates) == 1:
        d = date.fromisoformat(dates[0])
        return d, d
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t) or re.fullmatch(r"(\d{1,2})[-/](\d{4})", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        year, month = (a, b) if a > 31 else (b, a)
    else:
        m = re.fullmatch(r"([a-z]{3})[a-z]*[\s\-']*(\d{2,4})", t)
        if not m or m.group(1) not in MONTHS:
            raise ValueError(f"period {text!r} not understood: use e.g. Oct-26, 2026-10, 2026-10-01 to 2026-10-15, last month")
        month, year = MONTHS[m.group(1)], int(m.group(2))
        year += 2000 if year < 100 else 0
    start = date(year, month, 1)
    end = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
    return start, min(end, today)


def _fmt(n) -> str:
    return "-" if n is None else (f"{n:,.0f}" if abs(n) >= 100 else f"{n:,.1f}".rstrip("0").rstrip("."))


@tool
def business_numbers(period: str, portal: str = "all", by: str = "portal") -> str:
    """Sale, cancellations, RTO, customer returns, net sale (qty and value) and GMV of the orders placed in a period,
    from the business report's own order lines. Use it for any question about sale / returns / GMV / net qty.

    Args:
        period: e.g. "Oct-26", "2026-10", "2026-10-01 to 2026-10-15", "last month", "this month", "last 7 days".
        portal: "all", or MYNTRA, FLIPKART, AJIO (several with commas).
        by: "portal" (one row per portal), "month" (per order month), "portal,month", "account" or "brand".
    """
    import polars as pl
    start, end = span(period)
    frames, missing = _facts()
    want = PORTALS if portal.strip().lower() == "all" else tuple(p.strip().upper() for p in portal.split(","))
    data = [frames[p] for p in want if p in frames]
    if not data:
        return f"No business facts yet for {', '.join(want)} (they come with the next business report run)."
    d = pl.concat(data, how="diagonal_relaxed").filter(pl.col("ORDER DATE").is_between(start, end))
    keys = {"portal": ["PORTAL"], "month": ["ORDER MONTH"], "portal,month": ["PORTAL", "ORDER MONTH"],
            "account": ["PORTAL", "ACCOUNT"], "brand": ["BRAND"]}.get(by.replace(" ", ""), ["PORTAL"])
    st = pl.col("FINAL STATUS")
    agg = d.group_by(keys).agg(
        gq=pl.col("QTY").sum(), gv=pl.col("VALUE").sum(), has_v=pl.col("VALUE").is_not_null().any(),
        cq=pl.col("QTY").filter(st == "Cancelled").sum(), rq=pl.col("QTY").filter(st == "RTO").sum(),
        xq=pl.col("QTY").filter(st == "Customer Return").sum(), xv=pl.col("VALUE").filter(st == "Customer Return").sum(),
        nq=pl.col("QTY").filter(st == "Delivered").sum(), nv=pl.col("VALUE").filter(st == "Delivered").sum(),
    ).sort(keys)
    lines = [f"Orders placed {start:%d %b %Y} to {end:%d %b %Y} (by order date, the business report's numbers):",
             " | ".join([*keys, "Gross qty", "GMV", "Cancelled", "RTO", "RTO %", "Cust. return", "Return %",
                         "Return value", "Net qty", "Net sale value"])]
    for r in agg.iter_rows(named=True):
        disp, deliv = r["gq"] - r["cq"], r["nq"] + r["xq"]
        v = (lambda x: x) if r["has_v"] else (lambda x: None)   # noqa: E731 - a portal without values shows "-"
        lines.append(" | ".join([*(f"{r[k]:%b-%y}" if hasattr(r[k], "strftime") else str(r[k]) for k in keys),
                                 _fmt(r["gq"]), _fmt(v(r["gv"])), _fmt(r["cq"]), _fmt(r["rq"]),
                                 f"{r['rq'] / disp:.1%}" if disp else "-", _fmt(r["xq"]),
                                 f"{r['xq'] / deliv:.1%}" if deliv else "-", _fmt(v(r["xv"])), _fmt(r["nq"]),
                                 _fmt(v(r["nv"]))]))
    if agg.height == 0:
        lines.append("(no orders in this period)")
    if missing and portal.strip().lower() == "all":
        lines.append(f"Not included (no facts yet): {', '.join(missing)}")
    newest = d["ORDER DATE"].max() if d.height else None
    if newest and newest < end:
        lines.append(f"Note: the facts reach {newest:%d %b %Y}; later orders come with the next business report.")
    return "\n".join(lines)


@tool
def business_query(sql: str) -> str:
    """Any other question on the business facts, as one read-only SQL query over the table `facts` (columns: PORTAL,
    ACCOUNT, "ORDER DATE", "ORDER MONTH", BRAND, CATEGORY, "DESIGN-NO", QTY, VALUE, "FINAL STATUS", "RETURN MONTH";
    FINAL STATUS is Delivered, Customer Return, RTO, Cancelled, In Transit ...). Up to 50 rows come back.

    Args:
        sql: e.g. SELECT BRAND, SUM(QTY) AS qty FROM facts WHERE "FINAL STATUS"='Delivered' AND "ORDER MONTH"='2026-10-01' GROUP BY BRAND ORDER BY qty DESC LIMIT 10
    """
    import polars as pl
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or ";" in sql.strip().rstrip(";"):
        return "Error: one SELECT query only."
    frames, missing = _facts()
    if not frames:
        return "No business facts yet (they come with the next business report run)."
    ctx = pl.SQLContext(facts=pl.concat(list(frames.values()), how="diagonal_relaxed"), eager=True)
    try:
        out = ctx.execute(sql.strip().rstrip(";")).head(50)
    except Exception as exc:  # noqa: BLE001 - the model reads the error and fixes its query
        return f"Error: {type(exc).__name__}: {str(exc)[:300]}"
    with pl.Config(tbl_rows=50, tbl_cols=20, fmt_str_lengths=40, tbl_width_chars=200):
        text = str(out)
    return text + (f"\n(not included, no facts yet: {', '.join(missing)})" if missing else "")


TOOLS = [business_numbers, business_query]
