"""Flipkart sale / return analysis workbook (the owner's business reporting, Flipkart part).

Built like the Myntra analysis (Drive AGENT WORK/BUSINESS REPORTING, its CONTEXT.md): one row per
order item in RAW DATA, every number on the other sheets a SUMIFS on RAW DATA (written with its
value, so Drive / Google previews show it before Excel recalculates), by ORDER MONTH (what happened
to each month's orders). Look: yellow family, black text, no comments / emoji / charts / wrap,
values left + middle, headers centre + middle.

Inputs (PORTAL REPORTS, or the owner's files): the Seller Hub "Orders" report (one row per order
item, status, no price) and the "Returns" report (one row per return line). Payments (Settled
Transactions) are not used yet: no value or payment columns until they are in (owner, 1 Nov 2026).

FINAL STATUS of an order item:
  Customer Return   a return line of type customer_return (a cancelled return = not returned)
  RTO               a return line of type courier_return
  Cancelled         portal status CANCELLED / REJECTED
  Delivered         portal status DELIVERED, no return line
  Return Type Pending  portal status RETURNED / RETURN_REQUESTED without a return line: the type is
                    taken from the order's own return reason when that reason is only ever one
                    type; otherwise it waits for the returns report (never guessed)
  In Transit        anything else (READY_TO_SHIP, APPROVED, ...)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("bindal.business_report")

YELLOW, LIGHT, TITLE, EDGE = "#FFC000", "#FFE699", "#FFF2CC", "#BF8F00"
STATUSES = ["Delivered", "Customer Return", "RTO", "Cancelled", "Return Type Pending", "In Transit"]


# ------------------------------------------------------------------ data

def clean_sku(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace('"', "", regex=False).str.replace("SKU:", "", regex=False).str.strip()


def dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str[:19], errors="coerce", format="mixed")


def one_spelling(s: pd.Series) -> pd.Series:
    """Values that differ only in letter case or spaces become their most common spelling: Excel's
    SUMIFS does not tell "Customer requested" from "customer requested", so the sheets would count
    such a pair twice."""
    t = pd.Series(s, dtype=object).where(pd.notna(s), "").astype(str).str.strip()
    key = t.str.lower().str.replace(r"\s+", " ", regex=True)
    best = t[t != ""].groupby(key[t != ""]).agg(lambda x: x.value_counts().index[0])
    return key.map(best).fillna(t).values


def raw_data(orders: pd.DataFrame, returns: pd.DataFrame, master: pd.DataFrame,
             category_of_design: dict[str, str] | None = None) -> pd.DataFrame:
    o = orders.drop_duplicates("order_item_id", keep="last").copy()
    o["oi"] = o["order_item_id"].str.replace("OI:", "", regex=False)
    r = returns.copy()
    r["oi"] = r["order_item_id"].str.replace("OI:", "", regex=False)
    r["_d"] = dt(r["return_approval_date"])
    r = r[r["return_status"].str.lower() != "cancelled"]          # a cancelled return: the item stayed sold
    r = r.sort_values("_d").drop_duplicates("oi", keep="last").set_index("oi")

    fm = master[master["Channel Name"].str.upper().eq("FLIPKART")].drop_duplicates("Channel Listing SKU Code")
    fm = fm.set_index("Channel Listing SKU Code")
    sku = clean_sku(o["sku"])
    d = pd.DataFrame({
        "ORDER DATE": dt(o["order_date"]).dt.normalize().values,
        "ORDER ID": o["order_id"].values,
        "ORDER ITEM ID": o["oi"].values,
        "SKU": sku.values,
        "FSN": o["fsn"].values,
        "PRODUCT TITLE": clean_sku(o["product_title"]).values,
    })
    d["ORDER MONTH"] = d["ORDER DATE"].dt.to_period("M").dt.to_timestamp()
    for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]:
        d[c] = sku.map(fm[c]).values
    d["BRAND"] = sku.map(fm["Brand"]).fillna("Not Mapped").values
    cat = d["DESIGN-NO"].map(category_of_design or {})
    token = d["SKU"].str.split("-").str[1].str.upper().map({"COORD": "Co-Ords", "DRESS": "Dresses", "TOP": "Tops",
                                                             "JUMPSUIT": "Jumpsuit", "SHIRT": "Shirts"})
    d["CATEGORY"] = cat.fillna(token).fillna("Not Mapped").values
    d["QUANTITY"] = pd.to_numeric(o["quantity"], errors="coerce").fillna(1).values
    d["FULFILMENT TYPE"] = o["fulfilment_type"].values
    d["PORTAL ORDER STATUS"] = o["order_item_status"].values

    oi = d["ORDER ITEM ID"]
    rtype = oi.map(r["return_type"])
    st = o["order_item_status"].str.upper().values
    # a return without its return line: its reason decides when that reason belongs to one type only
    known = pd.DataFrame({"reason": o["return_reason"].values, "type": rtype.values}).dropna()
    one_type = known.groupby("reason")["type"].agg(lambda x: x.iloc[0] if x.nunique() == 1 else None).dropna()
    by_reason = pd.Series(o["return_reason"].values).map(one_type)
    pending = np.isin(st, ["RETURNED", "RETURN_REQUESTED"]) & rtype.isna().values
    rtype = rtype.where(~pending, by_reason.values)
    final = np.select(
        [rtype.eq("customer_return").values, rtype.eq("courier_return").values,
         np.isin(st, ["CANCELLED", "REJECTED"]), st == "DELIVERED",
         np.isin(st, ["RETURNED", "RETURN_REQUESTED"])],
        ["Customer Return", "RTO", "Cancelled", "Delivered", "Return Type Pending"], default="In Transit")
    d["FINAL STATUS"] = final
    d["RETURN TYPE SOURCE"] = np.where(oi.isin(r.index), "Returns report",
                                       np.where(pending & by_reason.notna().values, "Order return reason", ""))
    d["RETURN ID"] = oi.map(r["return_id"]).fillna(pd.Series(o["return_id"].values)).values
    d["RETURN STATUS"] = oi.map(r["return_status"]).values
    d["RETURN RESULT"] = oi.map(r["return_result"]).values
    reason = oi.map(r["return_reason"]).fillna(pd.Series(o["return_reason"].values))
    sub = oi.map(r["return_sub_reason"]).fillna(pd.Series(o["return_sub_reason"].values))
    d["REASON"] = np.where(np.isin(final, ["Customer Return", "RTO", "Return Type Pending"]), reason, "")
    d["SUB REASON"] = np.where(np.isin(final, ["Customer Return", "RTO", "Return Type Pending"]), sub, "")
    for c in ["REASON", "SUB REASON", "BRAND", "CATEGORY"]:
        d[c] = one_spelling(d[c])
    d["RETURN DATE"] = oi.map(r["_d"]).dt.normalize().values
    d["RETURN MONTH"] = pd.Series(d["RETURN DATE"]).dt.to_period("M").dt.to_timestamp().values
    d["CANCELLED DATE"] = dt(o["order_cancellation_date"]).dt.normalize().values
    d["DISPATCHED DATE"] = dt(o["dispatched_date"]).dt.normalize().values
    d["DELIVERED DATE"] = dt(o["order_delivery_date"]).dt.normalize().values
    d["DISPATCH SLA BREACHED"] = o["dispatch_sla_breached"].values
    d["COURIER"] = o["pickup_logistics_partner"].fillna(o["delivery_logistics_partner"]).values
    return d.sort_values(["ORDER DATE", "ORDER ITEM ID"]).reset_index(drop=True)


# ------------------------------------------------------------------ workbook

RAW_COLS = ["ORDER DATE", "ORDER MONTH", "ORDER ID", "ORDER ITEM ID", "SKU", "FSN", "PRODUCT TITLE", "MY SKU",
            "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "BRAND", "CATEGORY", "QUANTITY", "FULFILMENT TYPE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "RETURN TYPE SOURCE", "REASON", "SUB REASON", "RETURN ID",
            "RETURN STATUS", "RETURN RESULT", "RETURN DATE", "RETURN MONTH", "CANCELLED DATE", "DISPATCHED DATE",
            "DELIVERED DATE", "DISPATCH SLA BREACHED", "COURIER"]

# (group header, sub header, key)
SPEC = [("SALE", "Gross Qty", "g"), ("CANCELLED", "Qty", "Cancelled"), ("CANCELLED", "% of Gross", "cp"),
        ("RTO", "Qty", "RTO"), ("RTO", "% of Dispatched", "rp"),
        ("CUSTOMER RETURN", "Qty", "Customer Return"), ("CUSTOMER RETURN", "% of Delivered", "tp"),
        ("RETURN TYPE PENDING", "Qty", "Return Type Pending"), ("IN TRANSIT", "Qty", "In Transit"),
        ("NET SALE", "Qty", "Delivered"), ("NET SALE", "% of Gross", "np"), ("NET SALE", "MoM Growth %", "mom")]
PCT = {"cp", "rp", "tp", "np", "mom", "share"}


class Book:
    def __init__(self, path: Path, raw: pd.DataFrame):
        import xlsxwriter
        from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell
        self.cell, self.col_name = xl_rowcol_to_cell, xl_col_to_name
        self.wb = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True})
        self.raw = raw
        base = {"font_name": "Calibri", "font_size": 10, "font_color": "#000000", "valign": "vcenter", "align": "left"}
        box = {"border": 1, "border_color": "#BFBFBF"}
        tot = {"bold": True, "bg_color": LIGHT, "border": 1, "border_color": EDGE}
        f = lambda **k: self.wb.add_format({**base, **k})  # noqa: E731
        self.hdr = f(bold=True, bg_color=YELLOW, border=1, border_color=EDGE, align="center")
        self.sub = f(bold=True, bg_color=LIGHT, border=1, border_color=EDGE, align="center")
        self.title = f(bold=True, font_size=12, bg_color=TITLE, border=1, border_color=EDGE)
        self.txt, self.int, self.pct, self.mon = f(**box), f(num_format="#,##0", **box), f(num_format="0.0%", **box), f(num_format="mmm-yy", **box)
        self.ttxt, self.tint, self.tpct = f(**tot), f(num_format="#,##0", **tot), f(num_format="0.0%", **tot)
        self.dash, self.tdash = f(**box), f(**tot)
        self.day, self.month, self.plain = f(num_format="dd-mmm-yy"), f(num_format="mmm-yy"), f()
        self.last = len(raw) + 1

    def rng(self, col: str) -> str:
        c = self.col_name(RAW_COLS.index(col))
        return f"'RAW DATA'!${c}$2:${c}${self.last}"

    @staticmethod
    def q(text) -> str:
        t = str(text).replace("~", "~~").replace("*", "~*").replace("?", "~?").replace('"', '""')
        return f'"{t}"'

    def qty(self, crit: list[tuple[str, str]], status: str | None, frame: pd.DataFrame) -> tuple[str, float]:
        """SUMIFS formula of QUANTITY for crit (+ status) and its value on frame."""
        args = [self.rng("QUANTITY")]
        for col, val in crit + ([("FINAL STATUS", self.q(status))] if status else []):
            args += [self.rng(col), val]
        if len(args) == 1:
            args += [self.rng("ORDER ITEM ID"), '"<>"']
        g = frame if status is None else frame[frame["FINAL STATUS"] == status]
        return f"=SUMIFS({','.join(args)})", float(g["QUANTITY"].sum())

    def block(self, ws, r: int, first: str, title: str | None, rows: list, spec: list, share_total: float = 0,
              share_cell: str = "") -> int:
        """rows: (label, criteria, frame); the last row is the total. Returns the next free row."""
        if title:
            ws.merge_range(r, 0, r, len(spec), title, self.title)
            r += 1
        ws.merge_range(r, 0, r + 1, 0, first, self.hdr)
        j = 0
        while j < len(spec):
            k = j
            while k + 1 < len(spec) and spec[k + 1][0] == spec[j][0]:
                k += 1
            (ws.merge_range(r, 1 + j, r, 1 + k, spec[j][0], self.hdr) if k > j else ws.write(r, 1 + j, spec[j][0], self.hdr))
            j = k + 1
        for j, (_, sub, _) in enumerate(spec):
            ws.write(r + 1, 1 + j, sub, self.sub)
        r += 2
        col = {key: 1 + j for j, (_, _, key) in enumerate(spec)}
        prev_net = None
        for n, (label, crit, frame) in enumerate(rows):
            last = n == len(rows) - 1
            if isinstance(label, pd.Timestamp):
                ws.write_datetime(r, 0, label.to_pydatetime(), self.ttxt if last else self.mon)
            else:
                ws.write_string(r, 0, str(label), self.ttxt if last else self.txt)
            v = {}
            for key in ["g"] + STATUSES:
                if key in col:
                    fm, v[key] = self.qty(crit, None if key == "g" else key, frame)
                    ws.write_formula(r, col[key], fm, self.tint if last else self.int, v[key])
            c = {k: self.cell(r, i) for k, i in col.items()}

            def ratio(key, num, den_cells, den_val, num_val):
                if key not in col:
                    return
                val = num_val / den_val if den_val else "-"
                ws.write_formula(r, col[key], f'=IF({den_cells}=0,"-",{c[num]}/({den_cells}))',
                                 self.tpct if last else self.pct, val)
            ratio("cp", "Cancelled", c["g"], v["g"], v["Cancelled"])
            ratio("rp", "RTO", f'{c["g"]}-{c["Cancelled"]}', v["g"] - v["Cancelled"], v["RTO"])
            ratio("tp", "Customer Return", f'{c["Delivered"]}+{c["Customer Return"]}',
                  v["Delivered"] + v["Customer Return"], v["Customer Return"])
            ratio("np", "Delivered", c["g"], v["g"], v["Delivered"])
            if "mom" in col:
                if prev_net is None or last:
                    ws.write_string(r, col["mom"], "-", self.tdash if last else self.dash)
                else:
                    p = self.cell(r - 1, col["Delivered"])
                    ws.write_formula(r, col["mom"], f'=IF({p}=0,"-",{c["Delivered"]}/{p}-1)', self.pct,
                                     v["Delivered"] / prev_net - 1 if prev_net else "-")
            if "share" in col:
                ws.write_formula(r, col["share"], f'=IF({share_cell}=0,"-",{c["Delivered"]}/{share_cell})',
                                 self.tpct if last else self.pct, v["Delivered"] / share_total if share_total else "-")
            prev_net = v["Delivered"]
            r += 1
        return r

    def widths(self, ws, first: int, spec: list) -> None:
        ws.set_column(0, 0, first)
        for j, (_, sub, _) in enumerate(spec):
            ws.set_column(1 + j, 1 + j, max(len(sub) + 3, 12))


def build(raw: pd.DataFrame, out: Path, input_log: list[list], min_orders: int = 300) -> Path:
    b = Book(out, raw)
    wb = b.wb
    ws_raw = wb.add_worksheet("RAW DATA")
    months = sorted(raw["ORDER MONTH"].dropna().unique())
    pending = (raw["FINAL STATUS"] == "Return Type Pending").any()
    spec = [s for s in SPEC if pending or s[2] != "Return Type Pending"]

    # SUMIFS on a date column: the month's Excel serial number
    def month_crit(m: pd.Timestamp) -> str:
        return str((m - pd.Timestamp("1899-12-30")).days)

    def rows_by_month(frame: pd.DataFrame, extra: list) -> list:
        out_rows = [(pd.Timestamp(m), extra + [("ORDER MONTH", month_crit(pd.Timestamp(m)))],
                     frame[frame["ORDER MONTH"] == pd.Timestamp(m)]) for m in months]
        return out_rows + [("Total", extra, frame)]

    ws = wb.add_worksheet("MONTH WISE")
    b.block(ws, 0, "Month", None, rows_by_month(raw, []), spec)
    b.widths(ws, 10, spec)
    ws.freeze_panes(2, 1)

    for name, col in [("BRAND WISE", "BRAND"), ("CATEGORY WISE", "CATEGORY")]:
        ws = wb.add_worksheet(name)
        size = raw.groupby(col)["QUANTITY"].sum()
        named = [g for g in size.sort_values(ascending=False).index if size[g] >= min_orders]
        rest = raw[~raw[col].isin(named)]
        spec_all = [s for s in spec if s[2] != "mom"] + [("NET SALE", "Share in Net Sale %", "share")]
        total_net = float(raw.loc[raw["FINAL STATUS"] == "Delivered", "QUANTITY"].sum())
        n_rows = len(named) + (1 if len(rest) else 0) + 1
        share_cell = b.cell(3 + n_rows - 1, 1 + [k for _, _, k in spec_all].index("Delivered"), True, True)
        rows = [(g, [(col, b.q(g))], raw[raw[col] == g]) for g in named]
        if len(rest):
            rows.append(("Others", [(col, f'"<>{g}"') for g in named], rest))
        rows.append(("Total", [], raw))
        label = col.title()
        r = b.block(ws, 0, label, f"ALL {col.replace('Y', 'IE') if col.endswith('Y') else col}S - "
                    f"{pd.Timestamp(months[0]):%b-%y} TO {pd.Timestamp(months[-1]):%b-%y}".upper(),
                    rows, spec_all, total_net, share_cell) + 2
        for g in named + (["Others"] if len(rest) else []):
            crit = [(col, b.q(g))] if g != "Others" else [(col, f'"<>{x}"') for x in named]
            frame = raw[raw[col] == g] if g != "Others" else rest
            r = b.block(ws, r, "Month", f"{col}: {g}", rows_by_month(frame, crit), spec) + 2
        b.widths(ws, 26, spec_all)
        ws.freeze_panes(0, 1)

    # REASONS: customer return and RTO reasons side by side
    ws = wb.add_worksheet("REASONS")
    c0 = 0
    for label, status in [("Customer Return Reason", "Customer Return"), ("RTO Reason", "RTO")]:
        fr = raw[raw["FINAL STATUS"] == status]
        t = fr.assign(R=fr["REASON"].replace("", np.nan).fillna("Not Given")).groupby("R")["QUANTITY"].sum().sort_values(ascending=False)
        for j, h in enumerate([label, "Qty", "%"]):
            ws.write(0, c0 + j, h, b.hdr)
        end = len(t) + 1
        tot_cell = b.cell(end, c0 + 1, True, True)
        for i, (reason, qn) in enumerate(t.items(), start=1):
            crit = '"="' if reason == "Not Given" else b.q(reason)
            ws.write_string(i, c0, reason, b.txt)
            ws.write_formula(i, c0 + 1, b.qty([("REASON", crit)], status, raw)[0], b.int, float(qn))
            ws.write_formula(i, c0 + 2, f'=IF({tot_cell}=0,"-",{b.cell(i, c0 + 1)}/{tot_cell})', b.pct,
                             float(qn) / float(t.sum()) if t.sum() else "-")
        ws.write_string(end, c0, "Total", b.ttxt)
        ws.write_formula(end, c0 + 1, f"=SUM({b.cell(1, c0 + 1)}:{b.cell(end - 1, c0 + 1)})", b.tint, float(t.sum()))
        ws.write_formula(end, c0 + 2, f"=SUM({b.cell(1, c0 + 2)}:{b.cell(end - 1, c0 + 2)})", b.tpct, 1.0 if t.sum() else 0)
        ws.set_column(c0, c0, 40)
        ws.set_column(c0 + 1, c0 + 2, 12)
        ws.set_column(c0 + 3, c0 + 3, 3)
        c0 += 4
    ws.freeze_panes(1, 0)

    # INPUT LOG
    ws = wb.add_worksheet("INPUT LOG")
    heads = ["Input", "File", "Rows", "Date Used", "From", "To", "Note"]
    for j, h in enumerate(heads):
        ws.write(0, j, h, b.hdr)
    for i, row in enumerate(input_log, start=1):
        for j, v in enumerate(row):
            if isinstance(v, pd.Timestamp) and pd.notna(v):
                ws.write_datetime(i, j, v.to_pydatetime(), b.wb.add_format({"font_name": "Calibri", "font_size": 10,
                                  "num_format": "dd-mmm-yy", "align": "left", "valign": "vcenter", "border": 1, "border_color": "#BFBFBF"}))
            elif isinstance(v, (int, float, np.integer)) and not isinstance(v, bool):
                ws.write_number(i, j, float(v), b.int)
            else:
                ws.write_string(i, j, "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v), b.txt)
    for j, w in enumerate([22, 52, 10, 26, 11, 11, 70]):
        ws.set_column(j, j, w)
    ws.freeze_panes(1, 0)

    # RAW DATA (first in the tab order)
    for j, c in enumerate(RAW_COLS):
        ws_raw.write(0, j, c, b.hdr)
        w = len(c) + 3
        ws_raw.set_column(j, j, max(w, 12 if ("DATE" in c or "MONTH" in c) else 40 if c in ("PRODUCT TITLE", "REASON", "SUB REASON") else 16))
    kinds = [("m", b.month) if "MONTH" in c else ("d", b.day) if "DATE" in c else ("n", b.plain) if c == "QUANTITY"
             else ("s", b.plain) for c in RAW_COLS]
    cols = [raw[c].to_numpy(dtype=object) for c in RAW_COLS]
    for i in range(len(raw)):
        for j, (k, f) in enumerate(kinds):
            v = cols[j][i]
            if v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and v in ("", "nan")):
                continue
            if k in "md":
                ws_raw.write_datetime(i + 1, j, pd.Timestamp(v).to_pydatetime(), f)
            elif k == "n":
                ws_raw.write_number(i + 1, j, float(v), f)
            else:
                ws_raw.write_string(i + 1, j, str(v), f)
    ws_raw.freeze_panes(1, 4)
    ws_raw.autofilter(0, 0, len(raw), len(RAW_COLS) - 1)
    wb.close()
    log.info("Flipkart analysis: %d order items -> %s", len(raw), out)
    return out


def category_map_from_myntra(orders_parquet: Path, master: pd.DataFrame) -> dict[str, str]:
    """DESIGN-NO -> the article type Myntra lists it under (the most common one)."""
    o = pd.read_parquet(orders_parquet, columns=["myntra sku code", "seller sku code", "article type"])
    mm = master[master["Channel Name"].str.startswith("MYNTRA", na=False)]
    by_code = mm.dropna(subset=["MYNTRA SKU CODE"]).drop_duplicates("MYNTRA SKU CODE").set_index("MYNTRA SKU CODE")["DESIGN-NO"]
    by_sku = master.drop_duplicates("Channel Listing SKU Code").set_index("Channel Listing SKU Code")["DESIGN-NO"]
    design = o["myntra sku code"].map(by_code).fillna(o["seller sku code"].map(by_sku))
    t = pd.DataFrame({"d": design, "a": o["article type"]}).dropna()
    return t.groupby("d")["a"].agg(lambda x: x.value_counts().index[0]).to_dict()


def month_span(s: pd.Series) -> str:
    s = s.dropna()
    return "" if s.empty else f"{s.min():%d-%b-%y} to {s.max():%d-%b-%y}"


def safe(name: str) -> str:
    return re.sub(r"[^\w .-]", "_", name)
