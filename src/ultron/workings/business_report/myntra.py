"""Myntra sale / return analysis (business reporting): the owner's workbook (Drive AGENT WORK/BUSINESS
REPORTING, rules in docs/bots/business-report-context.md), its logic ported from the hand-run
scripts/3_build_workbook.py, the inputs from PORTAL REPORTS. The three accounts are one portal.

  ORDER REPORT    Seller_Orders_Report per account and month (one row per order line)
  RETURN REPORT   Seller_Returns_Report per account and month (returns + RTO lines)
  PAYMENT REPORT  every payout's line rows per account and month (Forward = sale settlement,
                  Reverse = return / RTO debit, NOD = SPF claims / adjustments)

FINAL STATUS per order line (CONTEXT.md):
  Customer Return = a returns line of type Return (exchanges included)
  Cancelled       = portal status F (SUB STATUS: before dispatch / after dispatch, came back as RTO)
  RTO             = portal status RTO, or an RTO line in the returns report
  Delivered       = portal status C and no return line
  In Transit      = SH / PK / WP
Sale value = final amount. NET SETTLEMENT = forward + reverse + NOD of the order line. Returns: the
newest line of an order line wins (later months' reports carry the late returns of earlier orders).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from typing import TYPE_CHECKING

from .workbook import Report
from ..core.tables import clean_id

if TYPE_CHECKING:
    import polars as pl

log = logging.getLogger("bindal.business_report")
ACCOUNT_OF = {"19170": "MAIN", "32207": "DBCC", "35426": "FMCC"}
MCOLS = ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]
V = "SALE PRICE (FINAL AMOUNT)"


def dt(s):
    d = pd.to_datetime(s, errors="coerce", format="mixed")
    return d.where(d > "2000-01-01")


def num(s):
    return pd.to_numeric(s, errors="coerce")


def ids(s: pd.Series) -> pd.Series:
    return clean_id(s.astype(str)).str.lstrip("'").replace({"nan": None, "None": None})


def payments(p: pd.DataFrame) -> pd.DataFrame:
    """The payment lines once each (the monthly files and the old dumps overlap)."""
    if not len(p):
        return p
    p = p.copy()
    for c in ["return_id", "NOD_Comment", "Logistics_Commission", "IGST_TCS", "CGST_TCS", "SGST_TCS", "TDS", "Commission"]:
        if c not in p.columns:
            p[c] = None
    p["Payment_Date"] = dt(p["Payment_Date"]).dt.normalize()
    for c in ["Settled_Amount", "Commission", "Logistics_Commission", "TDS", "IGST_TCS", "CGST_TCS", "SGST_TCS"]:
        p[c] = num(p[c]).fillna(0).round(2)
    p["Order_Type"] = p["Order_Type"].astype(str).str.strip().str.title()
    p["order_line_id"] = ids(p["order_line_id"])
    p = p.drop_duplicates(["Payment_Date", "utrNumber", "Order_Type", "order_line_id", "return_id", "Settled_Amount"])
    p["TAX"] = p["TDS"] + p["IGST_TCS"] + p["CGST_TCS"] + p["SGST_TCS"]
    p["ACCOUNT"] = ids(p["Seller_Id"]).map(ACCOUNT_OF)
    return p


def raw_data(o: pd.DataFrame, r: pd.DataFrame, m: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    o = o.copy()
    o["order line id"] = ids(o["order line id"])
    o = o.drop_duplicates("order line id", keep="last")
    mm = m[m["Channel Name"].str.startswith("MYNTRA", na=False)]
    by_code = mm.dropna(subset=["MYNTRA SKU CODE"]).drop_duplicates("MYNTRA SKU CODE").set_index("MYNTRA SKU CODE")[MCOLS]
    by_sku = m.drop_duplicates("Channel Listing SKU Code").set_index("Channel Listing SKU Code")[MCOLS]

    r = r.copy()
    for c in ["order_line_id", "exchange_id", "return_id", "order_id"]:
        r[c] = ids(r[c])
    r["EVENT DATE"] = dt(r["return_created_date"]).fillna(dt(r["order_rto_date"]))
    r = r.sort_values(["_order", "EVENT DATE"], na_position="first").drop_duplicates("order_line_id", keep="last")
    ret = r.set_index("order_line_id")
    exchange_release_ids = set(r["exchange_id"].dropna())

    fwd = rev = nod = pd.DataFrame()
    if len(p):
        fwd = p[p.Order_Type == "Forward"].groupby("order_line_id").agg(
            FWD_SETTLED=("Settled_Amount", "sum"), FWD_DATE=("Payment_Date", "max"), UTR=("utrNumber", "last"),
            COMMISSION=("Commission", "sum"), FWD_LOGISTICS=("Logistics_Commission", "sum"), TAX=("TAX", "sum"))
        rev = p[p.Order_Type == "Reverse"].groupby("order_line_id").agg(
            REV_SETTLED=("Settled_Amount", "sum"), REV_DATE=("Payment_Date", "max"),
            REV_LOGISTICS=("Logistics_Commission", "sum"))
        nod = p[p.Order_Type == "Nod"].groupby("order_line_id").agg(NOD=("Settled_Amount", "sum"))

    d = pd.DataFrame({
        "ACCOUNT": o["ACCOUNT"].values,
        "ORDER DATE": dt(o["created on"]).dt.normalize().values,
        "STORE ORDER ID": o["store order id"].astype(str).str.lstrip("'").values,
        "ORDER RELEASE ID": ids(o["order release id"]).values,
        "ORDER LINE ID": o["order line id"].values,
        "STYLE ID": ids(o["style id"]).values,
        "MYNTRA SKU CODE": o["myntra sku code"].values,
        "SELLER SKU CODE": o["seller sku code"].values,
    })
    d["ORDER MONTH"] = d["ORDER DATE"].dt.to_period("M").dt.to_timestamp()
    for c in MCOLS:
        d[c] = d["MYNTRA SKU CODE"].map(by_code[c]).fillna(d["SELLER SKU CODE"].map(by_sku[c]))
    d["BRAND"] = o["brand"].values
    d["CATEGORY"] = o["article type"].values
    d["SIZE"] = o["size"].values
    d["QTY"] = 1
    d["PO TYPE"] = o["po_type"].values
    d["MRP"] = num(o["total mrp"]).values
    d["DISCOUNT"] = num(o["discount"]).values
    d["SALE PRICE (FINAL AMOUNT)"] = num(o["final amount"]).values
    d["SELLER PRICE"] = num(o["seller price"]).values
    d["PORTAL ORDER STATUS"] = o["order status"].map(
        {"C": "Complete", "F": "Cancelled", "RTO": "RTO", "SH": "Shipped", "PK": "Packed", "WP": "WP"}).values

    oli = d["ORDER LINE ID"]
    rtype = oli.map(ret["type"])
    st = o["order status"].values
    final = np.select([rtype.eq("Return"), st == "F", rtype.eq("RTO") | (st == "RTO"), st == "C"],
                      ["Customer Return", "Cancelled", "RTO", "Delivered"], default="In Transit")
    d["FINAL STATUS"] = final
    sub = pd.Series(final, index=d.index)
    sub[(final == "Cancelled") & rtype.eq("RTO")] = "Cancelled after dispatch (came back as RTO)"
    sub[(final == "Cancelled") & rtype.isna()] = "Cancelled before dispatch"
    d["SUB STATUS"] = sub.values
    d["IS EXCHANGE REPLACEMENT ORDER"] = np.where(d["ORDER RELEASE ID"].isin(exchange_release_ids), "Yes", "No")
    canc_reason = o["cancellation reason"].values
    ret_reason = oli.map(ret["return_reason"])
    d["REASON"] = np.where(final == "Customer Return", ret_reason,
                           np.where(final == "RTO", pd.Series(canc_reason).fillna("RTO").values, canc_reason))
    d["DELIVERED DATE"] = dt(o["delivered on"]).dt.normalize().values
    d["CANCELLED DATE"] = dt(o["cancelled on"]).dt.normalize().values
    d["RTO DATE"] = dt(pd.Series(o["rto creation date"].values)).fillna(dt(oli.map(ret["order_rto_date"]))).dt.normalize().values
    d["RETURN CREATED DATE"] = dt(oli.map(ret["return_created_date"])).where(rtype.eq("Return")).values
    d["RETURN MONTH"] = pd.Series(d["RETURN CREATED DATE"]).dt.to_period("M").dt.to_timestamp().values
    d["RETURN ID"] = oli.map(ret["return_id"]).values
    d["RETURN PORTAL STATUS"] = oli.map(ret["status"]).values
    d["REFUNDED DATE"] = dt(oli.map(ret["refunded_date"])).values
    d["COURIER"] = o["courier code"].values
    d["CITY"] = o["city"].values
    d["STATE"] = o["state"].values
    for frame in (fwd, rev, nod):
        for c in frame.columns:
            d[c] = oli.map(frame[c]).values
    for c in ["FWD_SETTLED", "FWD_DATE", "UTR", "COMMISSION", "FWD_LOGISTICS", "TAX", "REV_SETTLED", "REV_DATE",
              "REV_LOGISTICS", "NOD"]:
        if c not in d.columns:
            d[c] = np.nan
    d = d.rename(columns={"FWD_SETTLED": "FWD SETTLED AMT", "FWD_DATE": "FWD PAYMENT DATE", "UTR": "FWD UTR",
                          "FWD_LOGISTICS": "FWD LOGISTICS", "TAX": "TCS + TDS", "REV_SETTLED": "REVERSE SETTLED AMT",
                          "REV_DATE": "REVERSE PAYMENT DATE", "REV_LOGISTICS": "RETURN LOGISTICS FEE", "NOD": "SPF / NOD AMT"})
    money = ["FWD SETTLED AMT", "REVERSE SETTLED AMT", "SPF / NOD AMT"]
    d["NET SETTLEMENT"] = d[money].fillna(0).sum(axis=1).where(d[money].notna().any(axis=1))
    hf, hr, fs = d["FWD SETTLED AMT"].notna(), d["REVERSE SETTLED AMT"].notna(), d["FINAL STATUS"]
    d["PAYMENT STATUS"] = np.select(
        [hf & hr, hf & fs.eq("Customer Return"), hf, hr, fs.eq("Delivered"), fs.eq("Customer Return")],
        ["Settled & Reversed", "Settled - Reverse Pending", "Settled", "Reverse Only", "Payment Pending",
         "No Payment (Returned)"], default="Not Applicable")
    return d.sort_values(["ORDER DATE", "ACCOUNT"]).reset_index(drop=True)



# ------------------------------------------------------------------ Polars (docs/libraries/06-polars.md)
# The same rules as the pandas code above, checked against it on real files (the golden business report run)
# before the switch. Dates in these reports are ISO: "2026-10-05", "... 12:34:56", "... 12:34:56.000".

def pdt(e: "pl.Expr") -> "pl.Expr":
    """A date column (ISO text) as a datetime; empty, unreadable or before 2000 (the 1970 of RTO lines) -> null."""
    import polars as pl
    s = e.cast(pl.Utf8).str.strip_chars()
    d = pl.coalesce(s.str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False),
                    s.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False),
                    s.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us")))
    return pl.when(d > pl.datetime(2000, 1, 1)).then(d).otherwise(None)


def pnum(e: "pl.Expr") -> "pl.Expr":
    import polars as pl
    return e.cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False)


def round2(e: "pl.Expr") -> "pl.Expr":
    """2 decimals exactly as pandas / numpy round them (x * 100, half to even, / 100): 13.145 -> 13.14, as the
    old reports had it, never a paisa off."""
    return (e * 100).round(0, mode="half_to_even") / 100


def pids(e: "pl.Expr") -> "pl.Expr":
    """An id as text: no ".0", no leading "'", "nan" / "None" as null."""
    import polars as pl
    s = e.cast(pl.Utf8).str.replace(r"\.0$", "").str.strip_chars_start("'")
    return s.replace({"nan": None, "None": None})          # keeps the column's name


def _month(e: "pl.Expr") -> "pl.Expr":
    return e.dt.truncate("1mo")


def payments_pl(p) -> "pl.DataFrame":
    """The payment lines once each (the monthly files and the old dumps overlap)."""
    import polars as pl

    from ..core.tables import to_polars
    p = to_polars(p)
    if not p.height:
        return p
    for c in ["return_id", "NOD_Comment", "Logistics_Commission", "IGST_TCS", "CGST_TCS", "SGST_TCS", "TDS", "Commission"]:
        if c not in p.columns:
            p = p.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
    money = ["Settled_Amount", "Commission", "Logistics_Commission", "TDS", "IGST_TCS", "CGST_TCS", "SGST_TCS"]
    p = p.with_columns(pdt(pl.col("Payment_Date")).dt.truncate("1d").alias("Payment_Date"),
                       *(round2(pnum(pl.col(c)).fill_null(0)).alias(c) for c in money),
                       pl.col("Order_Type").cast(pl.Utf8).fill_null("nan").str.strip_chars().str.to_titlecase()
                       .alias("Order_Type"),
                       pids(pl.col("order_line_id")).alias("order_line_id"))
    p = p.unique(subset=["Payment_Date", "utrNumber", "Order_Type", "order_line_id", "return_id", "Settled_Amount"],
                 keep="first", maintain_order=True)
    return p.with_columns((pl.col("TDS") + pl.col("IGST_TCS") + pl.col("CGST_TCS") + pl.col("SGST_TCS")).alias("TAX"),
                          pids(pl.col("Seller_Id")).replace_strict(ACCOUNT_OF, default=None).alias("ACCOUNT"))


def raw_data_pl(o, r, m, p) -> "pl.DataFrame":
    import polars as pl

    from ..core.tables import to_polars
    o, r, m, p = (to_polars(x) for x in (o, r, m, p))
    o = (o.with_columns(pids(pl.col("order line id")).alias("order line id"))
          .unique(subset=["order line id"], keep="last", maintain_order=True))
    mm = m.filter(pl.col("Channel Name").cast(pl.Utf8).str.starts_with("MYNTRA").fill_null(False))
    by_code = (mm.filter(pl.col("MYNTRA SKU CODE").is_not_null())
                 .unique(subset=["MYNTRA SKU CODE"], keep="first", maintain_order=True)
                 .select(pl.col("MYNTRA SKU CODE").alias("_code"), *(pl.col(c).alias(f"_c_{c}") for c in MCOLS)))
    by_sku = (m.unique(subset=["Channel Listing SKU Code"], keep="first", maintain_order=True)
               .select(pl.col("Channel Listing SKU Code").alias("_sku"), *(pl.col(c).alias(f"_s_{c}") for c in MCOLS)))

    r = r.with_columns(*(pids(pl.col(c)).alias(c) for c in ["order_line_id", "exchange_id", "return_id", "order_id"]))
    r = r.with_columns(pl.coalesce(pdt(pl.col("return_created_date")), pdt(pl.col("order_rto_date"))).alias("EVENT DATE"))
    r = (r.with_row_index("_row").sort(["_order", "EVENT DATE", "_row"], nulls_last=False)
          .unique(subset=["order_line_id"], keep="last", maintain_order=True))
    exchange_release_ids = r["exchange_id"].drop_nulls().unique().to_list()
    ret = r.select(pl.col("order_line_id").alias("_oli"), pl.col("type").alias("_rtype"),
                   pl.col("return_reason").alias("_rreason"), pl.col("order_rto_date").alias("_rrto"),
                   pl.col("return_created_date").alias("_rcreated"), pl.col("return_id").alias("_rid"),
                   pl.col("status").alias("_rstatus"), pl.col("refunded_date").alias("_rrefunded"))

    pay = []
    if p.height:
        fwd = p.filter(pl.col("Order_Type") == "Forward").group_by("order_line_id", maintain_order=True).agg(
            pl.col("Settled_Amount").sum().alias("FWD_SETTLED"), pl.col("Payment_Date").max().alias("FWD_DATE"),
            pl.col("utrNumber").drop_nulls().last().alias("UTR"), pl.col("Commission").sum().alias("COMMISSION"),
            pl.col("Logistics_Commission").sum().alias("FWD_LOGISTICS"), pl.col("TAX").sum().alias("TAX"))
        rev = p.filter(pl.col("Order_Type") == "Reverse").group_by("order_line_id", maintain_order=True).agg(
            pl.col("Settled_Amount").sum().alias("REV_SETTLED"), pl.col("Payment_Date").max().alias("REV_DATE"),
            pl.col("Logistics_Commission").sum().alias("REV_LOGISTICS"))
        nod = p.filter(pl.col("Order_Type") == "Nod").group_by("order_line_id", maintain_order=True).agg(
            pl.col("Settled_Amount").sum().alias("NOD"))
        pay = [f.filter(pl.col("order_line_id").is_not_null()).rename({"order_line_id": "_oli"}) for f in (fwd, rev, nod)]

    status_names = {"C": "Complete", "F": "Cancelled", "RTO": "RTO", "SH": "Shipped", "PK": "Packed", "WP": "WP"}
    d = o.select(
        pl.col("ACCOUNT"),
        pdt(pl.col("created on")).dt.truncate("1d").alias("ORDER DATE"),
        pl.col("store order id").cast(pl.Utf8).fill_null("nan").str.strip_chars_start("'").alias("STORE ORDER ID"),
        pids(pl.col("order release id")).alias("ORDER RELEASE ID"),
        pl.col("order line id").alias("ORDER LINE ID"),
        pids(pl.col("style id")).alias("STYLE ID"),
        pl.col("myntra sku code").alias("MYNTRA SKU CODE"),
        pl.col("seller sku code").alias("SELLER SKU CODE"),
        pl.col("brand").alias("_brand"), pl.col("article type").alias("_cat"), pl.col("size").alias("_size"),
        pl.col("po_type").alias("_po"), pnum(pl.col("total mrp")).alias("_mrp"), pnum(pl.col("discount")).alias("_disc"),
        pnum(pl.col("final amount")).alias("_final"), pnum(pl.col("seller price")).alias("_seller"),
        pl.col("order status").alias("_st"), pl.col("cancellation reason").alias("_canc"),
        pdt(pl.col("delivered on")).dt.truncate("1d").alias("_delivered"),
        pdt(pl.col("cancelled on")).dt.truncate("1d").alias("_cancelled"),
        pdt(pl.col("rto creation date")).alias("_orto"),
        pl.col("courier code").alias("_courier"), pl.col("city").alias("_city"), pl.col("state").alias("_state"))
    d = d.with_columns(_month(pl.col("ORDER DATE")).alias("ORDER MONTH"))
    d = (d.join(by_code, left_on="MYNTRA SKU CODE", right_on="_code", how="left", nulls_equal=False)
          .join(by_sku, left_on="SELLER SKU CODE", right_on="_sku", how="left", nulls_equal=True)
          .join(ret, left_on="ORDER LINE ID", right_on="_oli", how="left", nulls_equal=False))
    for f in pay:
        d = d.join(f, left_on="ORDER LINE ID", right_on="_oli", how="left", nulls_equal=False)
    rtype, st = pl.col("_rtype"), pl.col("_st")
    final = (pl.when(rtype == "Return").then(pl.lit("Customer Return"))
               .when(st == "F").then(pl.lit("Cancelled"))
               .when((rtype == "RTO") | (st == "RTO")).then(pl.lit("RTO"))
               .when(st == "C").then(pl.lit("Delivered")).otherwise(pl.lit("In Transit")))
    d = d.with_columns(final.alias("FINAL STATUS"))
    fs = pl.col("FINAL STATUS")
    d = d.with_columns(
        *(pl.coalesce(pl.col(f"_c_{c}"), pl.col(f"_s_{c}")).alias(c) for c in MCOLS),
        pl.lit(1).alias("QTY"),
        st.replace_strict(status_names, default=None).alias("PORTAL ORDER STATUS"),
        pl.when((fs == "Cancelled") & (rtype == "RTO").fill_null(False)).then(pl.lit("Cancelled after dispatch (came back as RTO)"))
          .when((fs == "Cancelled") & rtype.is_null()).then(pl.lit("Cancelled before dispatch")).otherwise(fs).alias("SUB STATUS"),
        pl.when(pl.col("ORDER RELEASE ID").is_in(exchange_release_ids).fill_null(False)).then(pl.lit("Yes"))
          .otherwise(pl.lit("No")).alias("IS EXCHANGE REPLACEMENT ORDER"),
        pl.when(fs == "Customer Return").then(pl.col("_rreason"))
          .when(fs == "RTO").then(pl.col("_canc").fill_null("RTO")).otherwise(pl.col("_canc")).alias("REASON"),
        pl.coalesce(pl.col("_orto"), pdt(pl.col("_rrto"))).dt.truncate("1d").alias("RTO DATE"),
        pl.when(rtype == "Return").then(pdt(pl.col("_rcreated"))).otherwise(None).alias("RETURN CREATED DATE"),
        pdt(pl.col("_rrefunded")).alias("REFUNDED DATE"))
    for c, dtype in (("FWD_SETTLED", pl.Float64), ("FWD_DATE", pl.Datetime("us")), ("UTR", pl.Utf8),
                     ("COMMISSION", pl.Float64), ("FWD_LOGISTICS", pl.Float64), ("TAX", pl.Float64),
                     ("REV_SETTLED", pl.Float64), ("REV_DATE", pl.Datetime("us")), ("REV_LOGISTICS", pl.Float64),
                     ("NOD", pl.Float64)):
        if c not in d.columns:
            d = d.with_columns(pl.lit(None, dtype=dtype).alias(c))
    money = [pl.col("FWD_SETTLED"), pl.col("REV_SETTLED"), pl.col("NOD")]
    any_money = pl.any_horizontal(*(c.is_not_null() for c in money))
    d = d.with_columns(
        _month(pl.col("RETURN CREATED DATE")).alias("RETURN MONTH"),
        pl.when(any_money).then(pl.sum_horizontal(*(c.fill_null(0) for c in money))).otherwise(None).alias("NET SETTLEMENT"))
    hf, hr = pl.col("FWD_SETTLED").is_not_null(), pl.col("REV_SETTLED").is_not_null()
    d = d.with_columns(
        pl.when(hf & hr).then(pl.lit("Settled & Reversed"))
          .when(hf & (fs == "Customer Return")).then(pl.lit("Settled - Reverse Pending"))
          .when(hf).then(pl.lit("Settled")).when(hr).then(pl.lit("Reverse Only"))
          .when(fs == "Delivered").then(pl.lit("Payment Pending"))
          .when(fs == "Customer Return").then(pl.lit("No Payment (Returned)"))
          .otherwise(pl.lit("Not Applicable")).alias("PAYMENT STATUS"))
    out = d.select(
        "ACCOUNT", "ORDER DATE", "STORE ORDER ID", "ORDER RELEASE ID", "ORDER LINE ID", "STYLE ID", "MYNTRA SKU CODE",
        "SELLER SKU CODE", "ORDER MONTH", *MCOLS, pl.col("_brand").alias("BRAND"), pl.col("_cat").alias("CATEGORY"),
        pl.col("_size").alias("SIZE"), "QTY", pl.col("_po").alias("PO TYPE"), pl.col("_mrp").alias("MRP"),
        pl.col("_disc").alias("DISCOUNT"), pl.col("_final").alias(V), pl.col("_seller").alias("SELLER PRICE"),
        "PORTAL ORDER STATUS", "FINAL STATUS", "SUB STATUS", "IS EXCHANGE REPLACEMENT ORDER", "REASON",
        pl.col("_delivered").alias("DELIVERED DATE"), pl.col("_cancelled").alias("CANCELLED DATE"), "RTO DATE",
        "RETURN CREATED DATE", "RETURN MONTH", pl.col("_rid").alias("RETURN ID"), pl.col("_rstatus").alias("RETURN PORTAL STATUS"),
        "REFUNDED DATE", pl.col("_courier").alias("COURIER"), pl.col("_city").alias("CITY"), pl.col("_state").alias("STATE"),
        pl.col("FWD_SETTLED").alias("FWD SETTLED AMT"), pl.col("FWD_DATE").alias("FWD PAYMENT DATE"),
        pl.col("UTR").alias("FWD UTR"), "COMMISSION", pl.col("FWD_LOGISTICS").alias("FWD LOGISTICS"),
        pl.col("TAX").alias("TCS + TDS"), pl.col("REV_SETTLED").alias("REVERSE SETTLED AMT"),
        pl.col("REV_DATE").alias("REVERSE PAYMENT DATE"), pl.col("REV_LOGISTICS").alias("RETURN LOGISTICS FEE"),
        pl.col("NOD").alias("SPF / NOD AMT"), "NET SETTLEMENT", "PAYMENT STATUS")
    return out.sort(["ORDER DATE", "ACCOUNT"], nulls_last=True, maintain_order=True)

RAW_COLS = ["ACCOUNT", "ORDER DATE", "ORDER MONTH", "STORE ORDER ID", "ORDER RELEASE ID", "ORDER LINE ID",
            "STYLE ID", "MYNTRA SKU CODE", "SELLER SKU CODE", "MY SKU", "FINAL SKU", "FINAL MY SKU",
            "DESIGN-NO", "BRAND", "CATEGORY", "SIZE", "QTY", "PO TYPE", "MRP", "DISCOUNT", V, "SELLER PRICE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "SUB STATUS", "REASON", "IS EXCHANGE REPLACEMENT ORDER",
            "DELIVERED DATE", "CANCELLED DATE", "RTO DATE", "RETURN CREATED DATE", "RETURN MONTH", "RETURN ID",
            "RETURN PORTAL STATUS", "REFUNDED DATE", "COURIER", "CITY", "STATE",
            "FWD SETTLED AMT", "FWD PAYMENT DATE", "FWD UTR", "COMMISSION", "FWD LOGISTICS", "TCS + TDS",
            "REVERSE SETTLED AMT", "REVERSE PAYMENT DATE", "RETURN LOGISTICS FEE", "SPF / NOD AMT", "NET SETTLEMENT",
            "PAYMENT STATUS"]
MONEY = {"MRP", "DISCOUNT", V, "SELLER PRICE", "FWD SETTLED AMT", "COMMISSION", "FWD LOGISTICS", "TCS + TDS",
         "REVERSE SETTLED AMT", "RETURN LOGISTICS FEE", "SPF / NOD AMT", "NET SETTLEMENT"}


def pay_months(p: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame | None:
    """Cash received by payment month (the second PAYMENT table, values)."""
    if not len(p):
        return None
    pp = p[p["Payment_Date"] >= start].copy()
    pp["M"] = pp["Payment_Date"].dt.to_period("M").dt.to_timestamp()
    t = pp.pivot_table(index="M", columns="Order_Type", values="Settled_Amount", aggfunc="sum", fill_value=0)
    t = t.reindex(columns=["Forward", "Reverse", "Nod"], fill_value=0)
    t.columns = ["Forward Settled", "Reverse Debit", "SPF / NOD"]
    t["Net Payout"] = t.sum(axis=1)
    f = pp[pp.Order_Type == "Forward"].groupby("M")
    t["Forward Lines"] = f.size()
    t["Reverse Lines"] = pp[pp.Order_Type == "Reverse"].groupby("M").size()
    t["Commission"] = f["Commission"].sum()
    t["Forward Logistics"] = f["Logistics_Commission"].sum()
    t["Return Logistics"] = pp[pp.Order_Type == "Reverse"].groupby("M")["Logistics_Commission"].sum()
    t["TCS + TDS"] = f["TAX"].sum()
    t = t.fillna(0)
    t["MoM %"] = t["Net Payout"].pct_change()
    t.iloc[0, t.columns.get_loc("MoM %")] = float("nan")
    return t


def pay_months_pl(p: "pl.DataFrame", start) -> pd.DataFrame | None:
    """Cash received by payment month (the second PAYMENT table, values), from Polars payment lines; a pandas
    table for the workbook (index M)."""
    import polars as pl

    from ..core.tables import to_pandas
    if p is None or not p.height:
        return None
    pp = p.filter(pl.col("Payment_Date") >= pl.lit(pd.Timestamp(start).to_pydatetime()))
    if not pp.height:
        return None
    pp = pp.with_columns(pl.col("Payment_Date").dt.truncate("1mo").alias("M"))
    kind = pl.col("Order_Type")

    def total(c: str, where) -> pl.Expr:
        return pl.col(c).filter(where).sum()
    t = (pp.group_by("M").agg(
            total("Settled_Amount", kind == "Forward").alias("Forward Settled"),
            total("Settled_Amount", kind == "Reverse").alias("Reverse Debit"),
            total("Settled_Amount", kind == "Nod").alias("SPF / NOD"),
            (kind == "Forward").sum().cast(pl.Float64).alias("Forward Lines"),
            (kind == "Reverse").sum().cast(pl.Float64).alias("Reverse Lines"),
            total("Commission", kind == "Forward").alias("Commission"),
            total("Logistics_Commission", kind == "Forward").alias("Forward Logistics"),
            total("Logistics_Commission", kind == "Reverse").alias("Return Logistics"),
            total("TAX", kind == "Forward").alias("TCS + TDS"))
          .sort("M")
          .with_columns((pl.col("Forward Settled") + pl.col("Reverse Debit") + pl.col("SPF / NOD")).alias("Net Payout")))
    t = t.with_columns((pl.col("Net Payout") / pl.col("Net Payout").shift(1) - 1).alias("MoM %"))
    t = t.select("M", "Forward Settled", "Reverse Debit", "SPF / NOD", "Net Payout", "Forward Lines", "Reverse Lines",
                 "Commission", "Forward Logistics", "Return Logistics", "TCS + TDS", "MoM %")
    out = to_pandas(t).set_index("M")
    out.index.name = "M"
    out.columns.name = None
    return out


def report_pl(raw: pd.DataFrame, p: "pl.DataFrame", input_log: pd.DataFrame) -> Report:
    """report() on the Polars payment lines (raw already a pandas table for the workbook)."""
    have_pay = raw["NET SETTLEMENT"].notna().any()
    return Report(
        portal="MYNTRA", raw=raw, raw_cols=RAW_COLS, value=V, settle="NET SETTLEMENT" if have_pay else None,
        money_cols=MONEY,
        pay_table=[("Forward Settled", "FWD SETTLED AMT"), ("Reverse Debit", "REVERSE SETTLED AMT"),
                   ("SPF / NOD", "SPF / NOD AMT"), ("Net Settlement", "NET SETTLEMENT"), ("Commission", "COMMISSION"),
                   ("Forward Logistics", "FWD LOGISTICS"), ("Return Logistics", "RETURN LOGISTICS FEE"),
                   ("TCS + TDS", "TCS + TDS")],
        pay_months=pay_months_pl(p, raw["ORDER MONTH"].min()), input_log=input_log, min_orders=500)


def report(raw: pd.DataFrame, p: pd.DataFrame, input_log: pd.DataFrame) -> Report:
    have_pay = raw["NET SETTLEMENT"].notna().any()
    return Report(
        portal="MYNTRA", raw=raw, raw_cols=RAW_COLS, value=V, settle="NET SETTLEMENT" if have_pay else None,
        money_cols=MONEY,
        pay_table=[("Forward Settled", "FWD SETTLED AMT"), ("Reverse Debit", "REVERSE SETTLED AMT"),
                   ("SPF / NOD", "SPF / NOD AMT"), ("Net Settlement", "NET SETTLEMENT"), ("Commission", "COMMISSION"),
                   ("Forward Logistics", "FWD LOGISTICS"), ("Return Logistics", "RETURN LOGISTICS FEE"),
                   ("TCS + TDS", "TCS + TDS")],
        pay_months=pay_months(p, raw["ORDER MONTH"].min()), input_log=input_log, min_orders=500)
