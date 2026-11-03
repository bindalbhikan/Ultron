"""GROSS, RETURN and CANCEL units per ORDER date and report block: the sale of a day against what later
happened to those same orders. Every function gives {metric: Counter[(order day, block)]}.

  Myntra    Seller_Orders_Report by created on, a line = 1 unit. CANCEL = status F; RETURN = an RTO (status
            RTO or an RTO date) or a return creation date. po_type FBM / SJIT = block SJIT, else MYNTRA
  Flipkart  Orders by order_date. RETURN = RETURNED, RETURN_REQUESTED; CANCEL = CANCELLED.
            fulfilment type FBF = block FBF, else FLIPKART
  AJIO      Dropship order report by Cust Order Date: Order Qty, Cancelled Qty. RETURN = the RTV lines of those
            customer orders (any return date), without cancelled pickups
  OMSGuru   the order list's line status by order date (for the channels with no portal client)
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

SJIT_MODELS = {"FBM", "SJIT"}
OMS_RETURN = {"return init", "return received", "partial return received"}
OMS_CANCEL = {"cancelled", "cancelled before shipping", "removed before shipping", "cancel init",
              "cancelled return received", "partial cancelled return received"}


def read_report(path: Path, needed: str) -> pd.DataFrame:
    """A report's rows as text, headers in lower case; for a workbook the first sheet with column
    `needed` (Flipkart's start with a Help sheet). Raises when no sheet has it: the report changed."""
    if path.suffix.lower() == ".csv":
        frames = [pd.read_csv(path, dtype=str, low_memory=False)]
    else:
        frames = list(pd.read_excel(path, sheet_name=None, dtype=str).values())
    for df in frames:
        df = df.rename(columns=lambda c: str(c).strip().casefold())
        if needed.casefold() in df.columns:
            return df
    raise ValueError(f"{path.name}: no column {needed!r}")


def _count(days: pd.Series, qty: pd.Series, blocks: pd.Series | str) -> Counter:
    frame = pd.DataFrame({"day": days, "qty": qty})
    frame["block"] = blocks
    frame = frame[frame["day"].notna() & (frame["qty"] != 0)]
    out: Counter = Counter()
    if not frame.empty:
        for (day, block), value in frame.groupby([frame["day"].dt.date, "block"])["qty"].sum().items():
            out[(day, block)] += int(value)
    return out


def _qty(df: pd.DataFrame, column: str, default: int = 1) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def _iso(values: pd.Series) -> pd.Series:
    """Dates that start with YYYY-MM-DD."""
    return pd.to_datetime(values.astype(str).str[:10], format="%Y-%m-%d", errors="coerce")


def _ajio_date(values: pd.Series) -> pd.Series:
    """AJIO writes 'Wed Sep 30 23:21:44 IST 2026'."""
    return pd.to_datetime(values.astype(str).str.replace(" IST ", " ", regex=False),
                          format="%a %b %d %H:%M:%S %Y", errors="coerce")


def myntra_orders(df: pd.DataFrame) -> dict[str, Counter]:
    day = _iso(df["created on"])
    block = df["po_type"].astype(str).str.strip().str.upper().map(lambda m: "SJIT" if m in SJIT_MODELS else "MYNTRA")
    status = df["order status"].astype(str).str.strip().str.upper()
    cancel = status == "F"
    rto = ~cancel & (df["rto creation date"].notna() | (status == "RTO"))
    returned = ~cancel & (rto | df["return creation date"].notna())
    one = pd.Series(1, index=df.index)
    return {"GROSS": _count(day, one, block), "RETURN": _count(day, one.where(returned, 0), block),
            "CANCEL": _count(day, one.where(cancel, 0), block)}


def flipkart_orders(df: pd.DataFrame) -> dict[str, Counter]:
    day = _iso(df["order_date"])
    qty = _qty(df, "quantity")
    block = df["fulfilment_type"].astype(str).str.replace(r"[\s_]", "", regex=True).str.upper().map(
        lambda t: "FBF" if t == "FBF" else "FLIPKART")
    status = df["order_item_status"].astype(str).str.strip().str.upper()
    return {"GROSS": _count(day, qty, block),
            "RETURN": _count(day, qty.where(status.isin(["RETURNED", "RETURN_REQUESTED"]), 0), block),
            "CANCEL": _count(day, qty.where(status == "CANCELLED", 0), block)}


def ajio_orders(orders: pd.DataFrame, rtv: pd.DataFrame) -> dict[str, Counter]:
    day = _ajio_date(orders["cust order date"])
    first_day = pd.DataFrame({"order": orders["cust order no"], "day": day}).dropna().groupby("order")["day"].min()
    rtv = rtv[~rtv["3pl delivery status"].astype(str).str.contains("cancel", case=False)]
    rtv = rtv.drop_duplicates(["return order number", "seller sku"])
    matched = rtv[rtv["cust order no"].isin(first_day.index)]
    return {"GROSS": _count(day, _qty(orders, "order qty"), "AJIO B2C"),
            "CANCEL": _count(day, _qty(orders, "cancelled qty", 0), "AJIO B2C"),
            "RETURN": _count(matched["cust order no"].map(first_day), _qty(matched, "return qty"), "AJIO B2C")}


def oms_metric(status: str) -> str | None:
    """RETURN / CANCEL for an OMSGuru line status; None for a line still sold."""
    low = status.strip().casefold()
    if low in OMS_RETURN:
        return "RETURN"
    if low in OMS_CANCEL:
        return "CANCEL"
    return None


def last_day(counted: dict[str, Counter]) -> date | None:
    return max((day for day, _ in counted["GROSS"]), default=None)
