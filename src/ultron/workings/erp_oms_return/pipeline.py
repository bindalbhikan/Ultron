"""ERP to OMSGuru returns: a return booked in the ERP's GRN is accepted in OMSGuru, as Good, the same evening.

Every GRN line of the ERP (report 58) goes on Drive AGENT WORK/ERP TO OMSGURU RETURN.xlsx, sheet 2026, with its OMSGuru state; SUMMARY
adds it up by month and by portal and month, in formulas on that sheet. Each AWB not yet accepted is tried (accept.py): accepted as
Good, the note "Return accepted in ERP <GRN date>" on the order. Never a Putaway, so OMSGuru's stock does not change.

Not accepted, and said why on the sheet: a line with no id in the ERP (it cannot be tied to an order), an AWB OMSGuru does not know, a
SKU the ERP booked that the order does not have (maybe the wrong item came back), a qty above what was sent, a GRN line with no date,
qty or SKU. ACTION is kept per GRN line, so a later GRN line of an AWB already accepted is still worked.
"""
from __future__ import annotations

import argparse
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

from ultron.portals.omsguru import OmsGuruClient

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num, output_dir
from ..core.drive import DriveFolder
from ..portals.erp import Erp
from .accept import accept
from ..core.config import agent_work_id

log = logging.getLogger("bindal.erp_oms_return")

FILE = "ERP TO OMSGURU RETURN.xlsx"
SHEET = "2026"
DONE = "Accepted"
NO_ID = "No ERP ID"
NO_DATA = "No GRN date, qty or SKU: check"
FAILS_IN_A_ROW = 40
COLUMNS = ["GRN DATE", "GRN VOUCHER", "PORTAL", "OMS CHANNEL", "ORDER DATE", "SHIPPING LABEL PRINT DATE", "ORDER ID", "ITEM ID", "SUB ORDER ID",
           "FWD AWB", "RT AWB", "SKU", "BARCODE", "QTY", "ERP STATUS", "OMS STATUS", "ACTION", "NOTE IN OMS", "ERP REMARK"]
KEEP = ["OMS CHANNEL", "ORDER DATE", "ORDER ID", "SUB ORDER ID", "RT AWB", "OMS STATUS"]      # the order's, per AWB
KEEP_LINE = ["ACTION", "NOTE IN OMS"]                                                         # the GRN line's


