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
  (Return Type Pending: dropped 16 Nov 2026 - returns only from the Returns report, in the window) The old rule was:
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

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .workbook import Report, any_date

if TYPE_CHECKING:
    import polars as pl

log = logging.getLogger("bindal.business_report")

CATEGORY_WORDS = {"COORD": "Co-Ords", "DRESS": "Dresses", "TOP": "Tops", "JUMPSUIT": "Jumpsuit", "SHIRT": "Shirts"}


from ..core.tables import pnum as _num  # noqa: E402 - one number reader (docs/CENTRALISE.md)

def clean(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace('"', "", regex=False).str.replace("SKU:", "", regex=False).str.strip()


def dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str[:19], errors="coerce", format="mixed")


def oi(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace("OI:", "", regex=False).str.strip()


# ------------------------------------------------------------------ inputs
def _xlsx(path: Path, sheet: str, header: int | None = 0) -> pd.DataFrame:
    """A Seller Hub sheet as text, read by Polars' calamine reader (core/tables.read_excel_text: the same cells as
    pandas' read_excel(dtype=str) on every Flipkart sheet, 16 Nov 2026), handed on as a pandas table."""
    from ..core.tables import read_excel_text, to_pandas
    return to_pandas(read_excel_text(path, sheet, header=header))


def read_orders(files: list[Path]) -> pd.DataFrame:
    frames = [_xlsx(f, "Orders").assign(_file=f.name) for f in files]
    o = pd.concat([f for f in frames if len(f)], ignore_index=True) if frames else pd.DataFrame()
    return o.drop_duplicates("order_item_id", keep="last") if len(o) else o


def read_returns(files: list[Path]) -> pd.DataFrame:
    frames = [_xlsx(f, "Returns").assign(_file=f.name) for f in files]
    return pd.concat([f for f in frames if len(f)], ignore_index=True) if frames else pd.DataFrame()


def _col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).split("\n")[0]).strip()


def read_settled(files: list[Path]) -> pd.DataFrame:
    """The "Orders" sheet of Settled Transactions files (header on the 2nd row, a sub-header row below)."""
    frames = []
    for f in files:
        df = _xlsx(f, "Orders", header=1)
        df.columns = [_col(c) for c in df.columns]
        df = df[df["Order item ID"].notna() & df["NEFT ID"].notna()]
        if len(df):
            frames.append(df.assign(_file=f.name))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_sales(files: list[Path]) -> pd.DataFrame:
    """The "Sales Report" sheet of tax Sales Report files (one row per sale / return / cancel event)."""
    frames = []
    for f in files:
        df = _xlsx(f, "Sales Report")
        if len(df):
            frames.append(df.assign(_file=f.name))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_monthly(files: list[tuple[Path, pd.Timestamp]]) -> pd.DataFrame:
    """The "Order Wise" sheet of the owner's monthly files; one row per order item settled that month."""
    frames = []
    for f, month in files:
        df = _xlsx(f, "Order Wise")
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
        s = _xlsx(f, "Summary of report", header=None).dropna(how="all").dropna(axis=1, how="all")
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
        d = _xlsx(f, "Order Wise")
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


SETTLE_COLS = {"Sale Amount (Rs.)": "SALE AMOUNT", "Bank Settlement Value (Rs.)": "NET SETTLEMENT",
               "Marketplace Fee (Rs.)": "MARKETPLACE FEE", "Commission (Rs.)": "COMMISSION",
               "Shipping Fee (Rs.)": "SHIPPING FEE", "Reverse Shipping Fee (Rs.)": "REVERSE SHIPPING FEE",
               "Refund (Rs.)": "REFUND", "Protection Fund (Rs.)": "PROTECTION FUND", "TCS (Rs.)": "TCS", "TDS (Rs.)": "TDS"}


# ------------------------------------------------------------------ Polars (docs/libraries/06-polars.md)
def _pl():
    import polars as pl
    return pl


def poi(e: "pl.Expr") -> "pl.Expr":
    """An order item id as text, no "OI:" (oi() in Polars)."""
    pl = _pl()
    return e.cast(pl.Utf8).str.replace_all("OI:", "", literal=True).str.strip_chars()


def pclean(e: "pl.Expr") -> "pl.Expr":
    """clean() in Polars: no quotes, no "SKU:", outer spaces out."""
    pl = _pl()
    return e.cast(pl.Utf8).str.replace_all('"', "", literal=True).str.replace_all("SKU:", "", literal=True).str.strip_chars()


