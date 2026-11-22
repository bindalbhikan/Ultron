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

Tables are Polars (docs/libraries/06-polars.md). Months are datetime.datetime (the 1st, midnight) everywhere.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl

log = logging.getLogger("bindal.business_report")

YELLOW, LIGHT, TITLE, EDGE = "#FFC000", "#FFE699", "#FFF2CC", "#BF8F00"
EXCEL_DAY0 = datetime(1899, 12, 30)
STANDARD = ["ORDER DATE", "ORDER MONTH", "BRAND", "CATEGORY", "QTY", "FINAL STATUS", "REASON"]
LOG_COLS = ["Input", "Account", "File", "Rows", "Date Used", "From", "To", "Note"]


@dataclass
class Report:
    portal: str
    raw: pl.DataFrame
    raw_cols: list[str]                       # RAW DATA columns in order (the standard ones included)
    value: str | None = None                  # sale value column
    settle: str | None = None                 # net settlement column (payment against the order line)
    money_cols: set[str] = field(default_factory=set)
    reasons: list[tuple[str, str]] = field(default_factory=lambda: [("Customer Return Reason", "Customer Return"),
                                                                      ("Cancellation Reason", "Cancelled")])
    pay_table: list[tuple[str, str]] = field(default_factory=list)   # PAYMENT (1): (header, RAW column), net last
    pay_months: pl.DataFrame | None = None    # PAYMENT (2): cash by payment month; first column = the month
    input_log: list[list] | None = None       # INPUT LOG rows (LOG_COLS)
    min_orders: int = 500
    unknown: dict[str, set] = field(default_factory=dict)   # BASE key -> months its number is not known: "-", never 0
    recv_all: bool = False                    # Net Received = the settlement of every line (a charge on an RTO is money too)
    pay_match: list[tuple[str, float]] = field(default_factory=list)   # PAYMENT: from the bank to the order lines, step by step
    earn_more: dict | None = None             # EARN MORE: order month -> the portal's month figures


def num(e: pl.Expr) -> pl.Expr:
    """A column as numbers for a sum: text that is no number, NaN and empty cells count 0 (pandas' to_numeric + fillna(0))."""
    return e.cast(pl.Float64, strict=False).fill_nan(None).fill_null(0.0)


def present(s: pl.Series) -> pl.Series:
    """pandas' notna(): not null and, for floats, not NaN."""
    out = s.is_not_null()
    return out & ~s.is_nan().fill_null(False) if s.dtype.is_float() else out


def one_spelling(s: pl.Series) -> pl.Series:
    """Values that differ only in letter case or spaces become their most common spelling (the first seen of equals):
    Excel's SUMIFS does not tell "Customer requested" from "customer requested"."""
    t = s.cast(pl.Utf8).fill_null("").str.strip_chars()
    df = pl.DataFrame({"t": t, "k": t.str.to_lowercase().str.replace_all(r"\s+", " ")}).with_row_index("i")
    best = (df.filter(pl.col("t") != "")
              .group_by("k", "t").agg(n=pl.len(), i=pl.col("i").min())
              .sort(["k", "n", "i"], descending=[False, True, False])
              .unique("k", keep="first").select("k", best="t"))
    return df.join(best, on="k", how="left", maintain_order="left").select(pl.coalesce("best", "t"))["best"].alias(s.name)