def blank(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().replace({"-": "", "nan": "", "NaN": "", "None": "", "NaT": ""})


def line_key(d: pd.DataFrame) -> pd.Series:
    """One GRN line: its AWB, SKU and voucher."""
    return d["FWD AWB"] + "|" + blank(d["SKU"]).str.upper() + "|" + blank(d["GRN VOUCHER"])


def erp_lines(erp: Erp) -> pd.DataFrame:
    """Every GRN line, in the sheet's columns, the AWB in capitals; the first label print date of its AWB."""
    g = pd.DataFrame(erp.grn())
    if not len(g):
        raise RuntimeError("the ERP's GRN report has no lines")
    d = pd.DataFrame(erp.dispatch())
    printed = pd.to_datetime(d["Voucher Date"], errors="coerce").groupby(d["Order ID"].astype(str).str.strip().str.upper()).min()
    awb = blank(g["Order Tracking Id"]).str.upper()
    return pd.DataFrame({
        "GRN DATE": pd.to_datetime(g["Voucher Date"], errors="coerce"), "GRN VOUCHER": g["Voucher No."],
        "PORTAL": blank(g["Order Portal Name"]).replace("", "No Portal"), "OMS CHANNEL": "", "ORDER DATE": "",
        "SHIPPING LABEL PRINT DATE": awb.map(printed), "ORDER ID": "", "ITEM ID": blank(g["Order Item Id"]), "SUB ORDER ID": "",
        "FWD AWB": awb, "RT AWB": "", "SKU": blank(g["SKU Code"]), "BARCODE": g["Barcode"],
        "QTY": pd.to_numeric(g["Qty (Pcs.)"], errors="coerce"), "ERP STATUS": "GRN " + g["Stock Type"].astype(str).str.strip(),
        "OMS STATUS": "", "ACTION": "", "NOTE IN OMS": "", "ERP REMARK": blank(g["Trans. Remarks"])})


def last_sheet(folder: DriveFolder, work: Path) -> pd.DataFrame:
    """What the sheet knows of each AWB and GRN line already (kept when the portal is not asked again); empty on a first run."""
    cols = ["FWD AWB", "SKU", "GRN VOUCHER"] + KEEP + KEEP_LINE
    path = folder.download(FILE, work / FILE)
    if not path:
        return pd.DataFrame(columns=cols)
    d = pd.read_excel(path, sheet_name=SHEET, dtype=str)
    if "FWD AWB" not in d.columns:
        return pd.DataFrame(columns=cols)
    d = d.reindex(columns=cols).fillna("")
    d["FWD AWB"] = d["FWD AWB"].astype(str).str.strip().str.upper()
    return d[d["FWD AWB"] != ""]


def work_returns(jobs: list[dict], dry_run: bool) -> tuple[dict, bool]:
    """{AWB: result} of every AWB tried, side by side on a few OMSGuru sessions; (…, stopped) after many failures in a row."""
    local, lock = threading.local(), threading.Lock()
    results, row, stop = {}, [0], threading.Event()

    def one(job):
        if stop.is_set():
            return
        try:
            if not hasattr(local, "client"):
                local.client = OmsGuruClient.from_env()
                local.client.login()
                local.warehouses = dict(local.client.warehouses())
                local.client.set_warehouse(next(iter(local.warehouses)))
            res = accept(local.client, job["awb"], job["skus"], f"Return accepted in ERP {job['day']}", local.warehouses, dry_run, job["type"])
        except Exception as exc:  # noqa: BLE001 - one order never stops the rest
            log.warning("AWB failed: %s", type(exc).__name__)
            res = None
        with lock:
            results[job["awb"]] = res
            row[0] = row[0] + 1 if res is None or res.outcome == "Failed" else 0
            if row[0] >= FAILS_IN_A_ROW:
                stop.set()
            if len(results) % 200 == 0:
                log.info("%d of %d AWBs done", len(results), len(jobs))

    with ThreadPoolExecutor(max_workers=int(num("ERP_OMS_WORKERS", 4))) as pool:
        list(pool.map(one, jobs))
    return results, stop.is_set()


def action_of(res) -> str:
    if res is None:
        return "Not accepted: failed"
    if res.outcome in ("Accepted", "Already accepted"):
        return DONE
    if res.outcome == "SKU not on the form":
        return "ERP and OMS SKU differ: check"
    if res.outcome == "Qty above sent":
        return "ERP qty above sent: check"
    if res.outcome == "OMS shows cancelled":
        return "OMS shows cancelled: check"
    if res.outcome == "Not found in OMS":
        return res.outcome
    if res.outcome == "Would accept":
        return "To accept"
    return f"Not accepted: {res.detail or res.outcome}"[:60]


def write(out: pd.DataFrame, path: Path) -> None:
    """Sheet 2026 and a SUMMARY of formulas on it: month, then portal and month: ERP Return, OMS Accepted, Pending (qty, by GRN date)."""
    from xlsxwriter.utility import xl_rowcol_to_cell as rc
    col = {c: chr(65 + COLUMNS.index(c)) for c in ("GRN DATE", "PORTAL", "QTY", "ACTION")}
    rng = {k: f"'{SHEET}'!${v}:${v}" for k, v in col.items()}
    months = [m.to_timestamp() for m in sorted(out["GRN DATE"].dropna().dt.to_period("M").unique())]
    portals = list(out.groupby("PORTAL")["QTY"].sum().sort_values(ascending=False).index)
    month_of = out["GRN DATE"].dt.to_period("M").dt.to_timestamp()

    def value(m=None, p=None, accepted=False) -> float:
        x = out[(month_of == m) if m is not None else [True] * len(out)]
        x = x[x["PORTAL"] == p] if p is not None else x
        x = x[x["ACTION"] == DONE] if accepted else x
        return float(x["QTY"].sum())

    def formula(m=None, p=None, accepted=False) -> str:
        crit = []
        if m:
            crit += [f'{rng["GRN DATE"]},">="&{m}', f'{rng["GRN DATE"]},"<"&EDATE({m},1)']
        if p:
            crit += [f'{rng["PORTAL"]},{p}']
        if accepted:
            crit += [f'{rng["ACTION"]},"{DONE}"']
        return f'=SUMIFS({rng["QTY"]},' + ",".join(crit) + ")"

    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="dd-mmm-yy") as xw:
        out[COLUMNS].to_excel(xw, sheet_name=SHEET, index=False, freeze_panes=(1, 0))
        wb = xw.book
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter", "border": 1, "border_color": "#BFBFBF"}
        hdr = wb.add_format({**base, "bold": True, "bg_color": "#FFC000", "align": "center"})
        sub = wb.add_format({**base, "bold": True, "bg_color": "#FFE699", "align": "center"})
        ttl = wb.add_format({**base, "bold": True, "font_size": 12, "bg_color": "#FFF2CC"})
        txt, n = wb.add_format(base), wb.add_format({**base, "num_format": "#,##0"})
        mon = wb.add_format({**base, "num_format": "mmm-yy", "align": "left"})
        tt, tn = wb.add_format({**base, "bold": True, "bg_color": "#FFE699"}), wb.add_format({**base, "bold": True, "bg_color": "#FFE699", "num_format": "#,##0"})
        mh = wb.add_format({**base, "bold": True, "bg_color": "#FFC000", "align": "center", "num_format": "mmm-yy"})
        ws = xw.sheets[SHEET]
        for j, c in enumerate(COLUMNS):
            ws.write(0, j, c, hdr)
            ws.set_column(j, j, max(len(c) + 3, 14 if "AWB" in c or "ID" in c else 11))
        ws.autofilter(0, 0, len(out), len(COLUMNS) - 1)
        s = wb.add_worksheet("SUMMARY")
        s.merge_range(0, 0, 0, 3, "RETURNS BY MONTH (QTY, BY GRN DATE)", ttl)
        for j, h in enumerate(["Month", "ERP Return", "OMS Accepted", "Pending"]):
            s.write(1, j, h, hdr)
        r = 2
        for m in months:
            s.write_datetime(r, 0, m.to_pydatetime(), mon)
            e, a = value(m), value(m, accepted=True)
            s.write_formula(r, 1, formula(rc(r, 0)), n, e)
            s.write_formula(r, 2, formula(rc(r, 0), accepted=True), n, a)
            s.write_formula(r, 3, f"={rc(r, 1)}-{rc(r, 2)}", n, e - a)
            r += 1
        s.write(r, 0, "Total", tt)
        for j, v in ((1, value()), (2, value(accepted=True)), (3, value() - value(accepted=True))):
            s.write_formula(r, j, f"=SUM({rc(2, j)}:{rc(r - 1, j)})", tn, v)
        r += 3
        width = 1 + 3 * (len(months) + 1)
        s.merge_range(r, 0, r, width - 1, "RETURNS BY PORTAL AND MONTH (QTY, BY GRN DATE)", ttl)
        r += 1
        s.merge_range(r, 0, r + 1, 0, "Portal", hdr)
        for i, m in enumerate(months):
            s.merge_range(r, 1 + 3 * i, r, 3 + 3 * i, m.to_pydatetime(), mh)
        s.merge_range(r, 1 + 3 * len(months), r, 3 + 3 * len(months), "Total", hdr)
        for i in range(len(months) + 1):
            for j, h in enumerate(["ERP Return", "OMS Accepted", "Pending"]):
                s.write(r + 1, 1 + 3 * i + j, h, sub)
        head, top = r, r + 2
        r = top
        for p in portals:
            s.write(r, 0, p, txt)
            for i, m in enumerate(months):
                c = 1 + 3 * i
                e, a = value(m, p), value(m, p, True)
                s.write_formula(r, c, formula(rc(head, c, True, True), rc(r, 0, False, True)), n, e)
                s.write_formula(r, c + 1, formula(rc(head, c, True, True), rc(r, 0, False, True), True), n, a)
                s.write_formula(r, c + 2, f"={rc(r, c)}-{rc(r, c + 1)}", n, e - a)
            c = 1 + 3 * len(months)
            for k, v in enumerate((value(p=p), value(p=p, accepted=True), value(p=p) - value(p=p, accepted=True))):
                s.write_formula(r, c + k, "=" + "+".join(rc(r, 1 + 3 * i + k) for i in range(len(months))), n, v)
            r += 1
        s.write(r, 0, "Total", tt)
        for c in range(1, width):
            i, k = (c - 1) // 3, (c - 1) % 3
            m = months[i] if i < len(months) else None
            s.write_formula(r, c, f"=SUM({rc(top, c)}:{rc(r - 1, c)})", tn, (value(m), value(m, accepted=True), value(m) - value(m, accepted=True))[k])
        s.set_column(0, 0, 14)
        s.set_column(1, width - 1, 12)
        s.freeze_panes(0, 1)
        s.activate()


