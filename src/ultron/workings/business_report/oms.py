"""OMSGuru's order lines in the Flipkart and AJIO analysis (owner's rule, 3 Nov 2026: OMSGuru's sale and return status).

  OMSGURU REPORT  one file a month in PORTAL REPORTS: every line of the channels Flipkart, Ajio and Ajio Api (Ajio up to
                  Feb-26, Ajio Api after), by order date: order id, SKU (the FINAL SKU of MasterSheet), qty, status, value.

Checked against the portals' own reports, Jan-26 to Sep-26, on 43,000 one-line orders: Delivered, Cancelled and Cancelled
Before Shipping mean the same; Return Init / Return Received = customer return; Cancelled Return Received and Cancel
Init = RTO. It is not whole: Flipkart FBF orders are not in it, and most orders cancelled before shipping are not.
So it corrects a line the reports have, and adds a line only in a month with no fuller report.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

FINAL = {"cancelled": "Cancelled", "cancelled before shipping": "Cancelled",
         "cancelled return received": "RTO", "partial cancelled return received": "RTO", "cancel init": "RTO",
         "return init": "Customer Return", "return received": "Customer Return", "partial return received": "Customer Return",
         "delivered": "Delivered"}
COLUMNS = ["DAY", "CHANNEL", "ORDER", "SKU", "QTY", "STATUS", "VALUE"]


def rows_of(lines: list[dict], names: dict[str, str]) -> pd.DataFrame:
    """OMSGuru order list lines (ultron.portals.omsguru_orders) as one row per SKU, exact repeats once."""
    rows = [{"DAY": r["day"], "CHANNEL": names.get(r["channel"], r["channel"]), "ORDER": r["order"], "SKU": sku.upper(),
             "QTY": qty, "STATUS": r["status"].strip(), "VALUE": r["value"]}
            for r in lines for sku, qty in (r["skus"] or [("", r["qty"])])]
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.drop_duplicates(["CHANNEL", "ORDER", "SKU", "DAY", "QTY", "STATUS"])


def read(files: list[Path]) -> pd.DataFrame:
    frames = [pd.read_excel(f, dtype=str).assign(_file=f.name) for f in files]
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame(columns=COLUMNS + ["_file", "FINAL"])
    df = pd.concat(frames, ignore_index=True)
    df["ORDER"] = df["ORDER"].astype(str).str.strip()
    df["SKU"] = df["SKU"].fillna("").astype(str).str.strip().str.upper()
    df["QTY"] = pd.to_numeric(df["QTY"], errors="coerce").fillna(1)
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
    df["DAY"] = pd.to_datetime(df["DAY"], errors="coerce").dt.normalize()
    df["FINAL"] = df["STATUS"].str.strip().str.lower().map(FINAL).fillna("In Transit")
    return df


def match(raw: pd.DataFrame, id_col: str, oms: pd.DataFrame) -> tuple[pd.Series, set]:
    """For every raw line its OMSGuru row (index, -1 = none), and the rows used. By order id + FINAL SKU, the nth line with
    the nth; then a line left over with the only row left of its order (a SKU spelled otherwise in the master)."""
    ids = raw[id_col].astype(str).str.strip()
    skus = raw["FINAL SKU"].fillna("").astype(str).str.strip().str.upper()
    nth = pd.DataFrame({"i": ids, "s": skus}).groupby(["i", "s"]).cumcount()
    a = ids + "|" + skus + "|" + nth.astype(str)
    b = oms["ORDER"] + "|" + oms["SKU"] + "|" + oms.groupby(["ORDER", "SKU"]).cumcount().astype(str)
    index_of = pd.Series(oms.index, index=b.values)
    found = a.map(index_of).fillna(-1).astype(int)
    used = set(found[found >= 0])
    left = oms[~oms.index.isin(used)]
    alone = left.groupby("ORDER").filter(lambda g: len(g) == 1)
    waiting = ids[found < 0]
    single = waiting[waiting.map(waiting.value_counts()) == 1]
    by_order = pd.Series(alone.index, index=alone["ORDER"].values)
    second = single.map(by_order).dropna().astype(int)
    found.loc[second.index] = second
    used |= set(second)
    return found, used


def status_of(raw: pd.DataFrame, found: pd.Series, oms: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(OMSGuru's status, its final status) of every raw line, blank when it has none."""
    has = found >= 0
    text = pd.Series("", index=raw.index, dtype=object)
    final = pd.Series("", index=raw.index, dtype=object)
    text.loc[has] = oms.loc[found[has], "STATUS"].values
    final.loc[has] = oms.loc[found[has], "FINAL"].values
    return text, final


def corrected(current: pd.Series, final: pd.Series, keep: pd.Series) -> pd.Series:
    """The final status after OMSGuru: a return, an RTO or a cancellation it shows replaces Delivered, In Transit or Return
    Type Pending; its Delivered replaces In Transit. keep: lines a return report has settled are not touched."""
    out = current.copy()
    open_line = current.isin(["Delivered", "In Transit", "Return Type Pending"]) & ~keep
    hit = open_line & final.isin(["Customer Return", "RTO", "Cancelled"])
    out.loc[hit] = final[hit]
    done = current.eq("In Transit") & final.eq("Delivered")
    out.loc[done] = "Delivered"
    return out
