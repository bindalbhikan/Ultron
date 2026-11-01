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

from .workbook import Report

log = logging.getLogger("bindal.business_report")
ACCOUNT_OF = {"19170": "MAIN", "32207": "DBCC", "35426": "FMCC"}
MCOLS = ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]


def dt(s):
    d = pd.to_datetime(s, errors="coerce", format="mixed")
    return d.where(d > "2000-01-01")


def num(s):
    return pd.to_numeric(s, errors="coerce")


def ids(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.lstrip("'").replace({"nan": None, "None": None})


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


V = "SALE PRICE (FINAL AMOUNT)"
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