def pdt(e: "pl.Expr") -> "pl.Expr":
    """dt() in Polars: the first 19 characters of an ISO date / date-time (every Flipkart report date: YYYY-MM-DD,
    YYYY-MM-DD HH:MM:SS, with or without fractions); anything else -> null."""
    pl = _pl()
    s = e.cast(pl.Utf8).str.slice(0, 19)
    return pl.coalesce(s.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False),
                       s.str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False),
                       s.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us")))


def _frame(df) -> "pl.DataFrame":
    from ..core.tables import to_polars
    pl = _pl()
    return pl.DataFrame() if df is None else to_polars(df)


def _get(df: "pl.DataFrame", name: str) -> "pl.Expr":
    """The column, or nulls when the file had none."""
    pl = _pl()
    return pl.col(name) if name in df.columns else pl.lit(None, dtype=pl.Utf8)


NO_ORDER_FIELDS = ["fsn", "product_title", "fulfilment_type", "return_reason", "return_sub_reason", "return_id",
                   "order_cancellation_date", "dispatched_date", "order_delivery_date", "dispatch_sla_breached",
                   "pickup_logistics_partner", "delivery_logistics_partner"]


def monthly_items(monthly) -> "pl.DataFrame":
    """Per order item, in the shape of the Orders report: delivered when its Net Qty over all months is above 0."""
    pl = _pl()
    m = _frame(monthly)
    if not m.height:
        return pl.DataFrame()
    first = lambda c: pl.col(c).drop_nulls().first()  # noqa: E731 - pandas' groupby first: the first non-empty
    out = (m.with_columns(_net=_num(pl.col("net qty")).fill_null(0), _sold=_num(pl.col("sale qty")).fill_null(0))
            .sort("_month", maintain_order=True, nulls_last=True)
            .group_by("oi", maintain_order=True)
            .agg(order_id=first("order id"), order_date=first("order_date"), sku=first("sku"),
                 quantity=pl.col("_sold").max().clip(lower_bound=1), _n=pl.col("_net").sum()))
    return out.select(pl.col("oi").alias("order_item_id"), "order_id", "order_date", "sku", "quantity",
                      pl.when(pl.col("_n") > 0).then(pl.lit("DELIVERED")).otherwise(pl.lit("RETURNED")).alias("order_item_status"),
                      pl.lit("Monthly file").alias("_file"),
                      *[pl.lit(None, dtype=pl.Utf8).alias(c) for c in NO_ORDER_FIELDS])


def sales_items(sales) -> "pl.DataFrame":
    """Per order item from every month's tax Sales Report events merged (a month's file also holds
    earlier months' orders), by the order's own date: SKU, qty, Price before discount of the sale, and its
    status. Cancelled = as many Cancellation rows as Sale rows: an item with a Sale, a Cancellation and
    a second Sale was only invoiced again and stayed sold (3,422 of 9,331 such items were later returned).
    More Returns than Return Cancellations = returned; else delivered. Rows in the shape of the Orders
    report, for the months whose Orders report Flipkart no longer gives (before Feb 2026)."""
    pl = _pl()
    s = _frame(sales)
    if not s.height:
        return pl.DataFrame()
    s = (s.with_columns(_oi=poi(pl.col("Order Item ID")), _sub=pl.col("Event Sub Type").str.strip_chars(),
                        _val=_num(pl.col("Price before discount")))
          .unique(["_oi", "_sub", "Event Type", "_val", "Order Date", "Buyer Invoice ID"], keep="first", maintain_order=True))
    sale = s.filter(pl.col("_sub") == "Sale")
    first = (sale.sort("Order Date", maintain_order=True, nulls_last=True)
                 .unique("_oi", keep="first", maintain_order=True))
    n = lambda kind: (pl.col("_sub") == kind).sum()  # noqa: E731
    counts = s.group_by("_oi").agg(_sale=n("Sale"), _canc=n("Cancellation"), _ret=n("Return"), _retc=n("Return Cancellation"))
    value = sale.group_by("_oi").agg(_value=pl.col("_val").max())
    out = (first.join(counts, on="_oi", how="left", maintain_order="left")
                .join(value, on="_oi", how="left", maintain_order="left"))
    status = (pl.when((pl.col("_canc") > 0) & (pl.col("_canc") >= pl.col("_sale"))).then(pl.lit("CANCELLED"))
                .when(pl.col("_ret") > pl.col("_retc")).then(pl.lit("RETURNED")).otherwise(pl.lit("DELIVERED")))
    return out.select(pl.col("_oi").alias("order_item_id"), pl.col("Order ID").alias("order_id"),
                      pl.col("Order Date").alias("order_date"), pl.col("SKU").alias("sku"), pl.col("FSN").alias("fsn"),
                      pl.col("Product Title/Description").alias("product_title"),
                      pl.col("Item Quantity").alias("quantity"), pl.col("Fulfilment Type").alias("fulfilment_type"),
                      status.alias("order_item_status"), "_value", pl.lit("Sales Report").alias("_file"),
                      *[pl.lit(None, dtype=pl.Utf8).alias(c) for c in NO_ORDER_FIELDS
                        if c not in ("fsn", "product_title", "fulfilment_type")])


