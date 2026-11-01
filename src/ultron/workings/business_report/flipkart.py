"""Flipkart sale / return analysis (business reporting): the Myntra layout (workbook.py) from the
Seller Hub reports kept in PORTAL REPORTS.

  ORDER REPORT    "Orders" (Fulfilment Reports): one row per order item, status, dates - no price
  RETURN REPORT   "Returns": one row per return line (customer_return / courier_return)
  PAYMENT REPORT  "Settled Transactions" (Payment Reports): the settlement of every order item
                  (Sale Amount, marketplace fee, commission, refund, bank settlement value)

FINAL STATUS of an order item:
  Customer Return     a return line of type customer_return (a cancelled return = not returned)
  RTO                 a return line of type courier_return
  Cancelled           portal status CANCELLED / REJECTED
  Delivered           portal status DELIVERED, no return line
  Return Type Pending portal status RETURNED / RETURN_REQUESTED without a return line: the type is
                      taken from the order's own return reason when that reason is only ever one
                      type, otherwise it waits for the returns report (never guessed)
  In Transit          anything else (READY_TO_SHIP, APPROVED, ...)

SALE VALUE = the item's Sale Amount in Settled Transactions (an item not settled yet has none:
the INPUT LOG says how many); NET SETTLEMENT = the sum of its Bank Settlement Values.
BRAND / design from MasterSheet (channel FLIPKART); CATEGORY = the article type Myntra lists the
same design under (else the SKU's category word).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .workbook import Report

log = logging.getLogger("bindal.business_report")

CATEGORY_WORDS = {"COORD": "Co-Ords", "DRESS": "Dresses", "TOP": "Tops", "JUMPSUIT": "Jumpsuit", "SHIRT": "Shirts"}


def clean(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace('"', "", regex=False).str.replace("SKU:", "", regex=False).str.strip()


def dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str[:19], errors="coerce", format="mixed")


def oi(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace("OI:", "", regex=False).str.strip()


# ------------------------------------------------------------------ inputs
def read_orders(files: list[Path]) -> pd.DataFrame:
    frames = [pd.read_excel(f, sheet_name="Orders", dtype=str).assign(_file=f.name) for f in files]
    o = pd.concat([f for f in frames if len(f)], ignore_index=True) if frames else pd.DataFrame()
    return o.drop_duplicates("order_item_id", keep="last") if len(o) else o


def read_returns(files: list[Path]) -> pd.DataFrame:
    frames = [pd.read_excel(f, sheet_name="Returns", dtype=str).assign(_file=f.name) for f in files]
    return pd.concat([f for f in frames if len(f)], ignore_index=True) if frames else pd.DataFrame()


def _col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).split("\n")[0]).strip()


def read_settled(files: list[Path]) -> pd.DataFrame:
    """The "Orders" sheet of Settled Transactions files (header on the 2nd row, a sub-header row below)."""
    frames = []
    for f in files:
        df = pd.read_excel(f, sheet_name="Orders", header=1, dtype=str)
        df.columns = [_col(c) for c in df.columns]
        df = df[df["Order item ID"].notna() & df["NEFT ID"].notna()]
        if len(df):
            frames.append(df.assign(_file=f.name))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


SETTLE_COLS = {"Sale Amount (Rs.)": "SALE AMOUNT", "Bank Settlement Value (Rs.)": "NET SETTLEMENT",
               "Marketplace Fee (Rs.)": "MARKETPLACE FEE", "Commission (Rs.)": "COMMISSION",
               "Shipping Fee (Rs.)": "SHIPPING FEE", "Reverse Shipping Fee (Rs.)": "REVERSE SHIPPING FEE",
               "Refund (Rs.)": "REFUND", "Protection Fund (Rs.)": "PROTECTION FUND", "TCS (Rs.)": "TCS", "TDS (Rs.)": "TDS"}


def settlement(st: pd.DataFrame) -> pd.DataFrame:
    """Per order item: SALE VALUE (its largest Sale Amount), the sums of the money columns, the last
    payment date and NEFT id."""
    if not len(st):
        return pd.DataFrame()
    s = st.copy()
    s["oi"] = oi(s["Order item ID"])
    for src, dst in SETTLE_COLS.items():
        s[dst] = pd.to_numeric(s.get(src), errors="coerce").fillna(0)
    s["PAY DATE"] = pd.to_datetime(s["Payment Date"], errors="coerce")
    s = s.drop_duplicates(["NEFT ID", "oi", "NET SETTLEMENT", "SALE AMOUNT", "PAY DATE"])
    g = s.groupby("oi")
    out = g[[c for c in SETTLE_COLS.values()]].sum()
    out["SALE VALUE"] = g["SALE AMOUNT"].max().where(lambda x: x > 0)
    out["PAYMENT DATE"] = g["PAY DATE"].max()
    out["NEFT ID"] = g["NEFT ID"].last()
    return out


def raw_data(orders: pd.DataFrame, returns: pd.DataFrame, master: pd.DataFrame, settled: pd.DataFrame,
             category_of_design: dict[str, str] | None = None) -> pd.DataFrame:
    o = orders.copy()
    o["oi"] = oi(o["order_item_id"])
    if len(returns):
        r = returns.copy()
        r["oi"] = oi(r["order_item_id"])
        r["_d"] = dt(r["return_approval_date"]).fillna(dt(r.get("return_requested_date", r["return_approval_date"])))
        r = r[r["return_status"].str.lower() != "cancelled"]          # a cancelled return: the item stayed sold
        r = r.sort_values("_d").drop_duplicates("oi", keep="last").set_index("oi")
    else:
        r = pd.DataFrame(columns=["return_type", "return_id", "return_status", "return_result", "return_reason",
                                  "return_sub_reason", "_d"])
    fm = master[master["Channel Name"].str.upper().eq("FLIPKART")].drop_duplicates("Channel Listing SKU Code")
    fm = fm.set_index("Channel Listing SKU Code")
    sku = clean(o["sku"])
    d = pd.DataFrame({"ORDER DATE": dt(o["order_date"]).dt.normalize().values})
    d["ORDER MONTH"] = d["ORDER DATE"].dt.to_period("M").dt.to_timestamp()
    d["ORDER ID"] = o["order_id"].values
    d["ORDER ITEM ID"] = o["oi"].values
    d["SKU"] = sku.values
    d["FSN"] = o["fsn"].values
    d["PRODUCT TITLE"] = clean(o["product_title"]).values
    for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]:
        d[c] = sku.map(fm[c]).values
    d["BRAND"] = sku.map(fm["Brand"]).fillna("Not Mapped").values
    token = d["SKU"].str.split("-").str[1].str.upper().map(CATEGORY_WORDS)
    d["CATEGORY"] = d["DESIGN-NO"].map(category_of_design or {}).fillna(token).fillna("Not Mapped").values
    d["QTY"] = pd.to_numeric(o["quantity"], errors="coerce").fillna(1).values
    d["FULFILMENT TYPE"] = o["fulfilment_type"].values
    d["PORTAL ORDER STATUS"] = o["order_item_status"].values

    key = d["ORDER ITEM ID"]
    rtype = key.map(r["return_type"])
    st = o["order_item_status"].str.upper().values
    known = pd.DataFrame({"reason": o["return_reason"].values, "type": rtype.values}).dropna()
    one_type = known.groupby("reason")["type"].agg(lambda x: x.iloc[0] if x.nunique() == 1 else None).dropna()
    by_reason = pd.Series(o["return_reason"].values).map(one_type)
    pending = np.isin(st, ["RETURNED", "RETURN_REQUESTED"]) & rtype.isna().values
    rtype = rtype.where(~pending, by_reason.values)
    final = np.select([rtype.eq("customer_return").values, rtype.eq("courier_return").values,
                       np.isin(st, ["CANCELLED", "REJECTED"]), st == "DELIVERED",
                       np.isin(st, ["RETURNED", "RETURN_REQUESTED"])],
                      ["Customer Return", "RTO", "Cancelled", "Delivered", "Return Type Pending"], default="In Transit")
    d["FINAL STATUS"] = final
    d["RETURN TYPE SOURCE"] = np.where(key.isin(r.index), "Returns report",
                                       np.where(pending & by_reason.notna().values, "Order return reason", ""))
    ret = np.isin(final, ["Customer Return", "RTO", "Return Type Pending"])
    d["REASON"] = np.where(ret, key.map(r["return_reason"]).fillna(pd.Series(o["return_reason"].values)), "")
    d["SUB REASON"] = np.where(ret, key.map(r["return_sub_reason"]).fillna(pd.Series(o["return_sub_reason"].values)), "")
    d["RETURN ID"] = key.map(r["return_id"]).fillna(pd.Series(o["return_id"].values)).values
    d["RETURN STATUS"] = key.map(r["return_status"]).values
    d["RETURN RESULT"] = key.map(r["return_result"]).values
    d["RETURN DATE"] = pd.to_datetime(key.map(r["_d"])).dt.normalize().values
    d["RETURN MONTH"] = pd.Series(d["RETURN DATE"]).dt.to_period("M").dt.to_timestamp().values
    d["CANCELLED DATE"] = dt(o["order_cancellation_date"]).dt.normalize().values
    d["DISPATCHED DATE"] = dt(o["dispatched_date"]).dt.normalize().values
    d["DELIVERED DATE"] = dt(o["order_delivery_date"]).dt.normalize().values
    d["DISPATCH SLA BREACHED"] = o["dispatch_sla_breached"].values
    d["COURIER"] = o["pickup_logistics_partner"].fillna(o["delivery_logistics_partner"]).values
    s = settlement(settled)
    for c in ["SALE VALUE", "PAYMENT DATE", "NEFT ID"] + [c for c in SETTLE_COLS.values() if c != "SALE AMOUNT"]:
        d[c] = key.map(s[c]).values if len(s) else np.nan
    d["PAYMENT STATUS"] = np.where(pd.notna(d["NET SETTLEMENT"]), "Settled",
                                   np.where(np.isin(final, ["Delivered", "Customer Return"]), "Payment Pending", "Not Applicable"))
    return d.sort_values(["ORDER DATE", "ORDER ITEM ID"]).reset_index(drop=True)


RAW_COLS = ["ORDER DATE", "ORDER MONTH", "ORDER ID", "ORDER ITEM ID", "SKU", "FSN", "PRODUCT TITLE", "MY SKU",
            "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "BRAND", "CATEGORY", "QTY", "SALE VALUE", "FULFILMENT TYPE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "RETURN TYPE SOURCE", "REASON", "SUB REASON", "RETURN ID",
            "RETURN STATUS", "RETURN RESULT", "RETURN DATE", "RETURN MONTH", "CANCELLED DATE", "DISPATCHED DATE",
            "DELIVERED DATE", "DISPATCH SLA BREACHED", "COURIER", "PAYMENT DATE", "NEFT ID", "MARKETPLACE FEE",
            "COMMISSION", "SHIPPING FEE", "REVERSE SHIPPING FEE", "REFUND", "PROTECTION FUND", "TCS", "TDS",
            "NET SETTLEMENT", "PAYMENT STATUS"]
MONEY = {"SALE VALUE", "MARKETPLACE FEE", "COMMISSION", "SHIPPING FEE", "REVERSE SHIPPING FEE", "REFUND",
         "PROTECTION FUND", "TCS", "TDS", "NET SETTLEMENT"}


def report(raw: pd.DataFrame, settled: pd.DataFrame, input_log: pd.DataFrame) -> Report:
    have_pay = raw["NET SETTLEMENT"].notna().any()
    pay_months = None
    if len(settled):
        s = settled.copy()
        s["m"] = pd.to_datetime(s["Payment Date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
        for src, dst in SETTLE_COLS.items():
            s[dst] = pd.to_numeric(s.get(src), errors="coerce").fillna(0)
        pay_months = s.groupby("m")[["SALE AMOUNT", "MARKETPLACE FEE", "REFUND", "TCS", "TDS", "NET SETTLEMENT"]].sum()
        pay_months.columns = ["Sale Amount", "Marketplace Fee", "Refund", "TCS", "TDS", "Bank Settlement"]
    return Report(
        portal="FLIPKART", raw=raw, raw_cols=RAW_COLS,
        value="SALE VALUE" if have_pay else None, settle="NET SETTLEMENT" if have_pay else None, money_cols=MONEY,
        reasons=[("Customer Return Reason", "Customer Return"), ("RTO Reason", "RTO")],
        pay_table=[("Marketplace Fee", "MARKETPLACE FEE"), ("Commission", "COMMISSION"), ("Refund", "REFUND"),
                   ("TCS", "TCS"), ("TDS", "TDS"), ("Net Settlement", "NET SETTLEMENT")],
        pay_months=pay_months, input_log=input_log, min_orders=300)
