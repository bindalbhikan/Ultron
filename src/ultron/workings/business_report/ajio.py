"""AJIO sale / return analysis (business reporting): the Myntra layout (workbook.py) from the AJIO
reports kept in PORTAL REPORTS.

  ORDER REPORT    Dropship order report: one row per order line (Cust Order No + Seller SKU), status,
                  Selling Price (what the customer paid), Invoice Value (what AJIO pays us)
  RETURN REPORT   Dropship RTV report: one row per return line; Return Type RVP / REPL / SELF_SHIP =
                  customer return (REPL = exchange, counted as a return as on Myntra), RTO = RTO
  PAYMENT REPORT  SRM statement of accounts (the AJIO ledger; owner's rule, 2 Nov 2026): G4 = payment
                  received for an invoice (REFERENCE = the Seller Invoice No), IC = a payment reversed for a
                  return (INVOICE REFERENCE NUMBER = the DOCNO of that invoice's G4), the rest (bank
                  clearing, TOT, ads, holds) are neither received nor reversed money of an order line

FINAL STATUS: Customer Return / RTO from the RTV line (return qty > 0), Cancelled (status Cancelled),
Delivered (status Delivered, no return), In Transit (Shipped and the rest).
SALE VALUE = Selling Price x qty; NET SETTLEMENT = G4 received less IC reversed (sign turned so money
to us is positive), both matched by invoice number. An invoice can hold several order lines: G4 is shared
by invoice value, IC by the credit note value of the invoice's returned lines, so no rupee counts twice.
BRAND from the order report; CATEGORY = the article type Myntra lists the same design under (MasterSheet
channel AJIO for the design), else the order's Description.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .workbook import Report

log = logging.getLogger("bindal.business_report")
AJIO_FMT = "%a %b %d %H:%M:%S %Y"
CUSTOMER = {"RVP", "REPL", "SELF_SHIP"}


def adate(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.replace(" IST", "", regex=False), format=AJIO_FMT, errors="coerce")


def num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def read(files: list[Path]) -> pd.DataFrame:
    frames = [pd.read_excel(f, dtype=str).assign(_file=f.name) for f in files]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def ledger_lines(ledger: pd.DataFrame) -> pd.DataFrame:
    """The ledger's lines once each; amt: money to us is positive; paid: the clearing date."""
    lg = ledger.copy()
    lg["amt"] = -num(lg["AMOUNT"]).fillna(0)
    lg["paid"] = pd.to_datetime(lg["CLEARINGDOCUMENTDATE"], format="%d.%m.%Y", errors="coerce")
    return lg.drop_duplicates(["DT", "REFERENCE", "DOCNO", "AMOUNT"])


def credit_notes(rtv: pd.DataFrame) -> pd.Series:
    """Order line key -> credit note value of its return lines (which line of an invoice an IC is for)."""
    if not len(rtv):
        return pd.Series(dtype=float)
    lines = rtv.drop_duplicates(["RETURN ORDER NUMBER", "SELLER SKU"], keep="last")
    keys = lines["Cust Order No"].str.strip() + "|" + lines["SELLER SKU"].str.strip()
    return num(lines["Credit Note Value"]).fillna(0).clip(lower=0).groupby(keys).sum()


