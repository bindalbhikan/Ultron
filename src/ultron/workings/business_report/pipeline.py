"""Business reporting: the owner's sale / return / payment analysis workbook of every portal (Myntra,
Flipkart, AJIO), the same layout for each (workbook.py), from every month kept in Drive AGENT
WORK/PORTAL REPORTS (core/portal_reports.py) since --from (default Jan 2025: a portal's months
start where its reports do), into Drive AGENT WORK/BUSINESS REPORTING as
"<PORTAL> SALE RETURN ANALYSIS <FIRST MON-YY> TO <LAST MON-YY>.xlsx" (the portal's older one goes to
the trash). Telegram: one line per portal.

Run after the reports change: the 2nd (order + payment reports), the 10th and the 15th (return
reports) - the business-report workflow follows those runs - or by hand.
"""
from __future__ import annotations

import argparse
import logging
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, output_dir
from ..core.drive import API, DriveFolder
from . import ajio, flipkart, myntra, oms
from .workbook import build

log = logging.getLogger("bindal.business_report")

FOLDER = "BUSINESS REPORTING"
# Where Flipkart's and AJIO's reports start (owner's rule, 3 Nov 2026): Apr-25. What a month lacks shows "-".
START = {"FLIPKART": date(2025, 4, 1), "AJIO": date(2025, 4, 1)}
NAME = re.compile(r"^(?P<portal>[A-Z]+) (?:(?P<acc>MAIN|DBCC|FMCC) )?(?P<kind>ORDER|RETURN|PAYMENT|SALES|MONTHLY|OMSGURU) REPORT "
                  r"(?P<mon>[A-Z]{3}-\d\d)(?P<partial> PARTIAL)?\.")


def month_of(text: str) -> date:
    y, m = text.split("-")
    return date(int(y), int(m), 1)


def portal_files(portal: str, first: date, last: date, dest: Path) -> list[dict]:
    """Every report file of the portal from first to last month, downloaded: one dict per file."""
    root = DriveFolder(env("AGENT_WORK_FOLDER_ID", pr.AGENT_WORK)).subfolder(pr.ROOT)
    pf = root.subfolder(portal) if root else None
    out = []
    if not pf:
        return out
    for year, yf in sorted(pf.children().items()):
        if not year.isdigit() or not first.year <= int(year) <= last.year:
            continue
        for mlabel, mf in DriveFolder(yf["id"], pf.http).children().items():
            try:
                month = pd.Timestamp(f"01-{mlabel}").date().replace(day=1)
            except ValueError:
                continue
            if not first <= month <= last:
                continue
            folder = DriveFolder(mf["id"], pf.http)
            for name in folder.children():
                m = NAME.match(name)
                if not m:
                    continue
                path = dest / portal / name
                if not path.exists():                  # --work: a folder kept between runs is not fetched again
                    path = folder.download(name, path)
                out.append({"path": path, "month": month, "kind": m["kind"], "account": m["acc"] or "",
                            "partial": bool(m["partial"]), "name": name})
    log.info("PORTAL REPORTS/%s: %d files %s..%s", portal, len(out), first, last)
    return sorted(out, key=lambda x: (x["month"], x["kind"], x["account"]))


def master_sheet(dest: Path) -> pd.DataFrame:
    folder = DriveFolder(env("AGENT_WORK_FOLDER_ID", pr.AGENT_WORK)).subfolder(FOLDER)
    path = folder.download("MasterSheet.xlsx", dest / "MasterSheet.xlsx") if folder else None
    if not path:
        raise RuntimeError("MasterSheet.xlsx not found in AGENT WORK/BUSINESS REPORTING")
    return pd.read_excel(path, sheet_name="Master", dtype=str, engine="calamine")


def log_rows(files: list[dict], frames: dict[str, pd.DataFrame], date_col: dict[str, tuple[str, callable]]) -> list:
    rows = []
    for f in files:
        df = frames.get(f["name"])
        n = len(df) if df is not None else 0
        col, parse = date_col.get(f["kind"], (None, None))
        d = parse(df[col]) if df is not None and col in df.columns else pd.Series(dtype="datetime64[ns]")
        rows.append([f["kind"].title(), f["account"] or "-", f["name"], n, col or "-",
                     d.min() if len(d.dropna()) else pd.NaT, d.max() if len(d.dropna()) else pd.NaT,
                     "days missing (PARTIAL)" if f["partial"] else ""])
    return rows


LOG_COLS = ["Input", "Account", "File", "Rows", "Date Used", "From", "To", "Note"]