def add_months(m: datetime, n: int) -> datetime:
    y, mo = divmod(m.month - 1 + n, 12)
    return m.replace(year=m.year + y, month=mo + 1)


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
        self.r = rep
        rep.raw = rep.raw.with_columns(*[one_spelling(rep.raw[c]) for c in ["BRAND", "CATEGORY", "REASON"]])
        self.raw = rep.raw
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
        self.months = sorted(self.raw["ORDER MONTH"].drop_nulls().unique().to_list())
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

    def crit_month(self, m: datetime) -> tuple:
        return ("ORDER MONTH", str((m - EXCEL_DAY0).days), lambda d: d["ORDER MONTH"] == m)

    def crit_eq(self, col: str, val) -> tuple:
        return (col, self.lit(val), lambda d: d[col].cast(pl.Utf8).fill_null("nan") == str(val))

    def crit_status(self, st) -> list:
        if st is None:
            return []
        if isinstance(st, tuple):
            return [("FINAL STATUS", "{" + ",".join(self.lit(s) for s in st) + "}", lambda d: d["FINAL STATUS"].is_in(list(st)))]
        return [("FINAL STATUS", self.lit(st), lambda d: d["FINAL STATUS"] == st)]

    def sumifs(self, col: str, crit: list) -> tuple[str, float]:
        args, mask, array = [self.rng(col)], pl.repeat(True, len(self.raw), eager=True), False
        for c, x, fn in crit:
            args += [self.rng(c), x]
            if (c, x) not in self._masks:                     # a criterion is worked out once
                self._masks[(c, x)] = fn(self.raw).fill_null(False)
            mask = mask & self._masks[(c, x)]
            array |= x.startswith("{")
        if len(args) == 1:
            args += [self.rng("QTY"), '"<>"']
        fm = f"SUMIFS({','.join(args)})"
        if col not in self._num:
            self._num[col] = self.raw.select(num(pl.col(col)))[col]
        val = float(self._num[col].filter(mask).sum())
        return (f"=SUM({fm})" if array else f"={fm}"), val

    def base_cell(self, key: str, crit: list) -> tuple[str, float]:
        st, kind = self.BASE[key]
        if key == "recv" and self.r.recv_all:
            st = None
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
            if isinstance(label, datetime):
                ws.write_datetime(r, 0, label, self.tmon if last else self.mon)
            else:
                ws.write_string(r, 0, str(label), self.ttxt if last else self.txt)
            v, c = {}, {k: self.cell(r, i) for k, i in col.items()}
            for key in col:
                if key not in self.BASE:
                    continue
                if isinstance(label, datetime) and label in self.r.unknown.get(key, ()):
                    ws.write_string(r, col[key], "-", self.dash)      # not known: never a 0
                    v[key] = 0.0
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
                if isinstance(label, datetime) and label in self.r.unknown.get("rq", ()):
                    ws.write_string(r, col["rp"], "-", self.dash)
                else:
                    ws.write_formula(r, col["rp"], f'=IF({c["gq"]}-N({c["cq"]})=0,"-",N({c["rq"]})/({c["gq"]}-N({c["cq"]})))', pct, v["rq"] / d if d else "-")
            unknown_at = lambda *keys: isinstance(label, datetime) and any(label in self.r.unknown.get(k, ()) for k in keys)  # noqa: E731
            if "tp" in col and unknown_at("tq", "nq"):
                ws.write_string(r, col["tp"], "-", self.dash)
            elif "tp" in col:
                d = v["nq"] + v["tq"]
                ws.write_formula(r, col["tp"], f'=IF({c["nq"]}+{c["tq"]}=0,"-",{c["tq"]}/({c["nq"]}+{c["tq"]}))', pct, v["tq"] / d if d else "-")
            if "asp" in col and unknown_at("nq", "nv"):
                ws.write_string(r, col["asp"], "-", self.dash)
            elif "asp" in col:
                ws.write_formula(r, col["asp"], f'=IF(OR({c["nq"]}=0,N({c["nv"]})=0),"-",{c["nv"]}/{c["nq"]})', num, v["nv"] / v["nq"] if v["nq"] and v["nv"] else "-")
            net = self.net
            if "mom" in col:
                # the month before must be the row above: a month with no data is never skipped over
                before = rows[n - 1][0] if n else None
                none = self.r.unknown.get(net, ())
                if (n == 0 or last or not isinstance(label, datetime)
                        or before != add_months(label, -1) or label in none or before in none):
                    ws.write_string(r, col["mom"], "-", self.tdash if last else self.dash)
                else:
                    prev, pv = self.cell(r - 1, col[net]), vals[-1][net]
                    ws.write_formula(r, col["mom"], f'=IF({prev}=0,"-",{c[net]}/{prev}-1)', self.pct, v[net] / pv - 1 if pv else "-")
            if "ly" in col:
                # the same month last year, found by its date: a month with no data must not shift the rest
                year_ago = next((i for i in range(n) if isinstance(label, datetime)
                                 and rows[i][0] == add_months(label, -12)), None)
                if year_ago is not None and not last and label not in self.r.unknown.get(net, ()) and rows[year_ago][0] not in self.r.unknown.get(net, ()):
                    ly = vals[year_ago][net]
                    ws.write_formula(r, col["ly"], f"={self.cell(top + year_ago, col[net])}", self.int, ly)
                    ws.write_formula(r, col["yoy"], f'=IF({c["ly"]}=0,"-",{c[net]}/{c["ly"]}-1)', self.pct, v[net] / ly - 1 if ly else "-")
                else:
                    ws.write_string(r, col["ly"], "-", self.tdash if last else self.dash)
                    ws.write_string(r, col["yoy"], "-", self.tdash if last else self.dash)
            if "share" in col and share:
                sc, sv = share[n] if isinstance(share, list) else share
                if label in self.r.unknown.get(net, ()):     # the month's net is "-": a formula on it would show #VALUE!
                    ws.write_string(r, col["share"], "-", self.tdash if last else self.dash)
                else:
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
        dl = self.raw.filter(pl.col("FINAL STATUS") == "Delivered").select("ORDER MONTH", v=num(pl.col(measure)))
        by_month = dict(dl.group_by("ORDER MONTH").agg(pl.col("v").sum()).iter_rows())
        out = [(f"'MONTH WISE'!{self.cell(2 + i, col, True, True)}", float(by_month.get(m, 0.0))) for i, m in enumerate(self.months)]
        out.append((f"'MONTH WISE'!{self.cell(2 + len(self.months), col, True, True)}", float(dl["v"].sum())))
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
        text = [pl.col(c).cast(pl.Utf8).fill_null("nan") for c in cols]
        g = (raw.select(pl.concat_str(text, separator=" - ").alias("_k"), *[t.alias(f"_p{i}") for i, t in enumerate(text)],
                        num(pl.col("QTY")).alias("_q"), num(pl.col(self.r.value or "QTY")).alias("_v"))
                .group_by("_k").agg(pl.col("_q").sum(), pl.col("_v").sum(), *[pl.col(f"_p{i}").first() for i in range(len(cols))])
                .sort("_k").sort("_v", descending=True, maintain_order=True))     # by value, equal values A to Z
        named = [k for k, q in zip(g["_k"], g["_q"]) if q >= self.r.min_orders]
        parts = {row[0]: tuple(row[1:]) for row in g.select("_k", *[f"_p{i}" for i in range(len(cols))]).iter_rows()}
        if len(cols) > 1:                              # brand A to Z, then category A to Z
            named.sort(key=lambda k: tuple(x.lower() for x in parts[k]))
        others = len(named) < g.height

        def crit_of(g):
            return [self.crit_eq(c, x) for c, x in zip(cols, parts[g])]
        share = [("NET SALE", "Share in Net Sale %", "share")]
        spec_all = [s for s in self.spec if s[2] != "mom"] + share + self._pay()
        spec_month = self.spec + share + self._pay()
        label = " - ".join(c.title() for c in cols)
        total_row = 3 + len(named) + int(others)
        total_net = float(raw.filter(pl.col("FINAL STATUS") == "Delivered").select(num(pl.col(self.r.value or "QTY")).sum()).item())
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
            reason = pl.when(pl.col("REASON").is_null() | (pl.col("REASON") == "")).then(pl.lit("Not Given")).otherwise(pl.col("REASON"))
            t = (self.raw.filter(pl.col("FINAL STATUS") == status).group_by(R=reason).agg(q=num(pl.col("QTY")).sum())
                     .sort("R").sort("q", descending=True, maintain_order=True))      # by qty, equal qty A to Z
            for j, h in enumerate([label, "Qty", "%"]):
                ws.write(0, c0 + j, h, self.hdr)
            end, total = t.height + 1, float(t["q"].sum())
            tot = self.cell(end, c0 + 1, True, True)
            for i, rs in enumerate(t["R"].to_list(), start=1):
                crit = [("REASON", '"="', lambda d: d["REASON"].is_null() | (d["REASON"] == ""))] if rs == "Not Given" \
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
        settled = (self.r.settle, '"<>"', lambda d: present(d[self.r.settle]))
        first, totals = 2, {}
        for i, m in enumerate(self.months + ["Total"]):
            r, last = first + i, m == "Total"
            if last:
                ws.write_string(r, 0, "Total", self.ttxt)
            else:
                ws.write_datetime(r, 0, m, self.mon)
            crit = [] if last else [self.crit_month(m)]
            v, cell = {}, {}
            for j, (_h, key) in enumerate(cols, start=1):
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
        if pm is not None and pm.height:
            names = pm.columns[1:]                                   # the first column is the payment month
            r = first + len(self.months) + 3
            ws.merge_range(r, 0, r, max(len(hs), len(names) + 1) - 1, "PAYMENT RECEIVED IN BANK EACH MONTH (BY PAYMENT DATE)", self.title)
            for j, h in enumerate(["Payment Month"] + list(names)):
                ws.write(r + 1, j, h, self.hdr)
                ws.set_column(j, j, max(len(h) + 3, 12))
            pct_cols = [str(c).endswith("%") for c in names]
            for i, row in enumerate(pm.iter_rows(), start=r + 2):
                ws.write_datetime(i, 0, row[0], self.mon)
                for j, x in enumerate(row[1:], start=1):
                    if x is None or x != x:
                        ws.write_blank(i, j, None, self.pct if pct_cols[j - 1] else self.int)
                    else:
                        ws.write_number(i, j, float(x), self.pct if pct_cols[j - 1] else self.int)
            end = r + 2 + pm.height
            ws.write_string(end, 0, "Total", self.ttxt)
            for j in range(1, len(names) + 1):
                if pct_cols[j - 1]:
                    ws.write_blank(end, j, None, self.tpct)
                else:
                    total = float(pm.select(pl.col(names[j - 1]).cast(pl.Float64).fill_nan(None).sum()).item() or 0.0)
                    ws.write_formula(end, j, f"=SUM({self.cell(r + 2, j)}:{self.cell(end - 1, j)})", self.tint, total)
            if self.r.pay_match:
                r = end + 3
                ws.merge_range(r, 0, r, 4, "PAYMENT MATCH: FROM THE BANK TO THE ORDER LINES", self.title)
                for i, (label, value) in enumerate(self.r.pay_match, start=r + 1):
                    total = label.startswith("=")
                    ws.merge_range(i, 0, i, 3, "", self.ttxt if total else self.txt)
                    ws.write_string(i, 0, label, self.ttxt if total else self.txt)   # a label may start with =
                    ws.write_number(i, 4, float(value), self.tint if total else self.int)
        ws.freeze_panes(0, 1)

    def input_log(self) -> None:
        ws = self.wb.add_worksheet("INPUT LOG")
        rows = self.r.input_log or []
        heads = LOG_COLS if self.r.input_log is not None else []
        day = self.f(num_format="dd-mmm-yy", border=1, border_color="#BFBFBF")
        for j, h in enumerate(heads):
            ws.write(0, j, h, self.hdr)
        for i, row in enumerate(rows, start=1):
            for j, v in enumerate(row):
                if isinstance(v, datetime):
                    ws.write_datetime(i, j, v, day)
                elif isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
                    ws.write_number(i, j, float(v), self.int)
                else:
                    ws.write_string(i, j, "" if v is None or (isinstance(v, float) and v != v) else str(v), self.txt)
        for j, w in enumerate([30, 9, 62, 10, 24, 11, 11, 70][:len(heads)]):
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
        cols = [raw[c].to_list() if c in raw.columns else [None] * raw.height for c in self.r.raw_cols]
        for i in range(raw.height):
            for j, (k, f) in enumerate(kinds):
                v = cols[j][i]
                if v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and v in ("", "nan", "None", "NaT")):
                    continue
                if k == "d":
                    if not isinstance(v, datetime):           # a date the report gave as text (ISO)
                        try:
                            v = datetime.fromisoformat(str(v).strip()[:19])
                        except ValueError:
                            ws.write_string(i + 1, j, str(v), rt)
                            continue
                    ws.write_datetime(i + 1, j, v, f)
                elif k == "n":
                    try:
                        ws.write_number(i + 1, j, float(v), f)
                    except (TypeError, ValueError):
                        ws.write_string(i + 1, j, str(v), rt)
                else:
                    ws.write_string(i + 1, j, str(v), rt)
        ws.freeze_panes(1, 4)
        ws.autofilter(0, 0, len(raw), len(self.r.raw_cols) - 1)

    def earn_sheet(self) -> None:
        """EARN MORE: the portal's own month figures, as its screen shows them, beside the units of RAW DATA. A month it has
        no data for shows -, never 0."""
        data = self.r.earn_more
        ws = self.wb.add_worksheet("EARN MORE")
        groups = [("Gross Units & Sales", 2), ("Cancellations (RTO included)", 2), ("Returns", 2), ("Net Units & Sales", 2), ("Gross ASP", 1), ("RAW DATA", 2)]
        subs = ["Units", "Sales", "Units", "Amount", "Units", "Amount", "Units", "Sales", "Rs", "Gross Qty", "Earn More less RAW DATA"]
        ws.merge_range(0, 0, 0, len(subs), f"{self.r.portal} EARN MORE, BY ORDER MONTH (figures of the portal's Earn More screen)", self.title)
        ws.merge_range(1, 0, 2, 0, "Month", self.hdr)
        col = 1
        for name, width in groups:
            if width > 1:
                ws.merge_range(1, col, 1, col + width - 1, name, self.hdr)
            else:
                ws.write(1, col, name, self.hdr)
            col += width
        for j, name in enumerate(subs, start=1):
            ws.write(2, j, name, self.sub)
        keys = ["gross_units", "gross_amount", "cancellation_units", "cancellation_amount", "return_units", "return_amount"]
        total = dict.fromkeys(keys, 0.0)
        total_qty = 0.0
        qty_of = dict(self.raw.group_by("ORDER MONTH").agg(num(pl.col("QTY")).sum()).iter_rows())
        for i, month in enumerate(self.months, start=3):
            ws.write_datetime(i, 0, month, self.mon)
            qty = float(qty_of.get(month, 0.0))
            ws.write_number(i, 10, qty, self.int)
            if month not in data:
                for j in [*range(1, 10), 11]:
                    ws.write_string(i, j, "-", self.dash)
                continue
            row = data[month]
            total_qty += qty
            for j, k in enumerate(keys, start=1):
                ws.write_number(i, j, float(row[k]), self.int)
                total[k] += float(row[k])
            b, c, e, g = (self.cell(i, n) for n in (1, 3, 5, 2))
            ws.write_formula(i, 7, f"={b}-{c}-{e}", self.int, float(row["gross_units"] - row["cancellation_units"] - row["return_units"]))
            ws.write_formula(i, 8, f"={g}-{self.cell(i, 4)}-{self.cell(i, 6)}", self.int, float(row["gross_amount"] - row["cancellation_amount"] - row["return_amount"]))
            ws.write_formula(i, 9, f"=IFERROR({g}/{b},0)", self.int, float(row["gross_amount"] / row["gross_units"]) if row["gross_units"] else 0.0)
            ws.write_formula(i, 11, f"={b}-{self.cell(i, 10)}", self.int, float(row["gross_units"]) - qty)
        r = 3 + len(self.months)
        ws.write_string(r, 0, "Total of the months with figures", self.ttxt)
        for j, k in enumerate(keys, start=1):
            ws.write_number(r, j, total[k], self.tint)
        ws.write_number(r, 7, total["gross_units"] - total["cancellation_units"] - total["return_units"], self.tint)
        ws.write_number(r, 8, total["gross_amount"] - total["cancellation_amount"] - total["return_amount"], self.tint)
        ws.write_number(r, 9, total["gross_amount"] / total["gross_units"] if total["gross_units"] else 0, self.tint)
        ws.write_number(r, 10, total_qty, self.tint)
        ws.write_number(r, 11, total["gross_units"] - total_qty, self.tint)
        ws.set_column(0, 0, 30)
        ws.set_column(1, 11, 12)
        ws.set_column(11, 11, 22)
        ws.freeze_panes(3, 1)
        ws.activate()

    def write(self) -> None:
        ws_raw = self.wb.add_worksheet("RAW DATA")          # first in the tab order, written last
        if self.r.earn_more is not None and len(self.r.earn_more):
            self.earn_sheet()
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
    rep.raw = rep.raw.with_columns(num(pl.col("QTY")).alias("QTY")).filter(pl.col("ORDER MONTH").is_not_null())
    Writer(rep, out).write()
    log.info("%s analysis: %d order lines -> %s (%.1f MB)", rep.portal, rep.raw.height, out.name, out.stat().st_size / 1e6)
    return out
