"""Return Analysis rendering of Business Reporting's canonical order lines.

No separate return classifier lives here: the same builders choose the order month, return
window, final status and returned quantities for both reports. The legacy engine only renders.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import polars as pl

from ..business_report import pipeline as business
from ..core.tables import read_excel_text
from . import engine

log = logging.getLogger(__name__)
KINDS = {"ORDER", "RETURN", "SALES", "MONTHLY", "OMSGURU"}


def template_source(rep):
    """Only the columns the analysis needs, once per portal, not per month/account."""
    needed = {"ORDER MONTH", "FINAL STATUS", "QTY", "ACCOUNT", "FINAL SKU", "MY SKU", "BRAND", "CATEGORY",
              "REASON", "STATE", "SELLER SKU CODE", "SKU", "SELLER SKU", "ORDER LINE ID", "ORDER ITEM ID", "CUST ORDER NO"}
    if rep.value:
        needed.add(rep.value)
    return rep.raw.select([c for c in rep.raw.columns if c in needed])


def template_rows(rep, month: date, account: str = "", cost_map=None, *, source=None):
    """The same known customer-return lines and units, in the existing analysis layout."""
    first = datetime(month.year, month.month, 1)
    if first in rep.unknown.get("tq", set()):
        raise ValueError("the order month's or next month's return report is missing")
    raw = source if source is not None else template_source(rep)
    raw = raw.filter((pl.col("ORDER MONTH") == first) & pl.col("FINAL STATUS").is_in(["Delivered", "Customer Return"]))
    if account:
        raw = raw.filter(pl.col("ACCOUNT") == account)
    if not raw.height:
        raise ValueError("no delivered or customer-return units for this order month")
    portal = rep.portal
    sku_col = {"MYNTRA": "SELLER SKU CODE", "FLIPKART": "SKU", "AJIO": "SELLER SKU"}[portal]
    id_col = {"MYNTRA": "ORDER LINE ID", "FLIPKART": "ORDER ITEM ID", "AJIO": "CUST ORDER NO"}[portal]
    qty = pl.col("QTY").cast(pl.Float64).cast(pl.Int64)
    price = pl.col(rep.value).cast(pl.Float64, strict=False) if rep.value else pl.lit(None, dtype=pl.Float64)
    if portal != "MYNTRA":
        price = price / qty
    name = f"MYNTRA {account}" if account else portal
    final_sku = pl.coalesce(pl.col("FINAL SKU"), pl.col("MY SKU"), pl.col(sku_col))
    frame = raw.select(
        pl.lit(f"{month:%m-%Y}").alias("MONTH"), pl.lit(name).alias("PORTAL"), "BRAND",
        pl.col(id_col).alias("ORDER ID"), pl.col(sku_col).alias("SELLER SKU CODE"), final_sku.alias("MY SKU"),
        qty.alias("QTY"), "CATEGORY",
        pl.when(pl.col("FINAL STATUS") == "Customer Return").then(pl.lit("Return"))
          .otherwise(pl.lit("Delivered")).alias("ORDER STATUS"),
        pl.when(pl.col("FINAL STATUS") == "Customer Return").then(pl.col("REASON").fill_null("blank"))
          .otherwise(pl.lit("blank")).alias("RETURN/EXCHANGE REASON"),
        price.alias("SALE PRICE"), pl.lit(None, dtype=pl.Float64).alias("COST"),
        (pl.col("STATE") if "STATE" in raw.columns else pl.lit(None, dtype=pl.Utf8)).alias("STATE"),
    )
    if cost_map is not None:
        frame = frame.with_columns(engine.cost_for(pl.col("MY SKU"), cost_map).alias("COST"))
    return frame


def load_context(supporting: Path):
    """Read the existing mapping/cost resources once for a monthly or yearly rebuild."""
    master = read_excel_text(supporting / "MasterSheet.xlsx", "Master")
    design_map, launch = engine.load_master(str(supporting))
    cost_map = engine.load_cost(str(supporting))
    return master, design_map, launch, cost_map


def load_reports(month: date, master, work: Path, *, files_by_portal=None, allowed=None):
    """The canonical builders once each; reusable for every month of a yearly rebuild."""
    reports, skipped, cats = {}, [], {}
    for portal in ("MYNTRA", "FLIPKART", "AJIO"):
        names = [f"MYNTRA {a}" for a in engine.MYNTRA_ACCOUNTS] if portal == "MYNTRA" else [portal]
        if allowed is not None and not any(n in allowed for n in names):
            continue
        first = business.START.get(portal, date(2025, 1, 1))
        try:
            files = (files_by_portal.get(portal, []) if files_by_portal is not None else
                     business.portal_files(portal, first, month, work, kinds=KINDS))
            if portal == "MYNTRA":
                rep, orders = business.build_myntra(files, master)
                cats = business.category_map(orders, master)
            elif portal == "FLIPKART":
                rep = business.build_flipkart(files, master, cats, first, include_earn_more=False)
            else:
                rep = business.build_ajio(files, master, cats, first)
        except Exception as exc:  # noqa: BLE001 - other portals can still be complete
            log.exception("%s canonical return lines could not be built", portal)
            skipped.append((portal, str(exc).splitlines()[0][:200]))
            continue
        reports[portal] = rep
    return reports, skipped


class NumbersDiffer(RuntimeError):
    """The return analysis would show other units than the business report for the same order month: not published."""


def business_figures(rep, month: date, account: str = "") -> tuple[float, float]:
    """(sold, returned) of an order month as the business report counts them on its own RAW DATA: sold = Delivered +
    Customer Return units, returned = Customer Return units (one account of Myntra when given)."""
    raw = rep.raw.filter(pl.col("ORDER MONTH") == datetime(month.year, month.month, 1))
    if account:
        raw = raw.filter(pl.col("ACCOUNT") == account)
    qty = pl.col("QTY").cast(pl.Float64)
    got = raw.select(qty.filter(pl.col("FINAL STATUS").is_in(["Delivered", "Customer Return"])).sum().alias("s"),
                     qty.filter(pl.col("FINAL STATUS") == "Customer Return").sum().alias("r")).row(0)
    return float(got[0] or 0), float(got[1] or 0)


def check_against_business(name: str, frame: pl.DataFrame, sold: float, returned: float) -> None:
    """The analysis' units must be the business report's, unit for unit (AGENTS.md: numbers that connect agree)."""
    mine = float(frame["QTY"].sum())
    back = float(frame.filter(pl.col("ORDER STATUS") == "Return")["QTY"].sum())
    if mine != sold or back != returned:
        raise NumbersDiffer(f"{name}: return analysis {mine:,.0f} sold / {back:,.0f} returned, business report "
                            f"{sold:,.0f} / {returned:,.0f} for the same order month: not published")


def build_month(month: date, supporting: Path, out: Path, work: Path, *, files_by_portal=None,
                allowed: set[str] | None = None, context=None, reports_by_portal=None):
    """Build from the same saved PORTAL REPORTS snapshots as business reporting.

    files_by_portal supplies local manifests for offline verification. A failed or unknown portal
    is named and excluded, never converted to a zero. No portal API or messaging is called here.
    """
    master, design_map, launch, cost_map = context if context is not None else load_context(supporting)
    if reports_by_portal is None:
        reports_by_portal, skipped = load_reports(month, master, work, files_by_portal=files_by_portal, allowed=allowed)
    else:
        skipped = []
    built, results = [], []
    tag = f"{month:%b-%y}".upper()
    for portal, rep in reports_by_portal.items():
        names = [f"MYNTRA {a}" for a in engine.MYNTRA_ACCOUNTS] if portal == "MYNTRA" else [portal]
        source = template_source(rep)
        for name in names:
            if allowed is not None and name not in allowed:
                continue
            try:
                frame = template_rows(rep, month, name.split()[-1] if portal == "MYNTRA" else "", cost_map, source=source)
            except ValueError as exc:
                skipped.append((name, str(exc)))
                continue
            account = name.split()[-1] if portal == "MYNTRA" else ""
            try:
                check_against_business(name, frame, *business_figures(rep, month, account))
            except NumbersDiffer as exc:
                log.error("%s", exc)
                skipped.append((name, str(exc)))
                continue
            stats = {"source": "Business Reporting order lines"}
            built.append((name, frame, stats))
            final = engine.write_template(frame, name, tag, str(out))
            report = engine.write_report(frame, name, tag, str(out), design_map, engine.launch_dates(launch, name))
            sold = int(final["QTY"].sum())
            returned = int(final.filter(pl.col("ORDER STATUS") == "Return")["QTY"].sum())
            results.append({"portal": name, "month": tag, "sold": sold, "returned": returned,
                            "rate": returned / sold * 100, "report": report,
                            "template": str(out / "Template" / f"{name} {tag} TEMPLATE.csv"), "stats": stats, "df": frame})
    results += engine.write_combined(built, str(out), design_map, launch, tag)
    return results, skipped