def read_any(path: Path, **kw) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, low_memory=False)
    return pd.read_excel(path, dtype=str, **kw)


# ------------------------------------------------------------------ portals
def build_myntra(files: list[dict], master: pd.DataFrame) -> tuple:
    frames = {f["name"]: read_any(f["path"]).assign(ACCOUNT=f["account"]) for f in files}
    get = lambda k: [frames[f["name"]].assign(_order=i) for i, f in enumerate(files) if f["kind"] == k]  # noqa: E731
    o, r, p = (pd.concat(get(k), ignore_index=True) if get(k) else pd.DataFrame() for k in ("ORDER", "RETURN", "PAYMENT"))
    if not len(o):
        raise RuntimeError("no Myntra order report in PORTAL REPORTS")
    p = myntra.payments(p)
    raw = myntra.raw_data(o, r, master, p)
    lg = log_rows(files, frames, {"ORDER": ("created on", myntra.dt), "RETURN": ("return_created_date", myntra.dt),
                                  "PAYMENT": ("Payment_Date", myntra.dt)})
    lg.append(["Orders used", "ALL", "one row per order line", len(raw), "Order date", raw["ORDER DATE"].min(), raw["ORDER DATE"].max(), ""])
    lg.append(["SKU master", "ALL", "BUSINESS REPORTING/MasterSheet.xlsx (sheet Master)", len(master), "-", pd.NaT, pd.NaT, ""])
    return myntra.report(raw, p, pd.DataFrame(lg, columns=LOG_COLS)), o


def category_map(myntra_orders: pd.DataFrame, master: pd.DataFrame) -> dict[str, str]:
    """DESIGN-NO -> the article type Myntra lists it under (the most common), for the other portals."""
    if myntra_orders is None or not len(myntra_orders):
        return {}
    mm = master[master["Channel Name"].str.startswith("MYNTRA", na=False)]
    by_code = mm.dropna(subset=["MYNTRA SKU CODE"]).drop_duplicates("MYNTRA SKU CODE").set_index("MYNTRA SKU CODE")["DESIGN-NO"]
    by_sku = master.drop_duplicates("Channel Listing SKU Code").set_index("Channel Listing SKU Code")["DESIGN-NO"]
    design = myntra_orders["myntra sku code"].map(by_code).fillna(myntra_orders["seller sku code"].map(by_sku))
    t = pd.DataFrame({"d": design, "a": myntra_orders["article type"]}).dropna()
    return t.groupby("d")["a"].agg(lambda x: x.value_counts().index[0]).to_dict()


def month_names(months) -> str:
    return ", ".join(f"{m:%b-%y}" for m in sorted(months))


def no_payment_months(raw: pd.DataFrame, paid: str, below: float = 0.01) -> set:
    """Order months with (almost) no payment on their sold lines: their payment is not known, not pending."""
    sold = raw[raw["FINAL STATUS"].isin(["Delivered", "Customer Return"])]
    share = sold[paid].notna().groupby(sold["ORDER MONTH"]).mean()
    return set(share[share < below].index)


def mark_no_payment(raw: pd.DataFrame, months: set) -> None:
    hit = raw["ORDER MONTH"].isin(months) & raw["PAYMENT STATUS"].eq("Payment Pending")
    raw.loc[hit, "PAYMENT STATUS"] = "No Payment Report"


def split_part(raw: pd.DataFrame, part: pd.Series, status: pd.Series, money: set, return_cols: list[str]) -> tuple[pd.DataFrame, int]:
    """Count by quantity: a line of which only some units were returned or cancelled becomes two rows of the same id, those
    units with `status` and the rest with the line's own. A rest whose status said returned is Delivered, without the return's
    details. Money is shared by quantity; the totals of QTY and money stay as they were (raises otherwise). (raw, lines split)"""
    part = pd.Series(part.values, index=raw.index).fillna(0)
    hit = (part > 0) & (part < raw["QTY"])
    if not hit.any():
        return raw, 0
    share = part[hit] / raw.loc[hit, "QTY"]
    cols = [c for c in money if c in raw.columns]
    done, rest = raw[hit].copy(), raw[hit].copy()
    done["QTY"], rest["QTY"] = part[hit], raw.loc[hit, "QTY"] - part[hit]
    for c in cols:
        amount = pd.to_numeric(raw.loc[hit, c], errors="coerce")
        done[c], rest[c] = amount * share, amount * (1 - share)
    done["FINAL STATUS"] = pd.Series(status.values, index=raw.index)[hit]
    gone = rest["FINAL STATUS"].isin(["Customer Return", "RTO", "Return Type Pending"])
    rest.loc[gone, "FINAL STATUS"] = "Delivered"
    for c in return_cols:
        if c in rest.columns:
            rest[c] = rest[c].astype(object)
            rest.loc[gone, c] = "" if c in ("REASON", "SUB REASON", "RETURN TYPE SOURCE") else None
    out = pd.concat([raw[~hit], done, rest], ignore_index=True).sort_values("ORDER DATE", kind="stable").reset_index(drop=True)
    for c in ["QTY", *cols]:
        before, after = pd.to_numeric(raw[c], errors="coerce").sum(), pd.to_numeric(out[c], errors="coerce").sum()
        if abs(before - after) > 0.01:
            raise RuntimeError(f"split by quantity changed the total of {c}: {before} to {after}")
    return out, int(hit.sum())


