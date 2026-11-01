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
from . import ajio, flipkart, myntra
from .workbook import build

log = logging.getLogger("bindal.business_report")

FOLDER = "BUSINESS REPORTING"
NAME = re.compile(r"^(?P<portal>[A-Z]+) (?:(?P<acc>MAIN|DBCC|FMCC) )?(?P<kind>ORDER|RETURN|PAYMENT) REPORT "
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


def build_flipkart(files: list[dict], master: pd.DataFrame, cats: dict) -> tuple:
    paths = lambda k: [f["path"] for f in files if f["kind"] == k]  # noqa: E731
    o, r, s = flipkart.read_orders(paths("ORDER")), flipkart.read_returns(paths("RETURN")), flipkart.read_settled(paths("PAYMENT"))
    if not len(o):
        raise RuntimeError("no Flipkart order report in PORTAL REPORTS")
    raw = flipkart.raw_data(o, r, master, s, cats)
    frames = {}
    for df, kind in ((o, "ORDER"), (r, "RETURN"), (s, "PAYMENT")):
        if len(df):
            for name, g in df.groupby("_file"):
                frames[name] = g
    lg = log_rows(files, frames, {"ORDER": ("order_date", flipkart.dt), "RETURN": ("return_approval_date", flipkart.dt),
                                  "PAYMENT": ("Payment Date", flipkart.dt)})
    unsettled = int(((raw["FINAL STATUS"] == "Delivered") & raw["SALE VALUE"].isna()).sum())
    lg.append(["Orders used", "-", "one row per order item", len(raw), "Order date", raw["ORDER DATE"].min(), raw["ORDER DATE"].max(),
               f"sale value = Settled Transactions' Sale Amount; {unsettled:,} delivered items not settled yet have none"])
    lg.append(["SKU master", "-", "MasterSheet.xlsx (channel FLIPKART); category = Myntra's article type of the design",
               len(master), "-", pd.NaT, pd.NaT, ""])
    return flipkart.report(raw, s, pd.DataFrame(lg, columns=LOG_COLS))


def build_ajio(files: list[dict], master: pd.DataFrame, cats: dict) -> tuple:
    paths = lambda k: [f["path"] for f in files if f["kind"] == k]  # noqa: E731
    o, r, p = ajio.read(paths("ORDER")), ajio.read(paths("RETURN")), ajio.read(paths("PAYMENT"))
    if not len(o):
        raise RuntimeError("no AJIO order report in PORTAL REPORTS")
    raw = ajio.raw_data(o, r, p, master, cats)
    frames = {}
    for df in (o, r, p):
        if len(df):
            for name, g in df.groupby("_file"):
                frames[name] = g
    ledger_date = lambda s: pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")  # noqa: E731
    lg = log_rows(files, frames, {"ORDER": ("Cust Order Date", ajio.adate), "RETURN": ("Return Created Date", ajio.adate),
                                  "PAYMENT": ("DOCDATE", ledger_date)})
    lg.append(["Orders used", "-", "one row per order line (Cust Order No + Seller SKU)", len(raw), "Order date",
               raw["ORDER DATE"].min(), raw["ORDER DATE"].max(), "sale value = Selling Price x qty; payment = SRM ledger G4 + IC"])
    return ajio.report(raw, p, pd.DataFrame(lg, columns=LOG_COLS))


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
            files = portal_files(portal, first, last, work)
            rep = build_flipkart(files, master, cats) if portal == "FLIPKART" else build_ajio(files, master, cats)
            lines.append(summary(rep, finish(rep, out_dir, args)))
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


def finish(rep, out_dir: Path, args) -> Path:
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