def settlement(st) -> "pl.DataFrame":
    """Per order item (`oi`): SALE VALUE (its largest Sale Amount), the sums of the money columns, the last
    payment date and NEFT id."""
    pl = _pl()
    s = _frame(st)
    if not s.height:
        return pl.DataFrame()
    s = (s.with_columns(oi=poi(pl.col("Order item ID")),
                        **{dst: _num(_get(s, src)).fill_null(0) for src, dst in SETTLE_COLS.items()},
                        _pay=pdt(pl.col("Payment Date")))
          .unique(["NEFT ID", "oi", "NET SETTLEMENT", "SALE AMOUNT", "_pay"], keep="first", maintain_order=True))
    return s.group_by("oi", maintain_order=True).agg(
        *[pl.col(c).sum() for c in SETTLE_COLS.values()],
        pl.col("SALE AMOUNT").max().alias("SALE VALUE"), pl.col("_pay").max().alias("PAYMENT DATE"),
        pl.col("NEFT ID").drop_nulls().last().alias("NEFT ID"),
    ).with_columns(pl.when(pl.col("SALE VALUE") > 0).then(pl.col("SALE VALUE")).alias("SALE VALUE"))


def windowed_returns(returns, month_of_item: "pl.DataFrame") -> "pl.DataFrame":
    """The returns report lines (cancelled returns out) dated from their item's order month's 1st to the next month's
    14th (owner, 16 Nov 2026: a month's returns and RTO come from the returns report only, and only within that
    window). month_of_item: `oi` -> `_om` (order month); a line of an item with no order month is left out.
    The lines keep their columns plus `oi` and `_d` (the return date)."""
    pl = _pl()
    r = _frame(returns)
    if not r.height:
        return pl.DataFrame({"oi": [], "_d": []}, schema={"oi": pl.Utf8, "_d": pl.Datetime("us")})
    asked = pdt(pl.col("return_approval_date"))
    r = r.with_columns(oi=poi(pl.col("order_item_id")),
                       _d=pl.coalesce(asked, pdt(pl.col("return_requested_date"))) if "return_requested_date" in r.columns else asked)
    r = r.filter(pl.col("return_status").fill_null("nan").str.to_lowercase() != "cancelled")   # the item stayed sold
    # a line with no return type (return id only "RI:", 26 in Apr-25..Oct-26) is no return: it sat at the same second as the
    # item's real RTO line and took its place now and then (17 Nov 2026)
    r = r.filter(pl.col("return_type").is_not_null()) if "return_type" in r.columns else r
    om = month_of_item.unique("oi", keep="last", maintain_order=True)
    return (r.join(om, on="oi", how="inner", maintain_order="left")
             .filter((pl.col("_d") >= pl.col("_om")) & (pl.col("_d") < pl.col("_om").dt.offset_by("1mo").dt.offset_by("14d")))
             .drop("_om"))


SETTLE_OUT = ["SALE VALUE", "PAYMENT DATE", "NEFT ID"] + [c for c in SETTLE_COLS.values() if c != "SALE AMOUNT"]
RETURN_FIELDS = ["return_type", "return_id", "return_status", "return_result", "return_reason", "return_sub_reason", "_d"]