def flipkart_with_oms(raw: pd.DataFrame, lines: pd.DataFrame, master: pd.DataFrame, cats: dict, no_orders: set) -> tuple[pd.DataFrame, int]:
    """OMSGuru's status on Flipkart's lines, and its lines the reports do not have in months with no Orders report (most
    RTO and some cancelled items never reach the Sales Report or a monthly file). (raw, lines added)"""
    raw = raw.reset_index(drop=True)
    raw["OMS STATUS"] = ""
    if not len(lines):
        return raw, 0
    found, used = oms.match(raw, "ORDER ID", lines)
    text, final = oms.status_of(raw, found, lines)
    raw["OMS STATUS"] = text
    settled = raw["RETURN TYPE SOURCE"].eq("Returns report")
    after = oms.corrected(raw["FINAL STATUS"], final, settled)
    changed = after.ne(raw["FINAL STATUS"]) & after.isin(["Customer Return", "RTO"])
    raw.loc[changed, "RETURN TYPE SOURCE"] = "OMSGuru"
    raw["FINAL STATUS"] = after
    extra = lines[~lines.index.isin(used)].copy()
    extra["month"] = extra["DAY"].dt.to_period("M").dt.to_timestamp()
    extra = extra[extra["month"].isin(no_orders)]
    if not len(extra):
        return raw, 0
    fm = master[master["Channel Name"].str.upper().eq("FLIPKART")].copy()
    fm["k"] = fm["FINAL SKU"].astype(str).str.strip().str.upper()
    fm = fm.drop_duplicates("k").set_index("k")
    new = pd.DataFrame({"ORDER DATE": extra["DAY"].values, "ORDER MONTH": extra["month"].values, "ORDER ID": extra["ORDER"].values,
                        "SOURCE": "OMSGuru", "OMS STATUS": extra["STATUS"].values, "SKU": extra["SKU"].values, "FINAL SKU": extra["SKU"].values,
                        "QTY": extra["QTY"].values, "SALE VALUE": extra["VALUE"].values, "PORTAL ORDER STATUS": extra["STATUS"].values,
                        "FINAL STATUS": extra["FINAL"].values})
    new["RETURN TYPE SOURCE"] = new["FINAL STATUS"].isin(["Customer Return", "RTO"]).map({True: "OMSGuru", False: ""})
    for c in ["MY SKU", "FINAL MY SKU", "DESIGN-NO"]:
        new[c] = new["SKU"].map(fm[c])
    new["BRAND"] = new["SKU"].map(fm["Brand"]).fillna("Not Mapped")
    token = new["SKU"].str.split("-").str[1].str.upper().map(flipkart.CATEGORY_WORDS)
    new["CATEGORY"] = new["DESIGN-NO"].map(cats or {}).fillna(token).fillna("Not Mapped")
    new["PAYMENT STATUS"] = new["FINAL STATUS"].isin(["Delivered", "Customer Return"]).map({True: "Payment Pending", False: "Not Applicable"})
    new["REASON"] = ""
    return pd.concat([raw, new], ignore_index=True).sort_values(["ORDER DATE", "ORDER ITEM ID"], na_position="last").reset_index(drop=True), len(new)


