# Superseded (1 Nov 2026) by src/ultron/workings/business_report (myntra.py + workbook.py): the
# owner's hand-run Myntra build script, kept unchanged for reference.
"""Myntra sale / return analysis (all three accounts treated as one portal).

Reads the parquet copies of the order, return, master and payment reports and writes
one Excel workbook: RAW DATA plus the analysis sheets.
"""
import sys
import numpy as np
import pandas as pd

S = sys.argv[1]
OUT = sys.argv[2]
PQ = S + "/pq/"


def dt(s):
    d = pd.to_datetime(s, errors="coerce", format="mixed")
    return d.where(d > "2000-01-01")


def num(s):
    return pd.to_numeric(s, errors="coerce")


# ------------------------------------------------------------------ inputs
o = pd.read_parquet(PQ + "orders.parquet")
r = pd.read_parquet(PQ + "returns.parquet")
m = pd.read_parquet(PQ + "master.parquet")
o = o.drop_duplicates("order line id")

# master: MY SKU / FINAL SKU, keyed on the Myntra SKU code, falling back to the seller SKU
mcols = ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]
mm = m[m["Channel Name"].str.startswith("MYNTRA", na=False)]
by_code = mm.dropna(subset=["MYNTRA SKU CODE"]).drop_duplicates("MYNTRA SKU CODE").set_index("MYNTRA SKU CODE")[mcols]
by_sku = m.drop_duplicates("Channel Listing SKU Code").set_index("Channel Listing SKU Code")[mcols]

# returns: the Apr-25..Sep-26 report, then the bot's Oct-26 month report and its daily reports, so
# returns raised in October on September orders are counted. The newest line of an order line wins.
import glob  # noqa: E402
from pathlib import Path  # noqa: E402

AW = "G:/My Drive/BINDAL EXPORTS/AGENT WORK/"
r["SOURCE"] = "MYNTRA RETURNS ALL ACCOUNTS APR-25 TO SEP-26.xlsx"
extra = []
for f in (sorted(glob.glob("G:/My Drive/MYNTRA ANALYSIS/Input/OCT-26 RETURNS/*.csv"))
          + sorted(glob.glob(AW + "MYNTRA/MYNTRA DAILY REPORTS/*/* Returns *.csv"))):
    x = pd.read_csv(f, dtype=str)
    x.insert(0, "ACCOUNT", Path(f).name.split()[0])
    x["SOURCE"] = Path(f).name
    extra.append(x)
r = pd.concat([r] + extra, ignore_index=True)
for c in ["order_line_id", "exchange_id", "return_id", "order_id"]:
    r[c] = r[c].str.replace(r"\.0$", "", regex=True)
r["EVENT DATE"] = dt(r["return_created_date"]).fillna(dt(r["order_rto_date"]))
r = r.drop_duplicates("order_line_id", keep="last").reset_index(drop=True)

# one row per order line
r["is_exchange"] = r["exchange_id"].notna()
ret = r.set_index("order_line_id")
exchange_release_ids = set(r["exchange_id"].dropna())

# ------------------------------------------------------------------ payments
pcols = ["Payment_Date", "utrNumber", "Order_Type", "order_line_id", "return_id", "Seller_Id",
         "Settled_Amount", "Commission", "Logistics_Commission", "TDS", "IGST_TCS", "CGST_TCS",
         "SGST_TCS", "NOD_Comment"]
PAY_FILES = {"MAIN_x": "SPF/MYNTRA/input/MAIN/payment.xlsx", "DBCC_x": "SPF/MYNTRA/input/DBCC/Payment.xlsx",
             "FMCC_x": "SPF/MYNTRA/input/FMCC/Payment.xlsx"}
for i, f in enumerate(sorted(glob.glob("G:/My Drive/BINDAL EXPORTS/SPF/MYNTRA/payment/*.csv"))):
    PAY_FILES[f"csv{i}"] = "SPF/MYNTRA/payment/" + Path(f).name
# payments downloaded live from the portal by the Ultron bot (scripts/myntra/myntra_payments.py)
for i, f in enumerate(sorted(glob.glob("G:/My Drive/MYNTRA ANALYSIS/Input/PAYMENTS AUG-OCT-26/*.csv"))):
    PAY_FILES[f"live{i}"] = "MYNTRA ANALYSIS/Input/PAYMENTS AUG-OCT-26/" + Path(f).name
pay_keys = list(PAY_FILES)
p = pd.concat([pd.read_parquet(PQ + f"pay_{k}.parquet", columns=pcols).assign(SRC=PAY_FILES[k]) for k in pay_keys],
              ignore_index=True)
p["Payment_Date"] = dt(p["Payment_Date"]).dt.normalize()
acc_of = {"19170": "MAIN", "32207": "DBCC", "35426": "FMCC"}
pay_log = p.assign(ACCOUNT=p["Seller_Id"].map(acc_of)).groupby(["ACCOUNT", "SRC"]).agg(
    Rows=("Payment_Date", "size"), From=("Payment_Date", "min"), To=("Payment_Date", "max")).reset_index()