def raw_data(orders, returns, master, settled, category_of_design: dict[str, str] | None = None, sales=None,
             monthly=None) -> pd.DataFrame:
    """One row per order item (Orders report, then items only the Sales Report or the owner's monthly files have),
    with its final status, return, settlement and master fields. Polars inside; handed on as a pandas table."""
    from ..core.tables import to_pandas
    pl = _pl()
    o = _frame(orders).with_columns(oi=poi(pl.col("order_item_id")), _source=pl.lit("Orders report"))
    tax = sales_items(sales)
    parts = [o]
    if tax.height:
        parts.append(tax.filter(~pl.col("order_item_id").is_in(o["oi"].implode()))
                        .drop("_value").with_columns(oi=pl.col("order_item_id"), _source=pl.lit("Sales report")))
    items = monthly_items(monthly)
    if items.height:                                                   # items only the owner's monthly files have
        have = pl.concat([p.select("oi") for p in parts])["oi"].implode()
        parts.append(items.filter(~pl.col("order_item_id").is_in(have))
                          .with_columns(oi=pl.col("order_item_id"), _source=pl.lit("Monthly file")))
    o = pl.concat(parts, how="diagonal_relaxed")
    for c in NO_ORDER_FIELDS + ["order_item_status", "quantity", "order_id", "sku"]:
        if c not in o.columns:
            o = o.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
    o = o.with_row_index("_row")

    month_of_item = o.select("oi", _om=pdt(pl.col("order_date")).dt.truncate("1mo"))
    r = windowed_returns(returns, month_of_item)
    r = r.sort("_d", maintain_order=True, nulls_last=True).unique("oi", keep="last", maintain_order=True) if r.height else r
    r = r.select("oi", *[pl.col(c).alias(f"r.{c}") if c in r.columns else pl.lit(None, dtype=pl.Utf8).alias(f"r.{c}")
                         for c in RETURN_FIELDS], pl.lit(True).alias("r.hit"))

    m = _frame(master)
    fm = (m.filter(pl.col("Channel Name").str.to_uppercase() == "FLIPKART")
           .unique("Channel Listing SKU Code", keep="first", maintain_order=True)
           .select(pl.col("Channel Listing SKU Code").alias("_sku"),
                   *[pl.col(c).alias(f"m.{c}") for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "Brand"]]))
    s = settlement(settled)
    s = (s.select("oi", *[pl.col(c).alias(f"s.{c}") for c in SETTLE_OUT]) if s.height else
         pl.DataFrame({"oi": []}, schema={"oi": pl.Utf8}).with_columns(*[pl.lit(None).alias(f"s.{c}") for c in SETTLE_OUT]))
    tv = (tax.select(pl.col("order_item_id").alias("oi"), pl.col("_value").alias("t.value")) if tax.height else
          pl.DataFrame({"oi": [], "t.value": []}, schema={"oi": pl.Utf8, "t.value": pl.Float64}))

    x = (o.with_columns(_sku=pclean(pl.col("sku")))
          .join(fm, on="_sku", how="left", maintain_order="left")
          .join(r, on="oi", how="left", maintain_order="left")
          .join(s, on="oi", how="left", maintain_order="left")
          .join(tv, on="oi", how="left", maintain_order="left"))
    day = lambda c: pdt(pl.col(c)).dt.truncate("1d")  # noqa: E731
    rtype, st = pl.col("r.return_type"), pl.col("order_item_status").cast(pl.Utf8).str.to_uppercase()
    # returned / RTO only by a returns report line in the window; the order report's own RETURNED status is not
    # kept up to date (owner), so an item it calls returned without such a line was delivered
    final = (pl.when(rtype == "customer_return").then(pl.lit("Customer Return"))
               .when(rtype == "courier_return").then(pl.lit("RTO"))
               .when(st.is_in(["CANCELLED", "REJECTED"])).then(pl.lit("Cancelled"))
               .when(st.is_in(["DELIVERED", "RETURNED", "RETURN_REQUESTED"])).then(pl.lit("Delivered"))
               .otherwise(pl.lit("In Transit")))
    x = x.with_columns(_final=final, _token=pl.col("_sku").str.split("-").list.get(1, null_on_oob=True)
                       .str.to_uppercase().replace_strict(CATEGORY_WORDS, default=None, return_dtype=pl.Utf8))
    ret = pl.col("_final").is_in(["Customer Return", "RTO"])
    cats = category_of_design or {}
    d = x.select(
        day("order_date").alias("ORDER DATE"),
        day("order_date").dt.truncate("1mo").alias("ORDER MONTH"),
        pl.col("order_id").alias("ORDER ID"), pl.col("oi").alias("ORDER ITEM ID"), pl.col("_sku").alias("SKU"),
        pl.col("fsn").alias("FSN"), pclean(pl.col("product_title")).alias("PRODUCT TITLE"),
        *[pl.col(f"m.{c}").alias(c) for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]],
        pl.col("m.Brand").fill_null("Not Mapped").alias("BRAND"),
        pl.coalesce(pl.col("m.DESIGN-NO").replace_strict(cats, default=None, return_dtype=pl.Utf8) if cats else
                    pl.lit(None, dtype=pl.Utf8), pl.col("_token"),
                    pl.lit("Not Mapped")).alias("CATEGORY"),
        _num(pl.col("quantity")).fill_null(1).alias("QTY"),
        pl.col("fulfilment_type").alias("FULFILMENT TYPE"), pl.col("order_item_status").alias("PORTAL ORDER STATUS"),
        pl.col("_final").alias("FINAL STATUS"),
        pl.when(pl.col("r.hit")).then(pl.lit("Returns report")).otherwise(pl.lit("")).alias("RETURN TYPE SOURCE"),
        pl.when(ret).then(pl.coalesce(pl.col("r.return_reason"), pl.col("return_reason"))).otherwise(pl.lit("")).alias("REASON"),
        pl.when(ret).then(pl.coalesce(pl.col("r.return_sub_reason"), pl.col("return_sub_reason"))).otherwise(pl.lit("")).alias("SUB REASON"),
        pl.coalesce(pl.col("r.return_id"), pl.col("return_id")).alias("RETURN ID"),
        pl.col("r.return_status").alias("RETURN STATUS"), pl.col("r.return_result").alias("RETURN RESULT"),
        pl.col("r._d").dt.truncate("1d").alias("RETURN DATE"), pl.col("r._d").dt.truncate("1mo").alias("RETURN MONTH"),
        day("order_cancellation_date").alias("CANCELLED DATE"), day("dispatched_date").alias("DISPATCHED DATE"),
        day("order_delivery_date").alias("DELIVERED DATE"), pl.col("dispatch_sla_breached").alias("DISPATCH SLA BREACHED"),
        pl.coalesce(pl.col("pickup_logistics_partner"), pl.col("delivery_logistics_partner")).alias("COURIER"),
        # sale value: the tax Sales Report's Price before discount, else Settled Transactions' Sale Amount
        pl.coalesce(pl.col("t.value"), pl.col("s.SALE VALUE")).alias("SALE VALUE"),
        *[pl.col(f"s.{c}").alias(c) for c in SETTLE_OUT if c != "SALE VALUE"],
        pl.col("_source").alias("SOURCE"),
        pl.when(pl.col("s.NET SETTLEMENT").is_not_null()).then(pl.lit("Settled"))
          .when(pl.col("_final").is_in(["Delivered", "Customer Return"])).then(pl.lit("Payment Pending"))
          .otherwise(pl.lit("Not Applicable")).alias("PAYMENT STATUS"),
        "_row",
    ).sort(["ORDER DATE", "ORDER ITEM ID", "_row"], nulls_last=True).drop("_row")
    return to_pandas(d)


def returned_units(raw: pd.DataFrame, returns) -> pd.Series:
    """Units returned per row of raw: the returns report quantity of the item's lines in its window (windowed_returns),
    each return once; a line can return no more than it holds. The returns report only (owner, 16 Nov 2026)."""
    from ..core.tables import to_polars
    pl = _pl()
    keys = to_polars(raw[["ORDER ITEM ID", "ORDER MONTH"]]).select(
        pl.col("ORDER ITEM ID").alias("oi"), pdt(pl.col("ORDER MONTH")).alias("_om"))
    r = windowed_returns(returns, keys)
    if not r.height:
        return pd.Series(0.0, index=raw.index)
    units = (r.unique(["oi", "return_id"], keep="first", maintain_order=True)
              .group_by("oi").agg(_u=_num(pl.col("quantity")).fill_null(1).sum()))
    got = keys.join(units, on="oi", how="left", maintain_order="left")["_u"].fill_null(0).to_list()
    return pd.Series(got, index=raw.index, dtype=float).clip(upper=raw["QTY"])


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