def ajio_with_oms(raw: pd.DataFrame, lines: pd.DataFrame, master: pd.DataFrame | None = None, cats: dict | None = None) -> tuple[pd.DataFrame, int]:
    """OMSGuru's status (channels Ajio and Ajio Api) on AJIO's lines, and its lines of days no report reaches.
    (raw, lines whose final status it changed)"""
    raw = raw.reset_index(drop=True)
    raw["OMS STATUS"] = ""
    if not len(lines):
        return raw, 0
    found, used = oms.match(raw, "SELLER ORDER NO", lines)
    text, final = oms.status_of(raw, found, lines)
    raw["OMS STATUS"] = text
    has_return = raw["RETURN TYPE"].notna() & raw["FINAL STATUS"].isin(["Customer Return", "RTO"])
    after = oms.corrected(raw["FINAL STATUS"], final, has_return)
    changed = int(after.ne(raw["FINAL STATUS"]).sum())
    raw["FINAL STATUS"] = after
    days = set(raw["ORDER DATE"].dropna())
    extra = lines[~lines.index.isin(used) & ~lines["DAY"].isin(days)]
    if len(extra) and master is not None:
        am = master[master["Channel Name"].str.upper().str.startswith("AJIO", na=False)].copy()
        am["k"] = am["FINAL SKU"].astype(str).str.strip().str.upper()
        am = am.drop_duplicates("k").set_index("k")
        new = pd.DataFrame({"ORDER DATE": extra["DAY"].values, "ORDER MONTH": extra["DAY"].dt.to_period("M").dt.to_timestamp().values,
                            "SOURCE": "OMSGuru", "OMS STATUS": extra["STATUS"].values, "SELLER ORDER NO": extra["ORDER"].values,
                            "SELLER SKU": extra["SKU"].values, "FINAL SKU": extra["SKU"].values, "QTY": extra["QTY"].values,
                            "INVOICE VALUE": extra["VALUE"].values, "PORTAL ORDER STATUS": extra["STATUS"].values,
                            "FINAL STATUS": extra["FINAL"].values, "REASON": "", "PAYMENT STATUS": "Payment Pending"})
        for c in ["MY SKU", "FINAL MY SKU", "DESIGN-NO"]:
            new[c] = new["SELLER SKU"].map(am[c])
        new["BRAND"] = new["SELLER SKU"].map(am["Brand"]).fillna("Not Mapped")
        new["CATEGORY"] = new["DESIGN-NO"].map(cats or {}).fillna("Not Mapped")
        raw = pd.concat([raw, new], ignore_index=True).sort_values(["ORDER DATE"], na_position="last").reset_index(drop=True)
    return raw, changed