for c in ["Settled_Amount", "Commission", "Logistics_Commission", "TDS", "IGST_TCS", "CGST_TCS", "SGST_TCS"]:
    p[c] = num(p[c]).fillna(0).round(2)
p["Order_Type"] = p["Order_Type"].str.strip().str.title()
p["order_line_id"] = p["order_line_id"].str.replace(r"\.0$", "", regex=True)
# the xlsx dumps and the newer csv exports overlap: keep each payout line once
p = p.drop_duplicates(["Payment_Date", "utrNumber", "Order_Type", "order_line_id", "return_id", "Settled_Amount"])
p["TAX"] = p["TDS"] + p["IGST_TCS"] + p["CGST_TCS"] + p["SGST_TCS"]
p["ACCOUNT"] = p["Seller_Id"].map({"19170": "MAIN", "32207": "DBCC", "35426": "FMCC"})

fwd = p[p.Order_Type == "Forward"].groupby("order_line_id").agg(
    FWD_SETTLED=("Settled_Amount", "sum"), FWD_DATE=("Payment_Date", "max"), UTR=("utrNumber", "last"),
    COMMISSION=("Commission", "sum"), FWD_LOGISTICS=("Logistics_Commission", "sum"), TAX=("TAX", "sum"))
rev = p[p.Order_Type == "Reverse"].groupby("order_line_id").agg(
    REV_SETTLED=("Settled_Amount", "sum"), REV_DATE=("Payment_Date", "max"),
    REV_LOGISTICS=("Logistics_Commission", "sum"))
nod = p[p.Order_Type == "Nod"].groupby("order_line_id").agg(NOD=("Settled_Amount", "sum"))

# ------------------------------------------------------------------ raw data
d = pd.DataFrame({
    "ACCOUNT": o["ACCOUNT"],
    "ORDER DATE": dt(o["created on"]).dt.normalize(),
    "STORE ORDER ID": o["store order id"].str.lstrip("'"),
    "ORDER RELEASE ID": o["order release id"],
    "ORDER LINE ID": o["order line id"],
    "SELLER ORDER ID": o["seller order id"],
    "STYLE ID": o["style id"],
    "MYNTRA SKU CODE": o["myntra sku code"],
    "SELLER SKU CODE": o["seller sku code"],
})
d["ORDER MONTH"] = d["ORDER DATE"].dt.to_period("M").dt.to_timestamp()
for c in mcols:
    d[c] = d["MYNTRA SKU CODE"].map(by_code[c]).fillna(d["SELLER SKU CODE"].map(by_sku[c]))