def raw_data(orders: pd.DataFrame, rtv: pd.DataFrame, ledger: pd.DataFrame, master: pd.DataFrame,
             category_of_design: dict[str, str] | None = None) -> pd.DataFrame:
    o = orders.copy()
    o["key"] = o["Cust Order No"].str.strip() + "|" + o["Seller SKU"].str.strip()
    o = o.drop_duplicates("key", keep="last")
    all_returns = rtv
    if len(rtv):
        r = rtv.copy()
        r["key"] = r["Cust Order No"].str.strip() + "|" + r["SELLER SKU"].str.strip()
        r["qty"] = num(r["Return QTY"]).fillna(0)
        r["created"] = adate(r["Return Created Date"])
        r["is_rto"] = r["Return Type"].eq("RTO")
        # one return per order line: an RTO first, then one with qty, then the latest
        r = r.sort_values(["key", "is_rto", "qty", "created"], ascending=[True, False, False, False]).drop_duplicates("key")
        r = r.set_index("key")
    else:
        r = pd.DataFrame(columns=["Return Type", "qty", "created", "Cust Return Reason", "RETURN ORDER NUMBER",
                                  "Return Status", "Credit Note Number", "Return Value"])
    am = master[master["Channel Name"].str.upper().str.startswith("AJIO", na=False)].drop_duplicates("Channel Listing SKU Code")
    am = am.set_index("Channel Listing SKU Code")
    sku = o["Seller SKU"].str.strip()
    d = pd.DataFrame({"ORDER DATE": adate(o["Cust Order Date"]).dt.normalize().values})
    d["ORDER MONTH"] = d["ORDER DATE"].dt.to_period("M").dt.to_timestamp()
    d["CUST ORDER NO"] = o["Cust Order No"].values
    d["SELLER ORDER NO"] = o["FWD Seller Order NO"].values
    d["SELLER INVOICE NO"] = o["Seller Invoice No"].values
    d["JIOCODE"] = o["JioCode"].values
    d["SELLER STYLE CODE"] = o["Seller Style Code"].values
    d["SELLER SKU"] = sku.values
    for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]:
        d[c] = sku.map(am[c]).values
    d["BRAND"] = o["Brand"].fillna(sku.map(am["Brand"])).fillna("Not Mapped").values
    d["CATEGORY"] = d["DESIGN-NO"].map(category_of_design or {}).fillna(o["Description"].str.title()).fillna("Not Mapped").values
    d["DESCRIPTION"] = o["Description"].values
    d["QTY"] = num(o["Order Qty"]).fillna(1).values
    d["MRP"] = num(o["Listing MRP"]).values
    d["SELLING PRICE"] = num(o["Selling Price"]).values
    d["SALE VALUE"] = (d["SELLING PRICE"] * d["QTY"]).values
    d["INVOICE VALUE"] = num(o["Invoice Value"]).values
    d["FULFILLMENT TYPE"] = o["Fulfillment Type"].values
    d["PORTAL ORDER STATUS"] = o["Status"].values
    key = pd.Series(o["key"].values)
    rtype, rqty = key.map(r["Return Type"]), key.map(r["qty"]).fillna(0)
    st = o["Status"].str.strip().str.lower().values
    final = np.select([rtype.eq("RTO").values, (rtype.isin(CUSTOMER) & (rqty > 0)).values,
                       st == "cancelled", st == "delivered"],
                      ["RTO", "Customer Return", "Cancelled", "Delivered"], default="In Transit")
    d["FINAL STATUS"] = final
    d["RETURN TYPE"] = rtype.values
    d["REASON"] = np.where(np.isin(final, ["Customer Return", "RTO"]), key.map(r["Cust Return Reason"]).fillna(""), "")
    d["RETURN ORDER NUMBER"] = key.map(r["RETURN ORDER NUMBER"]).values
    d["RETURN STATUS"] = key.map(r["Return Status"]).values
    d["RETURN CREATED DATE"] = pd.to_datetime(key.map(r["created"])).dt.normalize().values
    d["RETURN MONTH"] = pd.Series(d["RETURN CREATED DATE"]).dt.to_period("M").dt.to_timestamp().values
    d["CREDIT NOTE NUMBER"] = key.map(r["Credit Note Number"]).values
    d["COURIER"] = o["FWD Carrier"].values
    d["SHIPMENT DATE"] = adate(o["FWD Shipment Date"]).dt.normalize().values
    d["SLA STATUS"] = o["SLA Status"].values
    # payments by invoice number: G4 received (REFERENCE), IC reversed (through the DOCNO of the G4)
    if len(ledger):
        lg = ledger_lines(ledger)
        for c in ("REFERENCE", "DOCNO", "INVOICE REFERENCE NUMBER"):
            lg[c] = lg[c].astype(str).str.strip()
        received, ic = lg[lg["DT"] == "G4"], lg[lg["DT"] == "IC"]
        g4 = received.groupby("REFERENCE").agg(amt=("amt", "sum"), paid=("paid", "max"))
        invoice_of = received.drop_duplicates("DOCNO").set_index("DOCNO")["REFERENCE"]
        reversed_ = ic.groupby(ic["INVOICE REFERENCE NUMBER"].map(invoice_of))["amt"].sum()
        inv = pd.Series(d["SELLER INVOICE NO"]).astype(str).str.strip()
        value = pd.Series(d["INVOICE VALUE"]).fillna(0).clip(lower=0)
        total = value.groupby(inv).transform("sum")
        share = (value / total).where(total > 0, 1 / inv.map(inv.value_counts()))
        d["INVOICE PAID"] = (inv.map(g4["amt"]) * share).values
        d["PAYMENT DATE"] = inv.map(g4["paid"]).values
        note = key.map(credit_notes(all_returns)).fillna(0)
        noted = note.groupby(inv).transform("sum")
        debit = inv.map(reversed_) * (note / noted).where(noted > 0, share)     # no credit note: as G4
        d["CREDIT NOTE DEBIT"] = debit.where(debit != 0).values
        d["NET SETTLEMENT"] = (pd.Series(d["INVOICE PAID"]).fillna(0) + pd.Series(d["CREDIT NOTE DEBIT"]).fillna(0)) \
            .where(pd.Series(d["INVOICE PAID"]).notna() | pd.Series(d["CREDIT NOTE DEBIT"]).notna()).values
    else:
        for c in ["INVOICE PAID", "PAYMENT DATE", "CREDIT NOTE DEBIT", "NET SETTLEMENT"]:
            d[c] = np.nan
    d["PAYMENT STATUS"] = np.where(pd.notna(d["INVOICE PAID"]), "Settled",
                                   np.where(np.isin(final, ["Delivered", "Customer Return"]), "Payment Pending", "Not Applicable"))
    return d.sort_values(["ORDER DATE", "CUST ORDER NO"]).reset_index(drop=True)