def build_flipkart(files: list[dict], master: pd.DataFrame, cats: dict, first: date) -> tuple:
    paths = lambda k: [f["path"] for f in files if f["kind"] == k]  # noqa: E731
    o, r, s = flipkart.read_orders(paths("ORDER")), flipkart.read_returns(paths("RETURN")), flipkart.read_settled(paths("PAYMENT"))
    tax = flipkart.read_sales(paths("SALES"))
    monthly = flipkart.read_monthly([(f["path"], pd.Timestamp(f["month"])) for f in files if f["kind"] == "MONTHLY"])
    # a monthly file is the payment only of a month with no Settled Transactions file: nothing counts twice
    s = pd.concat([s, flipkart.monthly_settled(monthly, {pd.Timestamp(f["month"]) for f in files if f["kind"] == "PAYMENT"})], ignore_index=True)
    if not len(o) and not len(tax):
        raise RuntimeError("no Flipkart order or sales report in PORTAL REPORTS")
    if not len(o):
        o = pd.DataFrame(columns=["order_item_id"])
    raw = flipkart.raw_data(o, r, master, s, cats, tax, monthly)
    lines = oms.read(paths("OMSGURU"))
    no_orders = {pd.Timestamp(f["month"]) for f in files if f["kind"] in ("SALES", "MONTHLY")} - {pd.Timestamp(f["month"]) for f in files if f["kind"] == "ORDER"}
    raw, added = flipkart_with_oms(raw, lines, master, cats, no_orders)
    # a month with no order, sales or monthly report is left out and named: stray items of it in other
    # months' files (a return or settlement event) are not that month's sale
    have = {pd.Timestamp(f["month"]) for f in files if f["kind"] in ("ORDER", "SALES", "MONTHLY")}
    lacking = raw[~raw["ORDER MONTH"].isin(have) & (raw["ORDER MONTH"] >= pd.Timestamp(first))]
    raw = raw[raw["ORDER MONTH"].isin(have) & (raw["ORDER MONTH"] >= pd.Timestamp(first))].reset_index(drop=True)
    raw["QTY"] = pd.to_numeric(raw["QTY"], errors="coerce").fillna(1)
    part = flipkart.returned_units(raw, r, tax).where(raw["FINAL STATUS"].ne("Cancelled"), 0)
    part_status = raw["FINAL STATUS"].where(raw["FINAL STATUS"].ne("Delivered"), "Return Type Pending")
    raw, split = split_part(raw, part, part_status, flipkart.MONEY, flipkart.RETURN_COLS)
    frames = {}
    for df, kind in ((o, "ORDER"), (r, "RETURN"), (s, "PAYMENT"), (tax, "SALES"), (monthly, "MONTHLY"), (lines, "OMSGURU")):
        if len(df):
            for name, g in df.groupby("_file"):
                frames[name] = g
    lg = log_rows(files, frames, {"ORDER": ("order_date", flipkart.dt), "RETURN": ("return_approval_date", flipkart.dt),
                                  "PAYMENT": ("Payment Date", flipkart.dt), "SALES": ("Order Date", flipkart.dt),
                                  "MONTHLY": ("order_date", flipkart.dt), "OMSGURU": ("DAY", flipkart.dt)})
    lg.append(["OMSGuru", "-", f"status on {int(raw['OMS STATUS'].ne('').sum()):,} lines; {added:,} lines added in months with no Orders report", added, "-", pd.NaT, pd.NaT,
               "a return, RTO or cancellation it shows replaces Delivered, In Transit or Return Type Pending; a line the Returns report settled is not changed. FBF orders are not in OMSGuru"])
    unsettled = int(((raw["FINAL STATUS"] == "Delivered") & raw["SALE VALUE"].isna()).sum())
    lg.append(["Orders used", "-", "one row per order item", len(raw), "Order date", raw["ORDER DATE"].min(), raw["ORDER DATE"].max(),
               f"sale value = the Sales Report's Price before discount, else Settled Transactions' Sale Amount; {unsettled:,} delivered items have none; "
               f"{int((raw['SOURCE'] == 'Sales report').sum()):,} items from the Sales Report only (months without an Orders report), "
               f"{int((raw['SOURCE'] == 'Monthly file').sum()):,} from the owner's monthly files only"])
    lg.append(["Counted by quantity", "-", f"{split:,} lines returned in part", split, "-", pd.NaT, pd.NaT,
               "every count sums QTY; a line of which only some units came back is two rows of the same ORDER ITEM ID, money shared by quantity"])
    months = set(raw["ORDER MONTH"].dropna())
    with_orders = {pd.Timestamp(f["month"]) for f in files if f["kind"] == "ORDER"}
    with_sales = {pd.Timestamp(f["month"]) for f in files if f["kind"] == "SALES"}
    unknown = {"cq": months - with_orders - with_sales, "rq": set() if len(lines) else months - with_orders - with_sales,
               "recv": no_payment_months(raw, "NET SETTLEMENT", 0.10)}     # a few stray settlements are not a month's payment
    partly = no_payment_months(raw, "NET SETTLEMENT", 0.90) - unknown["recv"]
    mark_no_payment(raw, unknown["recv"])
    if unknown["cq"]:
        lg.append(["Not known: Cancelled", "-", month_names(unknown["cq"]), "-", "-", pd.NaT, pd.NaT,
                   "shown as -: no Orders report and no Sales Report for these months"])
    if months & with_sales - with_orders:
        lg.append(["Cancelled from the Sales Report", "-", month_names(months & with_sales - with_orders), "-", "-", pd.NaT, pd.NaT,
                   "no Orders report: every month's Sales Report merged, by order date. An item never invoiced (cancelled before dispatch) is in no report, so Gross and Cancelled are low in these months; an item cancelled and invoiced again counts as sold"])
    if unknown["rq"]:
        lg.append(["Not known: RTO", "-", month_names(unknown["rq"]), "-", "-", pd.NaT, pd.NaT,
                   "shown as -: no Sales Report for these months and the monthly files hold only items with a settlement, so most RTO items are not in them. Net Sale and Customer Return are whole"])
    if unknown["recv"]:
        lg.append(["Not known: Payment", "-", month_names(unknown["recv"]), "-", "-", pd.NaT, pd.NaT, "shown as -: no payment file reaches these orders (a few stray settlements are in RAW DATA and the PAYMENT MATCH only)"])
    if partly:
        lg.append(["Payment only in part", "-", month_names(partly), "-", "-", pd.NaT, pd.NaT, "Net Received is low in these months: the payment files of the months after them are missing (files exist for May-25, Jun-25, Oct-25 on)"])
    if len(lacking):
        names = ", ".join(sorted({f"{m:%b-%y}" for m in lacking["ORDER MONTH"].dropna()}))
        lg.append(["Months left out", "-", names, len(lacking), "Order date", pd.NaT, pd.NaT, "no order or sales report for these months yet"])
    lg.append(["SKU master", "-", "MasterSheet.xlsx (channel FLIPKART); category = Myntra's article type of the design",
               len(master), "-", pd.NaT, pd.NaT, ""])
    bank = flipkart.bank_paid([(f["path"], pd.Timestamp(f["month"])) for f in files if f["kind"] == "PAYMENT"],
                              [(f["path"], pd.Timestamp(f["month"])) for f in files if f["kind"] == "MONTHLY"])
    rep = flipkart.report(raw, s, pd.DataFrame(lg, columns=LOG_COLS), bank)
    rep.unknown = unknown
    if rep.pay_months is not None and "Net Bank Paid" in rep.pay_months.columns:
        paid, orders, lines = (float(rep.pay_months["Net Bank Paid"].sum()), float(rep.pay_months["Order Settlement"].sum()),
                               float(raw["NET SETTLEMENT"].sum()))
        rep.pay_match = [("Net bank paid, all payment months", paid),
                         ("Add back: non-order SPF, ads, storage (no order line)", orders - paid),
                         ("= Order money settled", orders),
                         ("Orders placed before the report starts, or not in it", lines - orders),
                         ("= NET SETTLEMENT in RAW DATA = Net Received in MONTH WISE", lines)]
    return rep


