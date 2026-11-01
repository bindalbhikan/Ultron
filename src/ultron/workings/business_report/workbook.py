"""The business reporting workbook, the same for every portal (the owner's Myntra layout, Drive
AGENT WORK/BUSINESS REPORTING, docs/bots/business-report-context.md):

  RAW DATA             one row per order line (portal columns + the standard ones below)
  MONTH WISE           SALE / CANCELLED / RTO / CUSTOMER RETURN / NET SALE (Qty, Value, ASP, MoM) /
                       LAST YEAR (YoY) / PAYMENT (Net Received) per ORDER MONTH
  BRAND WISE           all brands together, then one block per brand, every month
  CATEGORY WISE        the same per category
  BRAND CATEGORY WISE  the same per brand + category pair ("DressBerry - Tops")
  REASONS              customer return reasons next to cancellation / RTO reasons
  PAYMENT              payment against the orders of each month, then cash received by payment month
  INPUT LOG            every input file, rows and dates

Every number is a SUMIFS on RAW DATA written together with its value (worked out here), so Drive /
Google previews show the numbers before Excel recalculates. Groups under min_orders are "Others"
(the total less the named ones). Look: yellow family, black text, no comments, emoji, charts, KPI
tiles or wrap; values left + middle, headers centre + middle.

Standard RAW DATA columns: ORDER DATE, ORDER MONTH, BRAND, CATEGORY, QTY, FINAL STATUS, REASON;
the sale value and the net settlement columns when the portal has them (Report.value / .settle).
FINAL STATUS: Delivered, Customer Return, RTO, Cancelled, In Transit (+ Return Type Pending).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("bindal.business_report")

YELLOW, LIGHT, TITLE, EDGE = "#FFC000", "#FFE699", "#FFF2CC", "#BF8F00"
EXCEL_DAY0 = pd.Timestamp("1899-12-30")
STANDARD = ["ORDER DATE", "ORDER MONTH", "BRAND", "CATEGORY", "QTY", "FINAL STATUS", "REASON"]


@dataclass
class Report:
    portal: str
    raw: pd.DataFrame
    raw_cols: list[str]                       # RAW DATA columns in order (the standard ones included)
    value: str | None = None                  # sale value column
    settle: str | None = None                 # net settlement column (payment against the order line)
    money_cols: set[str] = field(default_factory=set)
    reasons: list[tuple[str, str]] = field(default_factory=lambda: [("Customer Return Reason", "Customer Return"),
                                                                      ("Cancellation Reason", "Cancelled")])
    pay_table: list[tuple[str, str]] = field(default_factory=list)   # PAYMENT (1): (header, RAW column), net last
    pay_months: pd.DataFrame | None = None    # PAYMENT (2): cash by payment month (values)
    input_log: pd.DataFrame | None = None
    min_orders: int = 500


def one_spelling(s: pd.Series) -> np.ndarray:
    """Values that differ only in letter case or spaces become their most common spelling: Excel's
    SUMIFS does not tell "Customer requested" from "customer requested"."""
    t = pd.Series(s, dtype=object).where(pd.notna(s), "").astype(str).str.strip()
    key = t.str.lower().str.replace(r"\s+", " ", regex=True)
    best = t[t != ""].groupby(key[t != ""]).agg(lambda x: x.value_counts().index[0])
    return key.map(best).fillna(t).values


class Writer:
    # key -> (FINAL STATUS or None for every line, measure)
    BASE = {"gq": (None, "QTY"), "gv": (None, "VALUE"), "cq": ("Cancelled", "QTY"), "rq": ("RTO", "QTY"),
            "tq": ("Customer Return", "QTY"), "tv": ("Customer Return", "VALUE"),
            "pq": ("Return Type Pending", "QTY"), "nq": ("Delivered", "QTY"), "nv": ("Delivered", "VALUE"),
            "recv": (("Delivered", "Customer Return"), "SETTLE")}

    def __init__(self, rep: Report, path: Path):
        import xlsxwriter
        from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell
        self.cell, self.colname = xl_rowcol_to_cell, xl_col_to_name
        self.r, self.raw = rep, rep.raw
        for c in ["BRAND", "CATEGORY", "REASON"]:
            self.raw[c] = one_spelling(self.raw[c])
        self.wb = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True})
        base = {"font_name": "Calibri", "font_size": 10, "font_color": "#000000", "valign": "vcenter", "align": "left"}
        box = {"border": 1, "border_color": "#BFBFBF"}
        tot = {"bold": True, "bg_color": LIGHT, "border": 1, "border_color": EDGE}
        self.f = f = lambda **k: self.wb.add_format({**base, **k})  # noqa: E731
        self.hdr = f(bold=True, bg_color=YELLOW, border=1, border_color=EDGE, align="center")
        self.sub = f(bold=True, bg_color=LIGHT, border=1, border_color=EDGE, align="center")
        self.title = f(bold=True, font_size=12, bg_color=TITLE, border=1, border_color=EDGE)
        self.txt, self.int, self.pct, self.mon = f(**box), f(num_format="#,##0", **box), f(num_format="0.0%", **box), f(num_format="mmm-yy", **box)
        self.ttxt, self.tint, self.tpct, self.tmon = f(**tot), f(num_format="#,##0", **tot), f(num_format="0.0%", **tot), f(num_format="mmm-yy", **tot)
        self.dash, self.tdash = f(**box), f(**tot)
        self.last = len(self.raw) + 1
        self.months = [pd.Timestamp(m) for m in sorted(self.raw["ORDER MONTH"].dropna().unique())]
        self.net = "nv" if rep.value else "nq"
        self.spec = self._spec()
        self._last_vals: list[dict] = []
        self._masks: dict = {}
        self._num = {}

    # ---------------------------------------------------------------- formulas with their values
    def rng(self, col: str) -> str:
        c = self.colname(self.r.raw_cols.index(col))
        return f"'RAW DATA'!${c}$2:${c}${self.last}"

    @staticmethod
    def lit(text) -> str:
        t = str(text).replace("~", "~~").replace("*", "~*").replace("?", "~?").replace('"', '""')
        return f'"{t}"'

    def crit_month(self, m: pd.Timestamp) -> tuple:
        return ("ORDER MONTH", str((m - EXCEL_DAY0).days), lambda d: d["ORDER MONTH"] == m)

    def crit_eq(self, col: str, val) -> tuple:
        return (col, self.lit(val), lambda d: d[col].astype(str) == str(val))

    def crit_status(self, st) -> list:
        if st is None:
            return []
        if isinstance(st, tuple):
            return [("FINAL STATUS", "{" + ",".join(self.lit(s) for s in st) + "}", lambda d: d["FINAL STATUS"].isin(st))]
        return [("FINAL STATUS", self.lit(st), lambda d: d["FINAL STATUS"] == st)]

    def sumifs(self, col: str, crit: list) -> tuple[str, float]:
        args, mask, array = [self.rng(col)], np.ones(len(self.raw), dtype=bool), False
        for c, x, fn in crit:
            args += [self.rng(c), x]
            if (c, x) not in self._masks:                     # a criterion is worked out once
                self._masks[(c, x)] = np.asarray(fn(self.raw), dtype=bool)
            mask &= self._masks[(c, x)]
            array |= x.startswith("{")
        if len(args) == 1:
            args += [self.rng("QTY"), '"<>"']
        fm = f"SUMIFS({','.join(args)})"
        if col not in self._num:
            self._num[col] = pd.to_numeric(self.raw[col], errors="coerce").fillna(0).to_numpy()
        val = float(self._num[col][mask].sum())
        return (f"=SUM({fm})" if array else f"={fm}"), val

    def base_cell(self, key: str, crit: list) -> tuple[str, float]:
        st, kind = self.BASE[key]
        col = {"QTY": "QTY", "VALUE": self.r.value, "SETTLE": self.r.settle}[kind]
        return self.sumifs(col, crit + self.crit_status(st))

    # ---------------------------------------------------------------- columns
    def _spec(self) -> list[tuple[str, str, str]]:
        v = self.r.value is not None
        s = [("SALE", "Gross Qty", "gq")] + ([("SALE", "Gross Value", "gv")] if v else [])
        s += [("CANCELLED", "Qty", "cq"), ("RTO", "Qty", "rq"), ("RTO", "% of Dispatched", "rp"),
              ("CUSTOMER RETURN", "Qty", "tq")] + ([("CUSTOMER RETURN", "Value", "tv")] if v else [])
        s += [("CUSTOMER RETURN", "% of Delivered", "tp")]
        if (self.raw["FINAL STATUS"] == "Return Type Pending").any():
            s += [("RETURN TYPE PENDING", "Qty", "pq")]
        s += [("NET SALE", "Qty", "nq")] + ([("NET SALE", "Value", "nv"), ("NET SALE", "ASP", "asp")] if v else [])
        return s + [("NET SALE", "MoM Growth %", "mom")]

    def spec_month(self) -> list:
        ly = [("LAST YEAR", "Net Value LY" if self.r.value else "Net Qty LY", "ly"), ("LAST YEAR", "YoY Growth %", "yoy")]
        return self.spec + (ly if len(self.months) > 12 else []) + self._pay()

    def _pay(self) -> list:
        return [("PAYMENT", "Net Received", "recv")] if self.r.settle else []

    # ---------------------------------------------------------------- one table
    def block(self, ws, r: int, first: str, title: str | None, rows: list, spec: list, share=None) -> tuple[int, int]:
        """rows: (label, how) - how = criteria list | ("rest", total criteria) = that total less the
        rows above | ("minus", total criteria, [(row, values)]) = that total less those rows (other
        blocks) | None = the sum of the rows above (the total row, last). share: (cell, value) or one
        per row. Returns (next free row, first data row)."""
        if title:
            ws.merge_range(r, 0, r, len(spec), title, self.title)
            r += 1
        ws.merge_range(r, 0, r + 1, 0, first, self.hdr)
        j = 0
        while j < len(spec):
            k = j
            while k + 1 < len(spec) and spec[k + 1][0] == spec[j][0]:
                k += 1
            if k > j:
                ws.merge_range(r, 1 + j, r, 1 + k, spec[j][0], self.hdr)
            else:
                ws.write(r, 1 + j, spec[j][0], self.hdr)
            j = k + 1
        for j, (_, sub, _) in enumerate(spec):
            ws.write(r + 1, 1 + j, sub, self.sub)
        r += 2
        top = r
        col = {key: 1 + j for j, (_, _, key) in enumerate(spec)}
        vals: list[dict] = []
        for n, (label, how) in enumerate(rows):
            last = n == len(rows) - 1
            if isinstance(label, pd.Timestamp):
                ws.write_datetime(r, 0, label.to_pydatetime(), self.tmon if last else self.mon)
            else:
                ws.write_string(r, 0, str(label), self.ttxt if last else self.txt)
            v, c = {}, {k: self.cell(r, i) for k, i in col.items()}
            for key in col:
                if key not in self.BASE:
                    continue
                if how is None:
                    fm, v[key] = f"=SUM({self.cell(top, col[key])}:{self.cell(r - 1, col[key])})", sum(x[key] for x in vals)
                elif isinstance(how, tuple) and how[0] == "rest":
                    fm0, v0 = self.base_cell(key, how[1])
                    fm, v[key] = f"{fm0}-SUM({self.cell(top, col[key])}:{self.cell(r - 1, col[key])})", v0 - sum(x[key] for x in vals)
                elif isinstance(how, tuple) and how[0] == "minus":
                    fm0, v0 = self.base_cell(key, how[1])
                    fm = fm0 + "".join(f"-{self.cell(o, col[key])}" for o, _ in how[2])
                    v[key] = v0 - sum(ov[key] for _, ov in how[2])
                else:
                    fm, v[key] = self.base_cell(key, how)
                ws.write_formula(r, col[key], fm, self.tint if last else self.int, v[key])
            pct, num = (self.tpct, self.tint) if last else (self.pct, self.int)
            if "rp" in col:
                d = v["gq"] - v["cq"]
                ws.write_formula(r, col["rp"], f'=IF({c["gq"]}-{c["cq"]}=0,"-",{c["rq"]}/({c["gq"]}-{c["cq"]}))', pct, v["rq"] / d if d else "-")
            if "tp" in col:
                d = v["nq"] + v["tq"]
                ws.write_formula(r, col["tp"], f'=IF({c["nq"]}+{c["tq"]}=0,"-",{c["tq"]}/({c["nq"]}+{c["tq"]}))', pct, v["tq"] / d if d else "-")
            if "asp" in col:
                ws.write_formula(r, col["asp"], f'=IF({c["nq"]}=0,"-",{c["nv"]}/{c["nq"]})', num, v["nv"] / v["nq"] if v["nq"] else "-")
            net = self.net
            if "mom" in col:
                if n == 0 or last or not isinstance(label, pd.Timestamp):
                    ws.write_string(r, col["mom"], "-", self.tdash if last else self.dash)
                else:
                    prev, pv = self.cell(r - 1, col[net]), vals[-1][net]
                    ws.write_formula(r, col["mom"], f'=IF({prev}=0,"-",{c[net]}/{prev}-1)', self.pct, v[net] / pv - 1 if pv else "-")
            if "ly" in col:
                if n >= 12 and not last:
                    ly = vals[n - 12][net]
                    ws.write_formula(r, col["ly"], f"={self.cell(r - 12, col[net])}", self.int, ly)
                    ws.write_formula(r, col["yoy"], f'=IF({c["ly"]}=0,"-",{c[net]}/{c["ly"]}-1)', self.pct, v[net] / ly - 1 if ly else "-")
                else:
                    ws.write_string(r, col["ly"], "-", self.tdash if last else self.dash)
                    ws.write_string(r, col["yoy"], "-", self.tdash if last else self.dash)
            if "share" in col and share:
                sc, sv = share[n] if isinstance(share, list) else share
                ws.write_formula(r, col["share"], f'=IF({sc}=0,"-",{c[net]}/{sc})', pct, v[net] / sv if sv else "-")
            vals.append(v)
            r += 1
        self._last_vals = vals
        return r, top

    def widths(self, ws, first: int, spec: list) -> None:
        ws.set_column(0, 0, first)
        for j, (_, sub, _) in enumerate(spec):
            ws.set_column(1 + j, 1 + j, max(len(sub) + 3, 12))

    def month_rows(self, extra: list) -> list:
        return [(m, extra + [self.crit_month(m)]) for m in self.months] + [("Total", None)]

    def month_net(self) -> list[tuple[str, float]]:
        """(MONTH WISE cell, value) of each month's net sale and of the total (the share columns)."""
        col = 1 + [k for _, _, k in self.spec_month()].index(self.net)
        measure = self.r.value or "QTY"
        dl = self.raw["FINAL STATUS"] == "Delivered"
        out = [(f"'MONTH WISE'!{self.cell(2 + i, col, True, True)}",
                float(self.raw.loc[dl & (self.raw["ORDER MONTH"] == m), measure].sum())) for i, m in enumerate(self.months)]
        out.append((f"'MONTH WISE'!{self.cell(2 + len(self.months), col, True, True)}", float(self.raw.loc[dl, measure].sum())))
        return out

    # ---------------------------------------------------------------- sheets
    def month_sheet(self) -> None:
        ws = self.wb.add_worksheet("MONTH WISE")
        spec = self.spec_month()
        self.block(ws, 0, "Month", None, self.month_rows([]), spec)
        self.widths(ws, 10, spec)
        ws.freeze_panes(2, 1)

    def group_sheet(self, name: str, cols: list[str]) -> None:
        ws = self.wb.add_worksheet(name)
        raw = self.raw
        key = raw[cols].astype(str).agg(" - ".join, axis=1)
        size = raw.groupby(key)["QTY"].sum()
        named = [g for g in raw.groupby(key)[self.r.value or "QTY"].sum().sort_values(ascending=False).index
                 if size[g] >= self.r.min_orders]
        parts = dict(zip(key, raw[cols].astype(str).itertuples(index=False, name=None)))
        if len(cols) > 1:                              # brand A to Z, then category A to Z
            named.sort(key=lambda g: tuple(x.lower() for x in parts[g]))
        others = bool((~key.isin(named)).any())

        def crit_of(g):
            return [self.crit_eq(c, x) for c, x in zip(cols, parts[g])]
        share = [("NET SALE", "Share in Net Sale %", "share")]
        spec_all = [s for s in self.spec if s[2] != "mom"] + share + self._pay()
        spec_month = self.spec + share + self._pay()
        label = " - ".join(c.title() for c in cols)
        total_row = 3 + len(named) + int(others)
        total_net = float(raw.loc[raw["FINAL STATUS"] == "Delivered", self.r.value or "QTY"].sum())
        share_all = (self.cell(total_row, 1 + [k for _, _, k in spec_all].index(self.net), True, True), total_net)
        rows = [(g, crit_of(g)) for g in named] + ([("Others", ("rest", []))] if others else []) + [("Total", None)]
        word = {"BRAND": "BRANDS", "CATEGORY": "CATEGORIES"}
        title = f"ALL {' - '.join(word.get(c, c) for c in cols)} - {self.months[0]:%b-%y} TO {self.months[-1]:%b-%y}".upper()
        r, _ = self.block(ws, 0, label, title, rows, spec_all, share=share_all)
        r += 2
        month_net, tops = self.month_net(), []
        for g in named:
            r, top = self.block(ws, r, "Month", f"{label.upper()}: {g}", self.month_rows(crit_of(g)), spec_month, share=month_net)
            tops.append((top, self._last_vals))
            r += 2
        if others:
            rows_o = [(m, ("minus", [self.crit_month(m)], [(t + i, vals[i]) for t, vals in tops]))
                      for i, m in enumerate(self.months)] + [("Total", None)]
            self.block(ws, r, "Month", f"{label.upper()}: Others", rows_o, spec_month, share=month_net)
        self.widths(ws, 40 if len(cols) > 1 else 24, spec_all)
        ws.freeze_panes(0, 1)

    def reasons_sheet(self) -> None:
        ws = self.wb.add_worksheet("REASONS")
        c0 = 0
        for label, status in self.r.reasons:
            fr = self.raw[self.raw["FINAL STATUS"] == status]
            t = fr.assign(R=fr["REASON"].replace("", np.nan).fillna("Not Given")).groupby("R")["QTY"].sum().sort_values(ascending=False)
            for j, h in enumerate([label, "Qty", "%"]):
                ws.write(0, c0 + j, h, self.hdr)
            end, total = len(t) + 1, float(t.sum())
            tot = self.cell(end, c0 + 1, True, True)
            for i, (rs, _) in enumerate(t.items(), start=1):
                crit = [("REASON", '"="', lambda d: d["REASON"].replace("", np.nan).isna())] if rs == "Not Given" \
                    else [self.crit_eq("REASON", rs)]
                fm, val = self.sumifs("QTY", crit + self.crit_status(status))
                ws.write_string(i, c0, str(rs), self.txt)
                ws.write_formula(i, c0 + 1, fm, self.int, val)
                ws.write_formula(i, c0 + 2, f'=IF({tot}=0,"-",{self.cell(i, c0 + 1)}/{tot})', self.pct, val / total if total else "-")
            ws.write_string(end, c0, "Total", self.ttxt)
            ws.write_formula(end, c0 + 1, f"=SUM({self.cell(1, c0 + 1)}:{self.cell(end - 1, c0 + 1)})", self.tint, total)
            ws.write_formula(end, c0 + 2, f"=SUM({self.cell(1, c0 + 2)}:{self.cell(end - 1, c0 + 2)})", self.tpct, 1.0 if total else 0)
            ws.set_column(c0, c0, 40)
            ws.set_column(c0 + 1, c0 + 2, 12)
            ws.set_column(c0 + 3, c0 + 3, 3)
            c0 += 4
        ws.freeze_panes(1, 0)

    def payment_sheet(self) -> None:
        if not self.r.settle:
            return
        ws = self.wb.add_worksheet("PAYMENT")
        cols = [("Net Qty", "nq")] + ([("Net Value", "nv")] if self.r.value else []) + \
               [("Settled Qty", "sq"), ("Pending Qty", "pq")] + ([("Pending Value", "pv")] if self.r.value else []) +                list(self.r.pay_table)
        hs = ["Order Month"] + [h for h, _ in cols] + (["Settlement %"] if self.r.value else [])
        ws.merge_range(0, 0, 0, len(hs) - 1, "PAYMENT AGAINST ORDERS PLACED IN EACH MONTH (BY ORDER MONTH)", self.title)
        for j, h in enumerate(hs):
            ws.write(1, j, h, self.hdr)
            ws.set_column(j, j, max(len(h) + 3, 12))
        settled = (self.r.settle, '"<>"', lambda d: d[self.r.settle].notna())
        first, totals = 2, {}
        for i, m in enumerate(self.months + ["Total"]):
            r, last = first + i, m == "Total"
            if last:
                ws.write_string(r, 0, "Total", self.ttxt)
            else:
                ws.write_datetime(r, 0, m.to_pydatetime(), self.mon)
            crit = [] if last else [self.crit_month(m)]
            v, cell = {}, {}
            for j, (h, key) in enumerate(cols, start=1):
                cell[key] = self.cell(r, j)
                if last:
                    fm, v[key] = f"=SUM({self.cell(first, j)}:{self.cell(r - 1, j)})", totals.get(key, 0.0)
                elif key == "nq":
                    fm, v[key] = self.sumifs("QTY", crit + self.crit_status("Delivered"))
                elif key == "nv":
                    fm, v[key] = self.sumifs(self.r.value, crit + self.crit_status("Delivered"))
                elif key == "sq":
                    fm, v[key] = self.sumifs("QTY", crit + self.crit_status("Delivered") + [settled])
                elif key == "pq":
                    fm, v[key] = f"={cell['nq']}-{cell['sq']}", v["nq"] - v["sq"]
                elif key == "pv":
                    sfm, sv = self.sumifs(self.r.value, crit + self.crit_status("Delivered") + [settled])
                    fm, v[key] = f"={cell['nv']}-{sfm[1:]}", v["nv"] - sv
                else:
                    fm, v[key] = self.sumifs(key, crit)
                if not last:
                    totals[key] = totals.get(key, 0.0) + v[key]
                ws.write_formula(r, j, fm, self.tint if last else self.int, v[key])
            if self.r.value:
                nk = self.r.settle
                ws.write_formula(r, len(hs) - 1, f'=IF({cell["nv"]}=0,"-",{cell[nk]}/{cell["nv"]})',
                                 self.tpct if last else self.pct, v[nk] / v["nv"] if v.get("nv") else "-")
        pm = self.r.pay_months
        if pm is not None and len(pm):
            r = first + len(self.months) + 3
            ws.merge_range(r, 0, r, max(len(hs), len(pm.columns) + 1) - 1, "PAYMENT RECEIVED IN BANK EACH MONTH (BY PAYMENT DATE)", self.title)
            for j, h in enumerate(["Payment Month"] + list(pm.columns)):
                ws.write(r + 1, j, h, self.hdr)
                ws.set_column(j, j, max(len(h) + 3, 12))
            pct_cols = [str(c).endswith("%") for c in pm.columns]
            for i, (m, row) in enumerate(pm.iterrows(), start=r + 2):
                ws.write_datetime(i, 0, pd.Timestamp(m).to_pydatetime(), self.mon)
                for j, x in enumerate(row.values, start=1):
                    if pct_cols[j - 1] and (x is None or pd.isna(x)):
                        ws.write_blank(i, j, None, self.pct)
                    else:
                        ws.write_number(i, j, float(x), self.pct if pct_cols[j - 1] else self.int)
            end = r + 2 + len(pm)
            ws.write_string(end, 0, "Total", self.ttxt)
            for j in range(1, len(pm.columns) + 1):
                if pct_cols[j - 1]:
                    ws.write_blank(end, j, None, self.tpct)
                else:
                    ws.write_formula(end, j, f"=SUM({self.cell(r + 2, j)}:{self.cell(end - 1, j)})", self.tint, float(pm.iloc[:, j - 1].sum()))
        ws.freeze_panes(0, 1)

    def input_log(self) -> None:
        ws = self.wb.add_worksheet("INPUT LOG")
        lg = self.r.input_log if self.r.input_log is not None else pd.DataFrame()
        day = self.f(num_format="dd-mmm-yy", border=1, border_color="#BFBFBF")
        for j, h in enumerate(lg.columns):
            ws.write(0, j, h, self.hdr)
        for i, row in enumerate(lg.itertuples(index=False), start=1):
            for j, v in enumerate(row):
                if isinstance(v, pd.Timestamp) and pd.notna(v):
                    ws.write_datetime(i, j, v.to_pydatetime(), day)
                elif isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and pd.notna(v):
                    ws.write_number(i, j, float(v), self.int)
                else:
                    ws.write_string(i, j, "" if v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)) else str(v), self.txt)
        for j, w in enumerate([30, 9, 62, 10, 24, 11, 11, 70][:len(lg.columns)]):
            ws.set_column(j, j, w)
        ws.freeze_panes(1, 0)

    def raw_sheet(self, ws) -> None:
        raw = self.raw
        rd, rm, rn, rt, rq = (self.f(num_format="dd-mmm-yy"), self.f(num_format="mmm-yy"), self.f(num_format="#,##0.00"),
                              self.f(), self.f(num_format="0"))
        kinds = []
        for j, c in enumerate(self.r.raw_cols):
            ws.write(0, j, c, self.hdr)
            w = len(c) + 3
            if "MONTH" in c:
                kinds.append(("d", rm))
                ws.set_column(j, j, max(w, 10))
            elif "DATE" in c:
                kinds.append(("d", rd))
                ws.set_column(j, j, max(w, 12))
            elif c in self.r.money_cols:
                kinds.append(("n", rn))
                ws.set_column(j, j, max(w, 12))
            elif c == "QTY":
                kinds.append(("n", rq))
                ws.set_column(j, j, 8)
            else:
                kinds.append(("s", rt))
                ws.set_column(j, j, max(w, 40 if c in ("REASON", "SUB STATUS", "PRODUCT TITLE") else 16))
        cols = [raw[c].to_numpy(dtype=object) for c in self.r.raw_cols]
        for i in range(len(raw)):
            for j, (k, f) in enumerate(kinds):
                v = cols[j][i]
                if v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and v in ("", "nan", "None", "NaT")):
                    continue
                if k == "d":
                    ws.write_datetime(i + 1, j, pd.Timestamp(v).to_pydatetime(), f)
                elif k == "n":
                    try:
                        ws.write_number(i + 1, j, float(v), f)
                    except (TypeError, ValueError):
                        ws.write_string(i + 1, j, str(v), rt)
                else:
                    ws.write_string(i + 1, j, str(v), rt)
        ws.freeze_panes(1, 4)
        ws.autofilter(0, 0, len(raw), len(self.r.raw_cols) - 1)

    def write(self) -> None:
        ws_raw = self.wb.add_worksheet("RAW DATA")          # first in the tab order, written last
        self.month_sheet()
        self.group_sheet("BRAND WISE", ["BRAND"])
        self.group_sheet("CATEGORY WISE", ["CATEGORY"])
        self.group_sheet("BRAND CATEGORY WISE", ["BRAND", "CATEGORY"])
        self.reasons_sheet()
        self.payment_sheet()
        self.input_log()
        self.raw_sheet(ws_raw)
        self.wb.close()


def build(rep: Report, out: Path) -> Path:
    missing = [c for c in STANDARD if c not in rep.raw_cols]
    if missing:
        raise ValueError(f"RAW DATA lacks {missing}")
    rep.raw = rep.raw.reset_index(drop=True)
    rep.raw["QTY"] = pd.to_numeric(rep.raw["QTY"], errors="coerce").fillna(0)
    rep.raw = rep.raw[rep.raw["ORDER MONTH"].notna()].reset_index(drop=True)
    Writer(rep, out).write()
    log.info("%s analysis: %d order lines -> %s (%.1f MB)", rep.portal, len(rep.raw), out.name, out.stat().st_size / 1e6)
    return out
