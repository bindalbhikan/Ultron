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

  SALES REPORT    the tax "Sales Report" (or "Sales Report Archived" for older months): every sale,
                  return and cancellation event with its invoice value. Months before Feb 2026, whose
                  Orders report Flipkart no longer gives, come from it (SOURCE = Sales report: status
                  from the events, the return type from the Returns report when it has the item)

SALE VALUE = Price before discount of the sale in the tax Sales Report (owner's rule, 4 Nov 2026), else the
item's Sale Amount in Settled Transactions; NET SETTLEMENT = the sum of its Bank Settlement Values.
  MONTHLY REPORT  the owner's monthly file (sheet "Order Wise", Oct-25 to Apr-26): one row per order item
                  settled in that month, its Bank Settlement Value the same as Settled Transactions (checked
                  May-26 to Sep-26, item by item). It is the payment of months with no Settled Transactions
                  file, and the source of items no other report has (Nov-25, Dec-25: SOURCE = Monthly file).
                  Net Qty > 0 = delivered, else returned (checked against the Orders report, Mar-26 to
                  Aug-26). An item with no settlement (cancelled, most RTO) is not in it.

BRAND / design from MasterSheet (channel FLIPKART); CATEGORY = the article type Myntra lists the
same design under (else the SKU's category word).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .workbook import Report, any_date

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


def read_sales(files: list[Path]) -> pd.DataFrame:
    """The "Sales Report" sheet of tax Sales Report files (one row per sale / return / cancel event)."""
    frames = []
    for f in files:
        df = pd.read_excel(f, sheet_name="Sales Report", dtype=str)
        if len(df):
            frames.append(df.assign(_file=f.name))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_monthly(files: list[tuple[Path, pd.Timestamp]]) -> pd.DataFrame:
    """The "Order Wise" sheet of the owner's monthly files; one row per order item settled that month."""
    frames = []
    for f, month in files:
        df = pd.read_excel(f, sheet_name="Order Wise", dtype=str)
        df.columns = [re.sub(r"\s+", " ", str(c)).strip().lower() for c in df.columns]
        df = df.rename(columns={"bank settlement value": "payout", "order item id": "oi"})
        df = df[df["oi"].astype(str).str.match(r"^(OI:)?\d+")].copy()     # order lines only, no totals or non-order rows
        df["oi"] = oi(df["oi"])
        day = any_date(df["order date"])
        df["order_date"] = day.where(day < month + pd.offsets.MonthBegin(1)).dt.strftime("%Y-%m-%d")   # a mistyped later date: no date
        frames.append(df.assign(_file=f.name, _month=month))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _rupees(text) -> float:
    """A transfer as the owner's monthly files list it: Rs 1.25 L, Rs 99.95 K."""
    m = re.search(r"([\d,.]+)\s*(K|L|Cr)?", str(text).replace("\u20b9", ""))
    return float(m[1].replace(",", "")) * {"K": 1e3, "L": 1e5, "Cr": 1e7, None: 1}[m[2]] if m else 0.0


def bank_paid(settled_files: list[tuple[Path, pd.Timestamp]], monthly_files: list[tuple[Path, pd.Timestamp]]) -> pd.DataFrame:
    """Per payment month what reached the bank: Settled Transactions' Net Bank Settlement, else the total row of the owner's
    monthly file (order money + non-order SPF + ads + storage), with the transfers that file lists (rounded by Flipkart)."""
    rows = {}
    for f, month in settled_files:
        s = pd.read_excel(f, sheet_name="Summary of report", header=None, dtype=str).dropna(how="all").dropna(axis=1, how="all")
        first = s.columns[0]
        head = s.index[s[first].astype(str).str.strip() == "Line Item"][0]
        amount = s.columns[list(s.loc[head]).index("Amount Settled (Rs.)")]
        line = s.loc[head + 1:]
        net = line[line[first].astype(str).str.startswith("Net Bank Settlement")]
        if len(net):
            rows[month] = {"Net Bank Paid": float(net[amount].iloc[0]), "Transfers Listed": np.nan}
    for f, month in monthly_files:
        if month in rows:
            continue
        d = pd.read_excel(f, sheet_name="Order Wise", dtype=str)
        d.columns = [re.sub(r"\s+", " ", str(c)).strip().lower() for c in d.columns]
        d = d.rename(columns={"bank settlement value": "payout"})
        kind = d["type"].astype(str).str.strip().str.lower()
        total = pd.to_numeric(d.loc[kind.isin(["total", "grand total", "net total"]), "payout"], errors="coerce").dropna()
        if not len(total):
            continue
        listed = np.nan
        start = d.index[kind == "payment"]
        if len(start):
            amounts = d.loc[start[0] + 2:, "order item id"].dropna().astype(str)
            listed = sum(_rupees(x) for x in amounts if "\u20b9" in x or re.match(r"^[\d,.]+\s*(K|L)?$", x.strip())) or np.nan
        rows[month] = {"Net Bank Paid": float(total.iloc[-1]), "Transfers Listed": listed}
    return pd.DataFrame.from_dict(rows, orient="index").sort_index() if rows else pd.DataFrame()


def monthly_items(monthly: pd.DataFrame) -> pd.DataFrame:
    """Per order item, in the shape of the Orders report: delivered when its Net Qty over all months is above 0."""
    m = monthly.copy()
    m["net"] = pd.to_numeric(m["net qty"], errors="coerce").fillna(0)
    m["sold"] = pd.to_numeric(m["sale qty"], errors="coerce").fillna(0)
    m = m.sort_values("_month")
    g = m.groupby("oi")
    out = pd.DataFrame({"order_id": g["order id"].first(), "order_date": g["order_date"].first(), "sku": g["sku"].first(),
                        "quantity": g["sold"].max().clip(lower=1), "net": g["net"].sum()}).reset_index(names="order_item_id")
    out["order_item_status"] = np.where(out.pop("net") > 0, "DELIVERED", "RETURNED")
    out["_file"] = "Monthly file"
    for c in ["fsn", "product_title", "fulfilment_type", "return_reason", "return_sub_reason", "return_id", "order_cancellation_date",
              "dispatched_date", "order_delivery_date", "dispatch_sla_breached", "pickup_logistics_partner", "delivery_logistics_partner"]:
        out[c] = None
    return out


def monthly_settled(monthly: pd.DataFrame, have: set) -> pd.DataFrame:
    """Rows in the shape of Settled Transactions, for the months in no Settled Transactions file (have).
    The file gives no payment date or NEFT id: the month is known, the id names the file."""
    m = monthly[~monthly["_month"].isin(have)] if len(monthly) else monthly
    if not len(m):
        return pd.DataFrame()
    out = pd.DataFrame({"Order item ID": m["oi"].values, "NEFT ID": m["_month"].dt.strftime("Monthly file %b-%y").values,
                        "Payment Date": None, "_month": m["_month"].values, "_file": m["_file"].values})
    for src, name in (("Sale Amount (Rs.)", "sale amount"), ("Bank Settlement Value (Rs.)", "payout"), ("Marketplace Fee (Rs.)", "marketplace fee"),
                      ("Commission (Rs.)", "commission"), ("Shipping Fee (Rs.)", "shipping fee"), ("Reverse Shipping Fee (Rs.)", "reverse shipping fee"),
                      ("Refund (Rs.)", "refund"), ("TCS (Rs.)", "tcs"), ("TDS (Rs.)", "tds")):
        out[src] = m[name].values if name in m.columns else None
    return out


def sales_items(sales: pd.DataFrame) -> pd.DataFrame:
    """Per order item from every month's tax Sales Report events merged (a month's file also holds
    earlier months' orders), by the order's own date: SKU, qty, Price before discount of the sale, and its
    status. Cancelled = as many Cancellation rows as Sale rows: an item with a Sale, a Cancellation and
    a second Sale was only invoiced again and stayed sold (3,422 of 9,331 such items were later returned).
    More Returns than Return Cancellations = returned; else delivered. Rows in the shape of the Orders
    report, for the months whose Orders report Flipkart no longer gives (before Feb 2026)."""
    if not len(sales):
        return pd.DataFrame()
    s = sales.copy()
    s["oi"] = oi(s["Order Item ID"])
    s["sub"] = s["Event Sub Type"].astype(str).str.strip()
    s["val"] = pd.to_numeric(s["Price before discount"], errors="coerce")
    s = s.drop_duplicates(["oi", "sub", "Event Type", "val", "Order Date", "Buyer Invoice ID"])
    sale = s[s["sub"] == "Sale"].sort_values("Order Date").drop_duplicates("oi", keep="first").set_index("oi")
    n = s.groupby(["oi", "sub"]).size().unstack(fill_value=0)
    for c in ["Sale", "Cancellation", "Return", "Return Cancellation"]:
        if c not in n.columns:
            n[c] = 0
    status = np.where((n["Cancellation"] > 0) & (n["Cancellation"] >= n["Sale"]), "CANCELLED",
                      np.where(n["Return"] > n["Return Cancellation"], "RETURNED", "DELIVERED"))
    st = pd.Series(status, index=n.index)
    items = sale.index
    out = pd.DataFrame({
        "order_item_id": items, "order_id": sale["Order ID"].values, "order_date": sale["Order Date"].values,
        "sku": sale["SKU"].values, "fsn": sale["FSN"].values, "product_title": sale["Product Title/Description"].values,
        "quantity": sale["Item Quantity"].values, "fulfilment_type": sale["Fulfilment Type"].values,
        "order_item_status": st.reindex(items).values, "_value": s[s["sub"] == "Sale"].groupby("oi")["val"].max().reindex(items).values,
        "_file": "Sales Report"})
    for c in ["return_reason", "return_sub_reason", "return_id", "order_cancellation_date", "dispatched_date",
              "order_delivery_date", "dispatch_sla_breached", "pickup_logistics_partner", "delivery_logistics_partner"]:
        out[c] = None
    return out


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
             category_of_design: dict[str, str] | None = None, sales: pd.DataFrame | None = None,
             monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    o = orders.copy()
    o["oi"] = oi(o["order_item_id"])
    o["_source"] = "Orders report"
    tax = sales_items(sales if sales is not None else pd.DataFrame())
    tax_value = pd.Series(dtype=float)
    if len(tax):
        tax_value = tax.set_index("order_item_id")["_value"]
        extra = tax[~tax["order_item_id"].isin(o["oi"])].copy()      # items the Orders reports do not have
        extra["oi"] = extra["order_item_id"]
        extra["_source"] = "Sales report"
        o = pd.concat([o, extra.drop(columns=["_value"])], ignore_index=True)
    if monthly is not None and len(monthly):                         # items only the owner's monthly files have
        items = monthly_items(monthly)
        extra = items[~items["order_item_id"].isin(o["oi"])].copy()
        extra["oi"] = extra["order_item_id"]
        extra["_source"] = "Monthly file"
        o = pd.concat([o, extra], ignore_index=True)
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
    # sale value: the tax Sales Report's Price before discount, else Settled Transactions' Sale Amount
    if len(tax_value):
        d["SALE VALUE"] = key.map(tax_value).fillna(pd.Series(d["SALE VALUE"])).values
    d["SOURCE"] = o["_source"].values
    d["PAYMENT STATUS"] = np.where(pd.notna(d["NET SETTLEMENT"]), "Settled",
                                   np.where(np.isin(final, ["Delivered", "Customer Return"]), "Payment Pending", "Not Applicable"))
    return d.sort_values(["ORDER DATE", "ORDER ITEM ID"]).reset_index(drop=True)


def returned_units(raw: pd.DataFrame, returns: pd.DataFrame, sales: pd.DataFrame) -> pd.Series:
    """Units returned per row of raw: the larger of the Sales Report's Return less Return Cancellation quantity and the
    Returns report's quantity (a line's returns are not always in both); a line can return no more than it holds."""
    found = []
    if len(sales):
        s = sales.copy()
        s["oi"] = oi(s["Order Item ID"])
        s["sub"] = s["Event Sub Type"].astype(str).str.strip()
        s["q"] = pd.to_numeric(s["Item Quantity"], errors="coerce").fillna(0)
        s = s[s["sub"].isin(["Return", "Return Cancellation"])].drop_duplicates(["oi", "sub", "Order Date", "Buyer Invoice ID", "q"])
        found.append((s["q"] * s["sub"].map({"Return": 1, "Return Cancellation": -1})).groupby(s["oi"]).sum().clip(lower=0))
    if len(returns):
        r = returns[returns["return_status"].str.lower() != "cancelled"].copy()
        r["oi"] = oi(r["order_item_id"])
        r = r.drop_duplicates(["oi", "return_id"])
        found.append(pd.to_numeric(r["quantity"], errors="coerce").fillna(1).groupby(r["oi"]).sum())
    if not found:
        return pd.Series(0.0, index=raw.index)
    units = pd.concat(found, axis=1).max(axis=1)
    return raw["ORDER ITEM ID"].map(units).fillna(0).clip(upper=raw["QTY"])


RETURN_COLS = ["REASON", "SUB REASON", "RETURN ID", "RETURN STATUS", "RETURN RESULT", "RETURN DATE", "RETURN MONTH", "RETURN TYPE SOURCE"]
RAW_COLS = ["ORDER DATE", "ORDER MONTH", "ORDER ID", "ORDER ITEM ID", "SOURCE", "OMS STATUS", "SKU", "FSN", "PRODUCT TITLE", "MY SKU",
            "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "BRAND", "CATEGORY", "QTY", "SALE VALUE", "FULFILMENT TYPE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "RETURN TYPE SOURCE", "REASON", "SUB REASON", "RETURN ID",
            "RETURN STATUS", "RETURN RESULT", "RETURN DATE", "RETURN MONTH", "CANCELLED DATE", "DISPATCHED DATE",
            "DELIVERED DATE", "DISPATCH SLA BREACHED", "COURIER", "PAYMENT DATE", "NEFT ID", "MARKETPLACE FEE",
            "COMMISSION", "SHIPPING FEE", "REVERSE SHIPPING FEE", "REFUND", "PROTECTION FUND", "TCS", "TDS",
            "NET SETTLEMENT", "PAYMENT STATUS"]
MONEY = {"SALE VALUE", "MARKETPLACE FEE", "COMMISSION", "SHIPPING FEE", "REVERSE SHIPPING FEE", "REFUND",
         "PROTECTION FUND", "TCS", "TDS", "NET SETTLEMENT"}


def report(raw: pd.DataFrame, settled: pd.DataFrame, input_log: pd.DataFrame, bank: pd.DataFrame | None = None) -> Report:
    have_pay = raw["NET SETTLEMENT"].notna().any()
    have_value = raw["SALE VALUE"].notna().any()
    pay_months = None
    if len(settled):
        s = settled.copy()
        s["m"] = pd.to_datetime(s["Payment Date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
        if "_month" in s.columns:                                    # a monthly file: its month
            s["m"] = s["m"].fillna(s["_month"])
        for src, dst in SETTLE_COLS.items():
            s[dst] = pd.to_numeric(s.get(src), errors="coerce").fillna(0)
        pay_months = s.groupby("m")[["SALE AMOUNT", "MARKETPLACE FEE", "REFUND", "TCS", "TDS", "NET SETTLEMENT"]].sum()
        pay_months.columns = ["Sale Amount", "Marketplace Fee", "Refund", "TCS", "TDS", "Order Settlement"]
        if bank is not None and len(bank):
            pay_months = pay_months.join(bank)
            pay_months.insert(6, "SPF, Ads, Storage", pay_months["Net Bank Paid"] - pay_months["Order Settlement"])
            pay_months["Difference"] = (pay_months["Net Bank Paid"] - pay_months["Transfers Listed"]).round(0)
    return Report(
        portal="FLIPKART", raw=raw, raw_cols=RAW_COLS,
        value="SALE VALUE" if have_value else None, settle="NET SETTLEMENT" if have_pay else None, money_cols=MONEY,
        reasons=[("Customer Return Reason", "Customer Return"), ("RTO Reason", "RTO")],
        pay_table=[("Marketplace Fee", "MARKETPLACE FEE"), ("Commission", "COMMISSION"), ("Refund", "REFUND"),
                   ("TCS", "TCS"), ("TDS", "TDS"), ("Net Settlement", "NET SETTLEMENT")],
        pay_months=pay_months, input_log=input_log, min_orders=300, recv_all=True)