def build_ajio(files: list[dict], master: pd.DataFrame, cats: dict, first: date) -> tuple:
    paths = lambda k: [f["path"] for f in files if f["kind"] == k]  # noqa: E731
    o, r, p = ajio.read(paths("ORDER")), ajio.read(paths("RETURN")), ajio.read(paths("PAYMENT"))
    if not len(o):
        raise RuntimeError("no AJIO order report in PORTAL REPORTS")
    monthly = ajio.read_monthly(paths("MONTHLY"))
    raw = ajio.raw_data(o, r, p, master, cats, monthly)
    raw = raw[raw["ORDER MONTH"] >= pd.Timestamp(first)].reset_index(drop=True)
    lines = oms.read(paths("OMSGURU"))
    raw, changed = ajio_with_oms(raw, lines, master, cats)
    raw = raw[raw["ORDER MONTH"] >= pd.Timestamp(first)].reset_index(drop=True)
    frames = {}
    for df in (o, r, p, monthly, lines):
        if len(df):
            for name, g in df.groupby("_file"):
                frames[name] = g
    ledger_date = lambda s: pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")  # noqa: E731
    lg = log_rows(files, frames, {"ORDER": ("Cust Order Date", ajio.adate), "RETURN": ("Return Created Date", ajio.adate),
                                  "PAYMENT": ("DOCDATE", ledger_date), "MONTHLY": ("Cust Order Date", ajio.adate),
                                  "OMSGURU": ("DAY", flipkart.dt)})
    lg.append(["OMSGuru", "-", f"channels Ajio and Ajio Api: status on {int(raw['OMS STATUS'].ne('').sum()):,} lines, final status changed on {changed:,}", len(lines), "-", pd.NaT, pd.NaT,
               "a return, RTO or cancellation it shows replaces Delivered or In Transit; a line the RTV report settled is not changed"])
    lg.append(["Orders used", "-", "one row per order line (Cust Order No + Seller SKU)", len(raw), "Order date",
               raw["ORDER DATE"].min(), raw["ORDER DATE"].max(), "sale value = Selling Price x qty; net settlement = SRM ledger G4 received + IC reversed"])
    if len(p):
        led = ajio.ledger_lines(p)
        left = {dt: led.loc[led["DT"] == dt, "amt"].sum() - raw[col].sum() for dt, col in (("G4", "INVOICE PAID"), ("IC", "CREDIT NOTE DEBIT"))}
        if any(abs(v) >= 1 for v in left.values()):
            lg.append(["Ledger not on these orders", "-", f"G4 {left['G4']:,.0f}, IC {left['IC']:,.0f}", len(led), "-", pd.NaT, pd.NaT,
                       "in the ledger, but its order or return line is not in these reports: left out of NET SETTLEMENT"])
    from_file = raw[raw["SOURCE"] == "Monthly file"]
    before_ledger = no_payment_months(raw, "INVOICE PAID")
    raw = ajio.file_payment(raw, r, before_ledger)
    # by quantity, after the payment (it maps a line's money by its key): cancelled units first, then returned ones
    raw["QTY"] = pd.to_numeric(raw["QTY"], errors="coerce").fillna(1)
    money = ajio.MONEY - {"MRP", "SELLING PRICE"}
    raw, cancel_split = split_part(raw, ajio.cancelled_units(raw, o).where(raw["FINAL STATUS"].ne("Cancelled"), 0),
                                   pd.Series("Cancelled", index=raw.index), money, ajio.RETURN_COLS)
    returned = ajio.returned_units(raw, r).where(raw["FINAL STATUS"].isin(["Customer Return", "RTO"]), 0)
    raw, return_split = split_part(raw, returned, raw["FINAL STATUS"], money, ajio.RETURN_COLS)
    lg.append(["Counted by quantity", "-", f"{return_split:,} lines returned in part, {cancel_split:,} cancelled in part", return_split + cancel_split, "-", pd.NaT, pd.NaT,
               "every count sums QTY; a line of which only some units came back or were cancelled is two rows of the same order line, money shared by quantity"])
    from_oms = raw[raw["SOURCE"] == "OMSGuru"]
    value_seen = raw["SALE VALUE"].notna().groupby(raw["ORDER MONTH"]).any()
    no_value = set(value_seen[~value_seen].index)
    unknown = {"cq": set(from_file["ORDER MONTH"].dropna()) | set(from_oms["ORDER MONTH"].dropna()), "recv": set(),
               "gv": no_value, "tv": no_value, "nv": no_value}
    if len(from_oms):
        lg.append(["Lines from OMSGuru", "-", f"{month_names(set(from_oms['ORDER MONTH'].dropna()))}: days with no order report or monthly file", int(from_oms["QTY"].sum()), "-",
                   from_oms["ORDER DATE"].min(), from_oms["ORDER DATE"].max(), "order id, SKU, qty, status; no selling price, so a month with only these shows its values as -"])
    if len(from_file):
        lg.append(["Monthly files", "-", f"{len(from_file):,} order lines the order report does not have", len(from_file), "-", pd.NaT, pd.NaT, ""])
    stale = int((raw["STALE SHIPPED"] & raw["FINAL STATUS"].eq("Delivered")).sum())
    if stale:
        lg.append(["Shipped, counted Delivered", "-", f"{stale:,} order lines", stale, "-", pd.NaT, pd.NaT,
                   f"Shipped in their report, over {ajio.SHIPPED_DAYS} days old, no return line since: a report's status is as old as its file"])
    if unknown["cq"]:
        lg.append(["Not known: Cancelled", "-", month_names(unknown["cq"]), "-", "-", pd.NaT, pd.NaT,
                   "shown as -: the monthly files and OMSGuru leave out most lines cancelled before shipping, so Gross Qty and Gross Value are low in these months"])
    if before_ledger:
        lg.append(["Payment as per monthly files", "-", month_names(before_ledger), "-", "-", pd.NaT, pd.NaT,
                   "the SRM ledger has no line before 28 Feb 2026: Invoice Value less FWD B2B Invoice Amt of returns, as the owner's monthly files work it out (their EXP sheets not taken off); what is due, not the bank"])
    charges = ajio.monthly_expenses([(f["path"], pd.Timestamp(f["month"])) for f in files if f["kind"] == "MONTHLY"])
    rep = ajio.report(raw, p, pd.DataFrame(lg, columns=LOG_COLS), ajio.file_payment_months(raw, r, before_ledger, charges))
    rep.unknown = unknown
    if rep.pay_months is not None and len(p):
        ledger_months = rep.pay_months[rep.pay_months["Bank Paid (KP)"].notna()]
        rep.pay_match = ajio.payment_match(raw, p, ledger_months)
    return rep