def run(args) -> int:
    work = Path(tempfile.mkdtemp(prefix="erp_oms_return_"))
    folder = DriveFolder(agent_work_id())
    erp = Erp.from_env()
    erp.login()
    out = erp_lines(erp)
    prev = last_sheet(folder, work)
    known = prev.drop_duplicates("FWD AWB", keep="last").set_index("FWD AWB")
    has_id = out["FWD AWB"] != ""
    for c in KEEP:
        out.loc[has_id, c] = out.loc[has_id, "FWD AWB"].map(known[c]).fillna("").values
    known_line = prev.assign(k=line_key(prev).astype(object)).drop_duplicates("k", keep="last").set_index("k")
    keys = line_key(out)
    for c in KEEP_LINE:
        out.loc[has_id, c] = keys[has_id].map(known_line[c]).fillna("").values
    out.loc[~has_id, "ACTION"] = NO_ID
    complete = out["GRN DATE"].notna() & (out["QTY"] > 0) & (out["SKU"] != "")
    out.loc[has_id & ~complete & (out["ACTION"] != DONE), "ACTION"] = NO_DATA

    pending = has_id & complete & (out["ACTION"] != DONE)
    todo = out[pending].copy()
    todo["k"] = todo["SKU"].str.upper()
    jobs = []
    for awb, g in todo.groupby("FWD AWB"):
        jobs.append({"awb": awb, "skus": {k: int(v) for k, v in g.groupby("k")["QTY"].sum().items()}, "day": f"{g['GRN DATE'].max():%d-%m-%Y}", "type": g["ERP STATUS"].iloc[-1]})
    jobs = jobs[:args.limit] if args.limit else jobs
    log.info("GRN lines %d, AWBs to try %d", len(out), len(jobs))
    results, stopped = work_returns(jobs, args.dry_run or args.no_upload)
    accepted_now = 0
    for awb, res in results.items():
        same = out["FWD AWB"] == awb
        at = same & pending                     # lines already accepted stay as they are
        out.loc[at, "ACTION"] = action_of(res)
        if res is None:
            continue
        accepted_now += res.outcome == "Accepted"
        if res.done:                            # some forms went through, others were refused
            out.loc[at & out["SKU"].str.upper().isin(res.done), "ACTION"] = DONE
        for col, val in (("ORDER ID", res.order_no), ("ORDER DATE", res.order_date), ("OMS CHANNEL", res.channel), ("RT AWB", res.return_awb), ("OMS STATUS", res.status)):
            if val:
                out.loc[same, col] = val
        if res.note:
            day = next(j["day"] for j in jobs if j["awb"] == awb)
            out.loc[at & (out["ACTION"] == DONE), "NOTE IN OMS"] = f"Return accepted in ERP {day}"
    out["ACTION"] = out["ACTION"].replace("", "To accept")
    out = out.sort_values(["GRN DATE", "GRN VOUCHER"]).reset_index(drop=True)

    path = output_dir("erp_oms_return") / FILE
    write(out, path)
    if not args.no_upload and not args.dry_run:
        folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    qty = out.groupby("ACTION")["QTY"].sum()
    done, total = int(qty.get(DONE, 0)), int(out["QTY"].sum())
    others = {k: int(v) for k, v in qty.items() if k not in (DONE, NO_ID)}
    no_qty = int(out["QTY"].isna().sum())
    lines = ["↩️ <b>ERP to OMSGuru returns</b>", f"<i>{date.today():%d %b %Y}</i>", "",
             f"Accepted today: <b>{accepted_now:,}</b> of {len(jobs):,} AWBs tried",
             f"ERP returns {total:,}, OMS accepted {done:,}, pending {total - done:,}",
             f"No id in the ERP: {int(qty.get(NO_ID, 0)):,}"]
    if no_qty:
        lines.append(f"GRN lines with no qty (left out of the totals): {no_qty:,}")
    lines += [f"{telegram.esc(k[:44])}: {v:,}" for k, v in sorted(others.items(), key=lambda x: -x[1])[:6]]
    if stopped:
        lines.append(f"\n❌ Stopped after {FAILS_IN_A_ROW} failures in a row: the next run goes on")
    if args.dry_run or args.no_upload:
        lines.append("\n<i>test run: nothing accepted, Drive not changed</i>")
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    return 1 if stopped else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py erp-oms-return", description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true", help="nothing accepted, Drive not changed")
    p.add_argument("--no-upload", action="store_true", help="test run: nothing accepted, Drive not changed")
    p.add_argument("--limit", type=int, default=0, help="at most this many AWBs (a test)")
    return run_bot("ERP to OMSGuru returns", p, run, argv)