RAW_COLS = ["ORDER DATE", "ORDER MONTH", "CUST ORDER NO", "SELLER ORDER NO", "SELLER INVOICE NO", "JIOCODE",
            "SELLER STYLE CODE", "SELLER SKU", "MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "BRAND", "CATEGORY",
            "DESCRIPTION", "QTY", "MRP", "SELLING PRICE", "SALE VALUE", "INVOICE VALUE", "FULFILLMENT TYPE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "RETURN TYPE", "REASON", "RETURN ORDER NUMBER", "RETURN STATUS",
            "RETURN CREATED DATE", "RETURN MONTH", "CREDIT NOTE NUMBER", "COURIER", "SHIPMENT DATE", "SLA STATUS",
            "INVOICE PAID", "PAYMENT DATE", "CREDIT NOTE DEBIT", "NET SETTLEMENT", "PAYMENT STATUS"]
MONEY = {"MRP", "SELLING PRICE", "SALE VALUE", "INVOICE VALUE", "INVOICE PAID", "CREDIT NOTE DEBIT", "NET SETTLEMENT"}


def report(raw: pd.DataFrame, ledger: pd.DataFrame, input_log: pd.DataFrame) -> Report:
    have_pay = raw["NET SETTLEMENT"].notna().any()
    pay_months = None
    if len(ledger):
        lg = ledger_lines(ledger)
        lg["m"] = lg["paid"].dt.to_period("M").dt.to_timestamp()
        lg = lg.dropna(subset=["m"])
        t = lg.pivot_table(index="m", columns="DT", values="amt", aggfunc="sum", fill_value=0)
        t = t.reindex(columns=["G4", "IC"] + sorted(c for c in t.columns if c not in ("G4", "IC")), fill_value=0)
        t.columns = ["Received (G4)", "Reversed (IC)"] + [f"Other ({c})" for c in t.columns[2:]]
        t["Net Payout"] = t["Received (G4)"] + t["Reversed (IC)"]      # the others are not order money
        pay_months = t
    return Report(
        portal="AJIO", raw=raw, raw_cols=RAW_COLS, value="SALE VALUE",
        settle="NET SETTLEMENT" if have_pay else None, money_cols=MONEY,
        reasons=[("Customer Return Reason", "Customer Return"), ("RTO Reason", "RTO")],
        pay_table=[("Invoice Value", "INVOICE VALUE"), ("Invoices Paid", "INVOICE PAID"),
                   ("Credit Notes", "CREDIT NOTE DEBIT"), ("Net Settlement", "NET SETTLEMENT")],
        pay_months=pay_months, input_log=input_log, min_orders=200)