# ------------------------------------------------------------------ run
def upload(path: Path, portal: str) -> None:
    folder = DriveFolder(env("AGENT_WORK_FOLDER_ID", pr.AGENT_WORK)).subfolder(FOLDER, create=True)
    folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for name, meta in folder.children().items():
        if name.startswith(f"{portal} SALE RETURN ANALYSIS") and name != path.name:
            r = folder.http.patch(f"{API}/{meta['id']}", params={"supportsAllDrives": "true"}, json={"trashed": True}, timeout=60)
            folder._check(r, f"trash of {name}")
            log.info("Older %s moved to the trash", name)


def summary(rep, out: Path) -> str:
    raw = rep.raw
    q = lambda s: float(raw.loc[raw["FINAL STATUS"] == s, "QTY"].sum())  # noqa: E731
    gross, net, ret, rto, canc = float(raw["QTY"].sum()), q("Delivered"), q("Customer Return"), q("RTO"), q("Cancelled")
    m0, m1 = raw["ORDER MONTH"].min(), raw["ORDER MONTH"].max()
    disp = gross - canc
    return (f"✅ <b>{rep.portal}</b> {m0:%b-%y} to {m1:%b-%y}: {int(gross):,} qty, net {net / gross:.1%}, "
            f"return {ret / (net + ret):.1%}, RTO {rto / disp:.1%}" + ("" if rep.settle else ", no payments yet")
            if gross and disp and (net + ret) else f"✅ <b>{rep.portal}</b>: {out.name}")