d["BRAND"] = o["brand"].values
d["CATEGORY"] = o["article type"].values
d["SIZE"] = o["size"].values
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
# an exchange is counted as a customer return (one status, no separate exchange numbers)
final = np.select(
    [rtype.eq("Return"), st == "F", rtype.eq("RTO") | (st == "RTO"), st == "C"],
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
d["RTO DATE"] = dt(o["rto creation date"]).fillna(dt(oli.map(ret["order_rto_date"]))).dt.normalize().values
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
d = d.rename(columns={"FWD_SETTLED": "FWD SETTLED AMT", "FWD_DATE": "FWD PAYMENT DATE", "UTR": "FWD UTR",
                      "COMMISSION": "COMMISSION", "FWD_LOGISTICS": "FWD LOGISTICS", "TAX": "TCS + TDS",
                      "REV_SETTLED": "REVERSE SETTLED AMT", "REV_DATE": "REVERSE PAYMENT DATE",
                      "REV_LOGISTICS": "RETURN LOGISTICS FEE", "NOD": "SPF / NOD AMT"})
money = ["FWD SETTLED AMT", "REVERSE SETTLED AMT", "SPF / NOD AMT"]
d["NET SETTLEMENT"] = d[money].fillna(0).sum(axis=1).where(d[money].notna().any(axis=1))
hf, hr = d["FWD SETTLED AMT"].notna(), d["REVERSE SETTLED AMT"].notna()
fs = d["FINAL STATUS"]
d["PAYMENT STATUS"] = np.select(
    [hf & hr, hf & fs.eq("Customer Return"), hf, hr,
     fs.eq("Delivered"), fs.eq("Customer Return")],
    ["Settled & Reversed", "Settled - Reverse Pending", "Settled", "Reverse Only",
     "Payment Pending", "No Payment (Returned)"], default="Not Applicable")

d = d.sort_values(["ORDER DATE", "ACCOUNT"]).reset_index(drop=True)

# gross = every order line (exchange replacement orders included; RAW DATA flags them)
a = d.copy()
V = "SALE PRICE (FINAL AMOUNT)"


# ------------------------------------------------------------------ metrics
def metrics(g):
    def q(s):
        return (g["FINAL STATUS"] == s).sum()

    def v(s):
        return g.loc[g["FINAL STATUS"] == s, V].sum()
    gross_q, gross_v = len(g), g[V].sum()
    canc_q, rto_q, cr_q, del_q, it_q = (q(s) for s in
                                        ["Cancelled", "RTO", "Customer Return", "Delivered", "In Transit"])
    disp = gross_q - canc_q
    reached = del_q + cr_q
    net_q = del_q
    net_v = v("Delivered")
    sett = g.loc[g["FINAL STATUS"].isin(["Delivered", "Customer Return"]), "NET SETTLEMENT"].sum()
    return pd.Series({
        "Gross Orders": gross_q, "Gross Sale Value": gross_v,
        "Cancelled": canc_q, "Cancelled Value": v("Cancelled"), "Cancel %": canc_q / gross_q if gross_q else np.nan,
        "Dispatched": disp,
        "RTO": rto_q, "RTO Value": v("RTO"), "RTO % (of Dispatched)": rto_q / disp if disp else np.nan,
        "Delivered to Customer": reached,
        "Customer Return": cr_q, "Customer Return Value": v("Customer Return"),
        "Return % (of Delivered)": cr_q / reached if reached else np.nan,
        "In Transit": it_q,
        "Net Sale Qty": net_q, "Net Sale Value": net_v,
        "Net Sale % (of Gross)": net_q / gross_q if gross_q else np.nan,
        "ASP (Net)": net_v / net_q if net_q else np.nan,
        "Net Settlement Received": sett,
        "Settlement % of Net Sale Value": sett / net_v if net_v else np.nan,
    })


def by(col, frame=a):
    t = frame.groupby(col).apply(metrics, include_groups=False)
    return t


month = by("ORDER MONTH")
month.insert(2, "MoM Gross Value %", month["Gross Sale Value"].pct_change())
month.insert(month.columns.get_loc("Net Sale Value") + 1, "MoM Net Value %", month["Net Sale Value"].pct_change())
month.insert(month.columns.get_loc("Net Sale Qty") + 1, "MoM Net Qty %", month["Net Sale Qty"].pct_change())
total = metrics(a)
total_row = total.copy()



# reasons
def reason_table(status, frame=a, top=None):
    s = frame.loc[frame["FINAL STATUS"] == status, "REASON"].fillna("Not Given")
    t = s.value_counts().rename("Qty").to_frame()
    t["Share %"] = t["Qty"] / t["Qty"].sum()
    return t.head(top) if top else t


cr_reason = reason_table("Customer Return")
cn_reason = reason_table("Cancelled")

# payments by month paid (cash view)
pp = p[p["Payment_Date"] >= "2025-04-01"].copy()
pp["PAY MONTH"] = pp["Payment_Date"].dt.to_period("M").dt.to_timestamp()
paym = pp.pivot_table(index="PAY MONTH", columns="Order_Type", values="Settled_Amount", aggfunc="sum", fill_value=0)
paym = paym.reindex(columns=["Forward", "Reverse", "Nod"], fill_value=0).rename(
    columns={"Forward": "Forward Settled (Sale)", "Reverse": "Reverse Debit (Return/RTO)", "Nod": "SPF / NOD"})
paym["Net Payout"] = paym.sum(axis=1)
paym["Forward Lines"] = pp[pp.Order_Type == "Forward"].groupby("PAY MONTH").size()
paym["Reverse Lines"] = pp[pp.Order_Type == "Reverse"].groupby("PAY MONTH").size()
paym["Commission"] = pp[pp.Order_Type == "Forward"].groupby("PAY MONTH")["Commission"].sum()
paym["Forward Logistics"] = pp[pp.Order_Type == "Forward"].groupby("PAY MONTH")["Logistics_Commission"].sum()
paym["Return Logistics Fee"] = pp[pp.Order_Type == "Reverse"].groupby("PAY MONTH")["Logistics_Commission"].sum()
paym["TCS + TDS"] = pp[pp.Order_Type == "Forward"].groupby("PAY MONTH")["TAX"].sum()
paym["MoM Net Payout %"] = paym["Net Payout"].pct_change()
paym = paym.fillna(0)

# payment reconciliation by order month
def recon(g):
    dl = g[g["FINAL STATUS"] == "Delivered"]
    rt = g[g["FINAL STATUS"].isin(["Customer Return"])]
    return pd.Series({
        "Net Sale Qty": len(dl), "Net Sale Value": dl[V].sum(),
        "Settled Qty": dl["FWD SETTLED AMT"].notna().sum(),
        "Pending Qty": dl["FWD SETTLED AMT"].isna().sum(),
        "Pending Sale Value": dl.loc[dl["FWD SETTLED AMT"].isna(), V].sum(),
        "Forward Settled": g["FWD SETTLED AMT"].sum(),
        "Reverse Debit": g["REVERSE SETTLED AMT"].sum(),
        "SPF / NOD": g["SPF / NOD AMT"].sum(),
        "Net Settlement": g["NET SETTLEMENT"].sum(),
        "Commission": g["COMMISSION"].sum(),
        "Forward Logistics": g["FWD LOGISTICS"].sum(),
        "Return Logistics Fee": g["RETURN LOGISTICS FEE"].sum(),
        "TCS + TDS": g["TCS + TDS"].sum(),
        "Returns Not Yet Debited": (rt["REVERSE SETTLED AMT"].isna() & rt["FWD SETTLED AMT"].notna()).sum(),
        "Settlement % of Net Sale": g["NET SETTLEMENT"].sum() / dl[V].sum() if len(dl) else np.nan,
    })


rec = a.groupby("ORDER MONTH").apply(recon, include_groups=False)

# ------------------------------------------------------------------ input log
ACC_ORDER = {"MAIN": 0, "DBCC": 1, "FMCC": 2}
log_rows = []
od = dt(o["created on"])
for acc, g in o.groupby("ACCOUNT"):
    gd = od[g.index]
    log_rows.append(["Orders", acc, "MYNTRA ORDERS ALL ACCOUNTS APR-25 TO SEP-26.xlsx", len(g), "Order date",
                     gd.min(), gd.max()])
raw_r = pd.concat([pd.read_parquet(PQ + "returns.parquet").assign(SOURCE=r["SOURCE"].iloc[0])] + extra,
                  ignore_index=True)
raw_r["EVENT DATE"] = dt(raw_r["return_created_date"]).fillna(dt(raw_r["order_rto_date"]))
raw_r["GROUP"] = np.where(raw_r["SOURCE"].str.contains(" Returns 2026-"), "Daily returns reports (bot, Drive AGENT WORK)",
                          np.where(raw_r["SOURCE"].str.contains("RETURNS 2026-10-01"), "Returns report 01-Oct-26 to 26-Oct-26 (portal job history)",
                                   raw_r["SOURCE"]))
for (acc, src), g in raw_r.groupby(["ACCOUNT", "GROUP"]):
    log_rows.append(["Returns", acc, src, len(g), "Return / RTO created date", g["EVENT DATE"].min(),
                     g["EVENT DATE"].max()])
for acc, g in r.groupby("ACCOUNT"):
    log_rows.append(["Returns used (merged, one row per order line)", acc, "All return files above", len(g),
                     "Return / RTO created date", g["EVENT DATE"].min(), g["EVENT DATE"].max()])
for _, x in pay_log.iterrows():
    log_rows.append(["Payment", x["ACCOUNT"], x["SRC"], x["Rows"], "Payment date", x["From"], x["To"]])
for acc, g in p.groupby("ACCOUNT"):
    log_rows.append(["Payment used (duplicates removed)", acc, "All payment files above", len(g), "Payment date",
                     g["Payment_Date"].min(), g["Payment_Date"].max()])
log_rows.append(["SKU master", "ALL", "MasterSheet.xlsx (sheet Master)", len(m), "-", pd.NaT, pd.NaT])
input_log = pd.DataFrame(log_rows, columns=["Input", "Account", "File", "Rows", "Date Used", "From", "To"])
kind_order = {"Orders": 0, "Returns": 1, "Returns used (merged, one row per order line)": 2, "Payment": 3,
              "Payment used (duplicates removed)": 4, "SKU master": 5}
input_log = input_log.assign(k=input_log["Input"].map(kind_order), a=input_log["Account"].map(ACC_ORDER).fillna(9))     .sort_values(["k", "a", "From"]).drop(columns=["k", "a"])

# ------------------------------------------------------------------ workbook
import xlsxwriter  # noqa: E402

wb = xlsxwriter.Workbook(OUT, {"nan_inf_to_errors": True})
base = {"font_name": "Calibri", "font_size": 10, "font_color": "#000000", "valign": "vcenter", "align": "left"}
box = {"border": 1, "border_color": "#BFBFBF"}
fmt = lambda **k: wb.add_format({**base, **k})  # noqa: E731
hdr = fmt(bold=True, bg_color="#FFC000", border=1, border_color="#BF8F00", align="center")
f_txt = fmt(align="left", **box)
f_int = fmt(num_format="#,##0", **box)
f_pct = fmt(num_format="0.0%", **box)
f_mon = fmt(num_format="mmm-yy", align="left", **box)
tot = {"bold": True, "bg_color": "#FFE699", "border": 1, "border_color": "#BF8F00"}
t_txt = fmt(align="left", **tot)
f_dash = fmt(**box)
t_dash = fmt(**tot)
t_int = fmt(num_format="#,##0", **tot)
t_pct = fmt(num_format="0.0%", **tot)


def put(ws, r, c, v, f):
    if v is None or v is pd.NaT or (isinstance(v, float) and not np.isfinite(v)):
        ws.write_blank(r, c, None, f)
    elif isinstance(v, pd.Timestamp):
        ws.write_datetime(r, c, v.to_pydatetime(), f)
    elif isinstance(v, (int, float, np.integer, np.floating)):
        ws.write_number(r, c, float(v), f)
    else:
        ws.write_string(r, c, str(v), f)


def table(ws, r0, c0, headers, rows, pct_cols, total=None):
    for j, h in enumerate(headers):
        ws.write(r0, c0 + j, h, hdr)
        if j:
            ws.set_column(c0 + j, c0 + j, max(len(h) + 3, 12))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            f = f_mon if isinstance(v, pd.Timestamp) else f_pct if headers[j] in pct_cols else f_int if j else f_txt
            put(ws, r0 + 1 + i, c0 + j, v, f)
    end = r0 + 1 + len(rows)
    if total is not None:
        for j, v in enumerate(total):
            put(ws, end, c0 + j, v, t_pct if headers[j] in pct_cols else t_int if j else t_txt)
        end += 1
    return end


PCT = {"Share %", "Settlement %", "MoM %", "%"}

# RAW DATA is written last but kept first in the tab order
ws_raw = wb.add_worksheet("RAW DATA")

# ---- formulas: every number on the analysis sheets is a COUNTIFS / SUMIFS on RAW DATA
from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell  # noqa: E402

RAW_COLS = ["ACCOUNT", "ORDER DATE", "ORDER MONTH", "STORE ORDER ID", "ORDER RELEASE ID", "ORDER LINE ID",
            "SELLER ORDER ID", "STYLE ID", "MYNTRA SKU CODE", "SELLER SKU CODE", "MY SKU", "FINAL SKU", "FINAL MY SKU",
            "DESIGN-NO", "BRAND", "CATEGORY", "SIZE", "PO TYPE", "MRP", "DISCOUNT", V, "SELLER PRICE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "SUB STATUS", "REASON", "IS EXCHANGE REPLACEMENT ORDER",
            "DELIVERED DATE", "CANCELLED DATE", "RTO DATE", "RETURN CREATED DATE", "RETURN MONTH", "RETURN ID",
            "RETURN PORTAL STATUS", "REFUNDED DATE", "COURIER", "CITY", "STATE",
            "FWD SETTLED AMT", "FWD PAYMENT DATE", "FWD UTR", "COMMISSION", "FWD LOGISTICS", "TCS + TDS",
            "REVERSE SETTLED AMT", "REVERSE PAYMENT DATE", "RETURN LOGISTICS FEE", "SPF / NOD AMT", "NET SETTLEMENT",
            "PAYMENT STATUS"]
RAW_LAST = len(d) + 1


def rng(col):
    c = xl_col_to_name(RAW_COLS.index(col))
    return f"'RAW DATA'!${c}$2:${c}${RAW_LAST}"


def q(text):
    return '"' + str(text).replace('"', '""') + '"'


def lit(text):
    """criterion that matches the text exactly (no wildcards)"""
    return q(str(text).replace("~", "~~").replace("*", "~*").replace("?", "~?"))


def ifs(fn, crit, sum_col=None):
    args = [rng(sum_col)] if sum_col else []
    for rg, c in [(rng("ORDER LINE ID"), q("<>"))] + crit:
        args += [rg, c]
    return f"{fn}({','.join(args)})"


def st(status):
    return [(rng("FINAL STATUS"), q(status))] if status else []


def cnt(crit, status=None):
    return ifs("COUNTIFS", crit + st(status))


def amt(col, crit, status=None):
    return ifs("SUMIFS", crit + st(status), col)


def month_crit(r):
    return [(rng("ORDER MONTH"), f"$A${r + 1}")]


BASE = {
    "gq": lambda c: cnt(c), "gv": lambda c: amt(V, c),
    "cq": lambda c: cnt(c, "Cancelled"),
    "rq": lambda c: cnt(c, "RTO"),
    "tq": lambda c: cnt(c, "Customer Return"), "tv": lambda c: amt(V, c, "Customer Return"),
    "nq": lambda c: cnt(c, "Delivered"), "nv": lambda c: amt(V, c, "Delivered"),
    "recv": lambda c: "SUM(" + ifs("SUMIFS", c + [(rng("FINAL STATUS"), '{"Delivered","Customer Return"}')],
                                   "NET SETTLEMENT") + ")",
}
PCT_KEYS = {"rp", "tp", "mom", "yoy", "share"}

# ---- MONTH / BRAND / CATEGORY: grouped headers (SALE, CANCELLED, RTO, ...) and one block per brand / category
grp_hdr = fmt(bold=True, bg_color="#FFC000", border=1, border_color="#BF8F00", align="center")
sub_hdr = fmt(bold=True, bg_color="#FFE699", border=1, border_color="#BF8F00", align="center")
blk_title = fmt(bold=True, font_size=12, bg_color="#FFF2CC", border=1, border_color="#BF8F00", align="left")

SPEC = [("SALE", "Gross Qty", "gq"), ("SALE", "Gross Value", "gv"),
        ("CANCELLED", "Qty", "cq"),
        ("RTO", "Qty", "rq"), ("RTO", "% of Dispatched", "rp"),
        ("CUSTOMER RETURN", "Qty", "tq"), ("CUSTOMER RETURN", "Value", "tv"),
        ("CUSTOMER RETURN", "% of Delivered", "tp"),
        ("NET SALE", "Qty", "nq"), ("NET SALE", "Value", "nv"), ("NET SALE", "ASP", "asp"),
        ("NET SALE", "MoM Growth %", "mom")]
SPEC_SHARE = [("NET SALE", "Share in Net Sale %", "share")]
SPEC_LY = [("LAST YEAR", "Net Value LY", "ly"), ("LAST YEAR", "YoY Growth %", "yoy")]
SPEC_PAY = [("PAYMENT", "Net Received", "recv")]
NV_COL = 1 + [s[2] for s in SPEC].index("nv")


def block(ws, r, first, title, rows, spec):
    """rows: (label, base, share) where base(key, r, top, cell) gives the formula of a count / value cell,
    or None for the total row (sum of the rows above). The last row is the total row.
    Returns (next free row, first data row)."""
    if title:
        ws.merge_range(r, 0, r, len(spec), title, blk_title)
        r += 1
    ws.merge_range(r, 0, r + 1, 0, first, grp_hdr)
    j = 0
    while j < len(spec):
        k = j
        while k + 1 < len(spec) and spec[k + 1][0] == spec[j][0]:
            k += 1
        if k > j:
            ws.merge_range(r, 1 + j, r, 1 + k, spec[j][0], grp_hdr)
        else:
            ws.write(r, 1 + j, spec[j][0], grp_hdr)
        j = k + 1
    for j, (_, sub, _) in enumerate(spec):
        ws.write(r + 1, 1 + j, sub, sub_hdr)
    r += 2
    top = r
    col = {key: 1 + j for j, (_, _, key) in enumerate(spec)}

    def cell(rr, key):
        return xl_rowcol_to_cell(rr, col[key])

    for n, (label, base, share) in enumerate(rows):
        last = n == len(rows) - 1
        put(ws, r, 0, label, t_txt if last else f_mon if isinstance(label, pd.Timestamp) else f_txt)
        c = {key: cell(r, key) for key in col}
        for j, (_, sub, key) in enumerate(spec):
            fm = None
            if key in BASE:
                fm = f"SUM({cell(top, key)}:{cell(r - 1, key)})" if base is None else base(key, r, top, cell)
            elif key == "rp":
                fm = f'IF({c["gq"]}-{c["cq"]}=0,"-",{c["rq"]}/({c["gq"]}-{c["cq"]}))'
            elif key == "tp":
                fm = f'IF({c["nq"]}+{c["tq"]}=0,"-",{c["tq"]}/({c["nq"]}+{c["tq"]}))'
            elif key == "asp":
                fm = f'IF({c["nq"]}=0,"-",{c["nv"]}/{c["nq"]})'
            elif key == "mom" and 0 < n and not last:
                prev = cell(r - 1, "nv")
                fm = f'IF({prev}=0,"-",{c["nv"]}/{prev}-1)'
            elif key == "ly" and n >= 12 and not last:
                fm = cell(r - 12, "nv")
            elif key == "yoy" and n >= 12 and not last:
                fm = f'IF({c["ly"]}=0,"-",{c["nv"]}/{c["ly"]}-1)'
            elif key == "share":
                fm = f'IF({share}=0,"-",{c["nv"]}/{share})'
            if fm is None:
                ws.write_string(r, 1 + j, "-", t_dash if last else f_dash)
                continue
            pct = key in PCT_KEYS
            ws.write_formula(r, 1 + j, "=" + fm,
                             (t_pct if pct else t_int) if last else (f_pct if pct else f_int))
        r += 1
    return r, top


def widths(ws, first_w, spec):
    ws.set_column(0, 0, first_w)
    for j, (_, sub, _) in enumerate(spec):
        ws.set_column(1 + j, 1 + j, max(len(sub) + 3, 12))


def by_month(extra_crit):
    return lambda key, r, top, cell: BASE[key](month_crit(r) + extra_crit)


months = list(month.index)
MW_TOP = 2  # first data row of MONTH WISE


def mw_net(i):
    return f"'MONTH WISE'!{xl_rowcol_to_cell(MW_TOP + i, NV_COL, True, True)}"


# MONTH WISE
ws = wb.add_worksheet("MONTH WISE")
spec = SPEC + SPEC_LY + SPEC_PAY
rows = [(mth, by_month([]), None) for mth in months] + [("Total", None, None)]
block(ws, 0, "Month", None, rows, spec)
widths(ws, 10, spec)
ws.freeze_panes(2, 1)


def group_sheet(name, group, min_orders=500):
    """group: one RAW DATA column, or a list of them (one row / block per combination, "A - B")."""
    ws = wb.add_worksheet(name)
    spec = SPEC + SPEC_SHARE + SPEC_PAY
    spec_all = [s for s in spec if s[2] != "mom"]
    cols = group if isinstance(group, list) else [group]
    label = " ".join(cols) if len(cols) > 1 else group
    key = a[cols].astype(object).apply(lambda x: " - ".join(x) if x.notna().all() else None, axis=1)
    parts_of = dict(zip(key, a[cols].itertuples(index=False, name=None)))
    size = key.value_counts()
    g_col = key.where(key.map(size) >= min_orders, "Others")
    fr = a.assign(G=g_col)
    order = [g for g in fr.groupby("G")[V].sum().sort_values(ascending=False).index if g != "Others"]
    if len(cols) > 1:  # brand A to Z, then category A to Z
        order.sort(key=lambda g: tuple(str(v).lower() for v in parts_of[g]))
    others = (g_col == "Others").any()

    def named(g):
        return [(rng(c), lit(v)) for c, v in zip(cols, parts_of[g])]

    # first table: every brand / category, all months together; Others = total less the named ones
    tot_row = 3 + len(order) + others  # title + 2 header rows + data rows
    tot_share = xl_rowcol_to_cell(tot_row, NV_COL, True, True)
    rows = [(g, lambda key, r, top, cell, g=g: BASE[key](named(g)), tot_share) for g in order]
    if others:
        rows.append(("Others", lambda key, r, top, cell: f"{cell(r + 1, key)}-SUM({cell(top, key)}:{cell(r - 1, key)})",
                     tot_share))
    rows.append(("Total", lambda key, r, top, cell: BASE[key]([]), tot_share))
    r, _ = block(ws, 0, label.title().replace(" ", " - "), f"ALL {label[:-1] + 'IES' if label.endswith('Y') else label + 'S'} - APR-25 TO SEP-26", rows, spec_all)
    r += 2
    # then one table per brand / category, every month; Others = month total less the named blocks
    tops = []
    total_net = mw_net(len(months))
    for g in order:
        rows = [(mth, by_month(named(g)), mw_net(i)) for i, mth in enumerate(months)] + [("Total", None, total_net)]
        r, top = block(ws, r, "Month", f"{label}: {g}", rows, spec)
        tops.append(top)
        r += 2
    if others:
        def rest(key, r, top, cell):
            return BASE[key](month_crit(r)) + "".join(f"-{cell(t + r - top, key)}" for t in tops)
        rows = [(mth, rest, mw_net(i)) for i, mth in enumerate(months)] + [("Total", None, total_net)]
        block(ws, r, "Month", f"{label}: Others", rows, spec)
    widths(ws, 40 if len(cols) > 1 else 24, spec)
    ws.freeze_panes(0, 1)


group_sheet("BRAND WISE", "BRAND")
group_sheet("CATEGORY WISE", "CATEGORY")
group_sheet("BRAND CATEGORY WISE", ["BRAND", "CATEGORY"])

# ---- REASONS: customer return (incl. exchange) and cancellation side by side
ws = wb.add_worksheet("REASONS")
col = 0
for label, status, t in [("Customer Return Reason", "Customer Return", cr_reason),
                         ("Cancellation Reason", "Cancelled", cn_reason)]:
    ws.write(0, col, label, hdr)
    ws.write(0, col + 1, "Qty", hdr)
    ws.write(0, col + 2, "%", hdr)
    end = len(t) + 1
    qty_all = f"{xl_rowcol_to_cell(1, col + 1)}:{xl_rowcol_to_cell(end - 1, col + 1)}"
    tot_cell = xl_rowcol_to_cell(end, col + 1, True, True)
    for i, reason in enumerate(t.index, start=1):
        crit = q("=") if reason == "Not Given" else lit(reason)
        put(ws, i, col, reason, f_txt)
        ws.write_formula(i, col + 1, "=" + cnt([(rng("REASON"), crit)], status), f_int)
        ws.write_formula(i, col + 2, f'=IF({tot_cell}=0,"-",{xl_rowcol_to_cell(i, col + 1)}/{tot_cell})', f_pct)
    put(ws, end, col, "Total", t_txt)
    ws.write_formula(end, col + 1, f"=SUM({qty_all})", t_int)
    ws.write_formula(end, col + 2, f"=SUM({xl_rowcol_to_cell(1, col + 2)}:{xl_rowcol_to_cell(end - 1, col + 2)})",
                     t_pct)
    ws.set_column(col, col, 40)
    ws.set_column(col + 1, col + 2, 12)
    ws.set_column(col + 3, col + 3, 3)
    col += 4
ws.freeze_panes(1, 0)

# ---- PAYMENT: by order month (formulas on RAW DATA), then cash received by payment month below
ws = wb.add_worksheet("PAYMENT")
ph = ["Order Month", "Net Qty", "Net Value", "Settled Qty", "Pending Qty", "Pending Value", "Forward Settled",
      "Reverse Debit", "SPF / NOD", "Net Settlement", "Commission", "Forward Logistics", "Return Logistics",
      "TCS + TDS", "Settlement %"]
ws.merge_range(0, 0, 0, len(ph) - 1, "PAYMENT AGAINST ORDERS PLACED IN EACH MONTH (BY ORDER MONTH)", blk_title)
for j, h in enumerate(ph):
    ws.write(1, j, h, hdr)
    if j:
        ws.set_column(j, j, max(len(h) + 3, 12))
settled = [(rng("FWD SETTLED AMT"), q("<>"))]
sum_cols = {6: "FWD SETTLED AMT", 7: "REVERSE SETTLED AMT", 8: "SPF / NOD AMT", 9: "NET SETTLEMENT",
            10: "COMMISSION", 11: "FWD LOGISTICS", 12: "RETURN LOGISTICS FEE", 13: "TCS + TDS"}
first = 2
end = first + len(months)
for i, mth in enumerate(months + ["Total"]):
    r = first + i
    last = mth == "Total"
    put(ws, r, 0, mth, t_txt if last else f_mon)
    c = {j: xl_rowcol_to_cell(r, j) for j in range(len(ph))}
    for j in range(1, len(ph)):
        if j == 14:
            fm = f'IF({c[2]}=0,"-",{c[9]}/{c[2]})'
        elif last:
            fm = f"SUM({xl_rowcol_to_cell(first, j)}:{xl_rowcol_to_cell(end - 1, j)})"
        elif j == 1:
            fm = cnt(month_crit(r), "Delivered")
        elif j == 2:
            fm = amt(V, month_crit(r), "Delivered")
        elif j == 3:
            fm = cnt(month_crit(r) + settled, "Delivered")
        elif j == 4:
            fm = f"{c[1]}-{c[3]}"
        elif j == 5:
            fm = f"{c[2]}-" + amt(V, month_crit(r) + settled, "Delivered")
        else:
            fm = amt(sum_cols[j], month_crit(r))
        pct = j == 14
        ws.write_formula(r, j, "=" + fm, (t_pct if pct else t_int) if last else (f_pct if pct else f_int))
qh = ["Payment Month", "Forward Settled", "Reverse Debit", "SPF / NOD", "Net Payout", "Forward Lines",
      "Reverse Lines", "Commission", "Forward Logistics", "Return Logistics", "TCS + TDS", "MoM %"]
qc = ["Forward Settled (Sale)", "Reverse Debit (Return/RTO)", "SPF / NOD", "Net Payout", "Forward Lines",
      "Reverse Lines", "Commission", "Forward Logistics", "Return Logistics Fee", "TCS + TDS", "MoM Net Payout %"]
rows = [[k] + [v[c] for c in qc] for k, v in paym.iterrows()]
rows[0][-1] = np.nan
ps = paym[qc].sum()
ws.merge_range(end + 3, 0, end + 3, len(ph) - 1, "PAYMENT RECEIVED IN BANK EACH MONTH (BY PAYMENT DATE)", blk_title)
table(ws, end + 4, 0, qh, rows, PCT, total=["Total"] + [ps[c] for c in qc[:-1]] + [np.nan])
ws.set_column(0, 0, 15)
ws.freeze_panes(0, 1)

# ---- INPUT LOG: every input file, account wise, with the dates it covers
ws = wb.add_worksheet("INPUT LOG")
f_day = fmt(num_format="dd-mmm-yy", align="left", **box)
heads = list(input_log.columns)
for j, h in enumerate(heads):
    ws.write(0, j, h, hdr)
for i, row in enumerate(input_log.itertuples(index=False), start=1):
    used = str(row[0]).endswith(")")
    for j, v in enumerate(row):
        f = (t_txt if used else f_txt) if j < 3 or j == 4 else (t_int if used else f_int) if j == 3 else             fmt(num_format="dd-mmm-yy", align="left", **tot) if used else f_day
        put(ws, i, j, v, f)
ws.set_column(0, 0, 46)
ws.set_column(1, 1, 9)
ws.set_column(2, 2, 70)
ws.set_column(3, 3, 10)
ws.set_column(4, 4, 26)
ws.set_column(5, 6, 11)
ws.freeze_panes(1, 0)

# ---- RAW DATA
ws = ws_raw
order = RAW_COLS
raw = d[order]
moneys = {"MRP", "DISCOUNT", V, "SELLER PRICE", "FWD SETTLED AMT", "COMMISSION", "FWD LOGISTICS", "TCS + TDS",
          "REVERSE SETTLED AMT", "RETURN LOGISTICS FEE", "SPF / NOD AMT", "NET SETTLEMENT"}
r_date, r_mon, r_num = fmt(num_format="dd-mmm-yy"), fmt(num_format="mmm-yy"), fmt(num_format="#,##0.00")
r_txt = fmt(align="left")
kinds = []
for j, c in enumerate(order):
    ws.write(0, j, c, hdr)
    w = len(c) + 3
    if "MONTH" in c:
        kinds.append(("d", r_mon))
        ws.set_column(j, j, max(w, 10))
    elif "DATE" in c:
        kinds.append(("d", r_date))
        ws.set_column(j, j, max(w, 12))
    elif c in moneys:
        kinds.append(("n", r_num))
        ws.set_column(j, j, max(w, 12))
    else:
        kinds.append(("s", None))
        ws.set_column(j, j, max(w, 40 if c in ("REASON", "SUB STATUS", "SELLER ORDER ID") else 16))
cols = [raw[c].to_numpy(dtype=object) for c in order]
for i in range(len(raw)):
    for j, (k, f) in enumerate(kinds):
        v = cols[j][i]
        if v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)):
            continue
        if k == "d":
            ws.write_datetime(i + 1, j, pd.Timestamp(v).to_pydatetime(), f)
        elif k == "n":
            ws.write_number(i + 1, j, float(v), f)
        else:
            ws.write_string(i + 1, j, str(v), r_txt)
ws.freeze_panes(1, 6)
ws.autofilter(0, 0, len(raw), len(order) - 1)
wb.close()
print("done", len(d))