def myntra_orders_only(files: list[dict]) -> pd.DataFrame:
    """Myntra's order lines only (the category map of the other portals)."""
    frames = [read_any(f["path"]) for f in files if f["kind"] == "ORDER"]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run(args) -> int:
    today = date.today()
    first = month_of(args.from_month)
    last = month_of(args.to_month) if args.to_month else (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    portals = [p.strip().upper() for p in (args.portals or "MYNTRA,FLIPKART,AJIO").split(",") if p.strip()]
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="business_report_"))
    work.mkdir(parents=True, exist_ok=True)
    master = master_sheet(work)
    out_dir = output_dir("business_report")
    lines, failed, cats = ["📊 <b>Business reporting</b>", ""], [], {}
    others = [p for p in portals if p != "MYNTRA"]
    if "MYNTRA" in portals or others:          # Myntra first: its article types name the others' categories
        try:
            files = portal_files("MYNTRA", first, last, work)
            if "MYNTRA" in portals:
                rep, orders = build_myntra(files, master)
                done = finish(rep, out_dir, args)
                lines.append(summary(rep, done))
            else:
                orders = myntra_orders_only(files)
            cats = category_map(orders, master)
        except Exception as exc:  # noqa: BLE001 - one portal never stops the others
            log.exception("MYNTRA business report failed")
            failed.append("MYNTRA")
            lines.append(f"❌ <b>MYNTRA</b>: {telegram.esc((str(exc).splitlines() or [type(exc).__name__])[0][:200])}")
    for portal in others:
        try:
            start = max(first, START.get(portal, first))
            files = portal_files(portal, start, last, work)
            rep = build_flipkart(files, master, cats, start) if portal == "FLIPKART" else build_ajio(files, master, cats, start)
            lines.append(summary(rep, finish(rep, out_dir, args, start)))
        except Exception as exc:  # noqa: BLE001
            log.exception("%s business report failed", portal)
            failed.append(portal)
            lines.append(f"❌ <b>{portal}</b>: {telegram.esc((str(exc).splitlines() or [type(exc).__name__])[0][:200])}")
    lines.append(f"\n<i>Drive AGENT WORK/{FOLDER}</i>" + (" (test run: not uploaded)" if args.no_upload else ""))
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    if failed:
        raise RuntimeError(f"business report failed for {', '.join(failed)}")
    return 0


def finish(rep, out_dir: Path, args, first: date | None = None) -> Path:
    # a report of the first month also carries a few older orders (their events fell in it): not a month of the report
    rep.raw = rep.raw[rep.raw["ORDER MONTH"] >= pd.Timestamp(first or month_of(args.from_month))].reset_index(drop=True)
    m0, m1 = rep.raw["ORDER MONTH"].min(), rep.raw["ORDER MONTH"].max()
    out = out_dir / f"{rep.portal} SALE RETURN ANALYSIS {m0:%b-%y} TO {m1:%b-%y}".upper()
    out = out.with_name(out.name + ".xlsx")
    build(rep, out)
    if not args.no_upload:
        upload(out, rep.portal)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py business-report", description=__doc__.splitlines()[0])
    p.add_argument("--portals", default="", help="MYNTRA,FLIPKART,AJIO (default: all)")
    p.add_argument("--from", dest="from_month", default="2025-01", metavar="YYYY-MM", help="first order month (default 2025-01)")
    p.add_argument("--to", dest="to_month", default="", metavar="YYYY-MM", help="last order month (default: last month)")
    p.add_argument("--no-upload", action="store_true", help="build only, Drive not changed (test run)")
    p.add_argument("--work", default="", help="keep the downloaded reports in this folder (a test run again reads them)")
    return run_bot("Business reporting", p, run, argv)
