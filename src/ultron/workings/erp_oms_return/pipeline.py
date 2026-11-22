"""ERP to OMSGuru returns: a return booked in the ERP's GRN is accepted in OMSGuru, as Good, the same evening.

Every GRN line of the ERP (report 58) goes on Drive AGENT WORK/ERP TO OMSGURU RETURN.xlsx, sheet 2026, with its OMSGuru state; SUMMARY
adds it up by month and by portal and month, in formulas on that sheet. Each AWB not yet accepted is tried (accept.py): accepted as
Good, the note "Return accepted in ERP <GRN date>" on the order. Never a Putaway, so OMSGuru's stock does not change.

Not accepted, and said why on the sheet: a line with no id in the ERP (it cannot be tied to an order), an AWB OMSGuru does not know, a
SKU the ERP booked that the order does not have (maybe the wrong item came back), a qty above what was sent, a GRN line with no date,
qty or SKU. ACTION is kept per GRN line, so a later GRN line of an AWB already accepted is still worked.

Tables are Polars; the workbook is written by xlsxwriter.
"""
from __future__ import annotations

import argparse
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import polars as pl

from ..core import telegram
from ..core.app import run_bot
from ..core.config import num, output_dir
from ..core.drive import DriveFolder, agent_folder
from ..portals.erp import Erp
from .accept import accept
from ..core import clients

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


GRN_TEXT = ["Voucher No.", "Stock Type", "Barcode", "SKU Code", "Order Portal Name", "Order Tracking Id", "Order Item Id",
            "Trans. Remarks", "Qty (Pcs.)"]


def blank(e: pl.Expr) -> pl.Expr:
    """A field as stripped text; empty, "-" and missing-value words as ""."""
    t = e.cast(pl.Utf8).str.strip_chars()
    return pl.when(t.is_null() | t.is_in(["-", "nan", "NaN", "None", "NaT"])).then(pl.lit("")).otherwise(t)


def line_key() -> pl.Expr:
    """One GRN line: its AWB, SKU and voucher."""
    return pl.concat_str([pl.col("FWD AWB"), blank(pl.col("SKU")).str.to_uppercase(), blank(pl.col("GRN VOUCHER"))], separator="|")


def report_table(rows: list[dict], text: list[str], when: list[str]) -> pl.DataFrame:
    """An ERP report's rows (ultron.workings.portals.erp) as a typed table: the fields named in `text` as text, those in
    `when` as datetimes (already datetimes in the answer when they were ISO; anything else is empty)."""
    schema = {**{c: pl.Utf8 for c in text}, **{c: pl.Datetime("us") for c in when}}
    cols = {c: pl.Series(c, [r.get(c) for r in rows], dtype=dt, strict=False) for c, dt in schema.items()}
    return pl.DataFrame(cols)


def erp_lines(erp: Erp) -> pl.DataFrame:
    """Every GRN line, in the sheet's columns, the AWB in capitals; the first label print date of its AWB."""
    rows = erp.grn()
    if not rows:
        raise RuntimeError("the ERP's GRN report has no lines")
    g = report_table(rows, GRN_TEXT, ["Voucher Date"])
    d = report_table(erp.dispatch(), ["Order ID"], ["Voucher Date"])
    printed = (d.select(pl.col("Order ID").str.strip_chars().str.to_uppercase().alias("FWD AWB"),
                        pl.col("Voucher Date").alias("SHIPPING LABEL PRINT DATE"))
                .group_by("FWD AWB").agg(pl.col("SHIPPING LABEL PRINT DATE").min()))
    empty = pl.lit("")
    out = g.select(
        pl.col("Voucher Date").alias("GRN DATE"), pl.col("Voucher No.").alias("GRN VOUCHER"),
        pl.when(blank(pl.col("Order Portal Name")) == "").then(pl.lit("No Portal")).otherwise(blank(pl.col("Order Portal Name"))).alias("PORTAL"),
        empty.alias("OMS CHANNEL"), empty.alias("ORDER DATE"), empty.alias("ORDER ID"), blank(pl.col("Order Item Id")).alias("ITEM ID"),
        empty.alias("SUB ORDER ID"), blank(pl.col("Order Tracking Id")).str.to_uppercase().alias("FWD AWB"), empty.alias("RT AWB"),
        blank(pl.col("SKU Code")).alias("SKU"), pl.col("Barcode").alias("BARCODE"),
        pl.col("Qty (Pcs.)").str.strip_chars().cast(pl.Float64, strict=False).alias("QTY"),
        (pl.lit("GRN ") + pl.col("Stock Type").str.strip_chars()).alias("ERP STATUS"),      # no stock type: empty
        empty.alias("OMS STATUS"), empty.alias("ACTION"), empty.alias("NOTE IN OMS"), blank(pl.col("Trans. Remarks")).alias("ERP REMARK"))
    return out.join(printed, on="FWD AWB", how="left", maintain_order="left").select(COLUMNS)


def last_sheet(folder: DriveFolder, work: Path) -> pl.DataFrame:
    """What the sheet knows of each AWB and GRN line already (kept when the portal is not asked again); empty on a first run."""
    from ..core.tables import read_excel_text
    cols = ["FWD AWB", "SKU", "GRN VOUCHER"] + KEEP + KEEP_LINE
    none = pl.DataFrame(schema={c: pl.Utf8 for c in cols})
    path = folder.download(FILE, work / FILE)
    if not path:
        return none
    d = read_excel_text(path, SHEET)
    if "FWD AWB" not in d.columns:
        return none
    d = d.select(*[(pl.col(c) if c in d.columns else pl.lit(None, dtype=pl.Utf8)).fill_null("").alias(c) for c in cols])
    return d.with_columns(pl.col("FWD AWB").str.strip_chars().str.to_uppercase()).filter(pl.col("FWD AWB") != "")


def with_known(out: pl.DataFrame, prev: pl.DataFrame) -> pl.DataFrame:
    """What the sheet knew: the order's fields per AWB (KEEP), the line's per GRN line (KEEP_LINE); lines with no id say so,
    lines with no date, qty or SKU say so too."""
    has_id = pl.col("FWD AWB") != ""
    by_awb = prev.unique("FWD AWB", keep="last", maintain_order=True).select("FWD AWB", *[pl.col(c).alias(f"_k.{c}") for c in KEEP])
    by_line = (prev.with_columns(line_key().alias("_line")).unique("_line", keep="last", maintain_order=True)
                   .select("_line", *[pl.col(c).alias(f"_k.{c}") for c in KEEP_LINE]))
    out = (out.with_columns(line_key().alias("_line"))
              .join(by_awb, on="FWD AWB", how="left", maintain_order="left")
              .join(by_line, on="_line", how="left", maintain_order="left")
              .with_columns(*[pl.when(has_id).then(pl.col(f"_k.{c}").fill_null("")).otherwise(pl.col(c)).alias(c) for c in KEEP + KEEP_LINE])
              .drop("_line", *[f"_k.{c}" for c in KEEP + KEEP_LINE]))
    complete = pl.col("GRN DATE").is_not_null() & (pl.col("QTY") > 0).fill_null(False) & (pl.col("SKU") != "")
    action = (pl.when(~has_id).then(pl.lit(NO_ID))
                .when(~complete & (pl.col("ACTION") != DONE)).then(pl.lit(NO_DATA)).otherwise(pl.col("ACTION")))
    return out.with_columns(action.alias("ACTION"))


def pending() -> pl.Expr:
    """GRN lines still to be accepted: with an id, a date, qty and SKU, not accepted yet."""
    complete = pl.col("GRN DATE").is_not_null() & (pl.col("QTY") > 0).fill_null(False) & (pl.col("SKU") != "")
    return (pl.col("FWD AWB") != "") & complete & (pl.col("ACTION") != DONE)


def jobs_of(out: pl.DataFrame) -> list[dict]:
    """One job per AWB with lines to accept (AWBs A to Z): its SKUs (upper case) and units, the last GRN day, the GRN type."""
    todo = out.filter(pending()).with_columns(pl.col("SKU").str.to_uppercase().alias("_k"))
    skus = (todo.group_by("FWD AWB", "_k").agg(pl.col("QTY").sum()).sort("FWD AWB", "_k")
                .group_by("FWD AWB", maintain_order=True).agg("_k", "QTY"))
    awbs = todo.group_by("FWD AWB", maintain_order=True).agg(pl.col("GRN DATE").max().alias("day"),
                                                           pl.col("ERP STATUS").last().alias("type"))
    j = skus.join(awbs, on="FWD AWB", how="left").sort("FWD AWB")
    return [{"awb": awb, "skus": {k: int(q) for k, q in zip(ks, qs)}, "day": f"{day:%d-%m-%Y}", "type": kind}
            for awb, ks, qs, day, kind in j.iter_rows()]


def with_results(out: pl.DataFrame, results: dict, jobs: list[dict]) -> pl.DataFrame:
    """The tried AWBs' answers on their lines: ACTION of the lines still pending, the SKUs that went through, the order's fields
    on every line of the AWB, the note on the lines accepted. Lines with no ACTION yet are "To accept"."""
    day_of = {j["awb"]: j["day"] for j in jobs}
    rows = [{"FWD AWB": awb, "_action": action_of(res), "_done": sorted(res.done) if res else [],
             "_note": bool(res and res.note), "_day": day_of.get(awb, ""),
             **{f"_r.{c}": (getattr(res, a) or None) if res else None for c, a in RESULT_FIELDS}}
            for awb, res in results.items()]
    schema = {"FWD AWB": pl.Utf8, "_action": pl.Utf8, "_done": pl.List(pl.Utf8), "_note": pl.Boolean, "_day": pl.Utf8,
              **{f"_r.{c}": pl.Utf8 for c, _ in RESULT_FIELDS}}
    r = pl.DataFrame(rows, schema=schema)
    tried = pl.col("_action").is_not_null()
    at = tried & pl.col("_pending")
    action = (pl.when(at & pl.col("SKU").str.to_uppercase().is_in(pl.col("_done")).fill_null(False)).then(pl.lit(DONE))
                .when(at).then(pl.col("_action")).otherwise(pl.col("ACTION")))
    out = (out.with_columns(pending().alias("_pending")).join(r, on="FWD AWB", how="left", maintain_order="left")
              .with_columns(action.alias("ACTION"),
                            *[pl.coalesce(pl.col(f"_r.{c}"), pl.col(c)).alias(c) for c, _ in RESULT_FIELDS]))
    note = at & pl.col("_note").fill_null(False) & (pl.col("ACTION") == DONE)
    out = out.with_columns(pl.when(note).then(pl.lit("Return accepted in ERP ") + pl.col("_day")).otherwise(pl.col("NOTE IN OMS"))
                             .alias("NOTE IN OMS"),
                           pl.when(pl.col("ACTION") == "").then(pl.lit("To accept")).otherwise(pl.col("ACTION")).alias("ACTION"))
    return out.select(COLUMNS).sort(["GRN DATE", "GRN VOUCHER"], nulls_last=True, maintain_order=True)


RESULT_FIELDS = [("ORDER ID", "order_no"), ("ORDER DATE", "order_date"), ("OMS CHANNEL", "channel"), ("RT AWB", "return_awb"),
                 ("OMS STATUS", "status")]


def work_returns(jobs: list[dict], dry_run: bool) -> tuple[dict, bool]:
    """{AWB: result} of every AWB tried, side by side on a few OMSGuru sessions; (…, stopped) after many failures in a row."""
    local, lock = threading.local(), threading.Lock()
    results, row, stop = {}, [0], threading.Event()

    def one(job):
        if stop.is_set():
            return
        try:
            if not hasattr(local, "client"):
                local.client = clients.omsguru()
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


def write(out: pl.DataFrame, path: Path) -> None:
    """Sheet 2026 and a SUMMARY of formulas on it: month, then portal and month: ERP Return, OMS Accepted, Pending (qty, by GRN date)."""
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell as rc
    col = {c: chr(65 + COLUMNS.index(c)) for c in ("GRN DATE", "PORTAL", "QTY", "ACTION")}
    rng = {k: f"'{SHEET}'!${v}:${v}" for k, v in col.items()}
    t = out.with_columns(pl.col("GRN DATE").dt.truncate("1mo").alias("_m"), (pl.col("ACTION") == DONE).alias("_a"),
                         pl.col("QTY").fill_null(0).alias("_q"))
    months = sorted(t["_m"].drop_nulls().unique().to_list())
    portals = (t.group_by("PORTAL").agg(pl.col("_q").sum()).sort("PORTAL")
                .sort("_q", descending=True, maintain_order=True)["PORTAL"].to_list())   # most qty first, equal qty A to Z
    sums = {(m, p, a): q for m, p, a, q in t.group_by("_m", "PORTAL", "_a").agg(pl.col("_q").sum()).iter_rows()}

    def value(m=None, p=None, accepted=False) -> float:
        return float(sum(q for (mm, pp, aa), q in sums.items()
                         if (m is None or mm == m) and (p is None or pp == p) and (aa or not accepted)))

    def formula(m=None, p=None, accepted=False) -> str:
        crit = []
        if m:
            crit += [f'{rng["GRN DATE"]},">="&{m}', f'{rng["GRN DATE"]},"<"&EDATE({m},1)']
        if p:
            crit += [f'{rng["PORTAL"]},{p}']
        if accepted:
            crit += [f'{rng["ACTION"]},"{DONE}"']
        return f'=SUMIFS({rng["QTY"]},' + ",".join(crit) + ")"

    wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "strings_to_formulas": False, "strings_to_urls": False})
    base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter", "border": 1, "border_color": "#BFBFBF"}
    hdr = wb.add_format({**base, "bold": True, "bg_color": "#FFC000", "align": "center"})
    sub = wb.add_format({**base, "bold": True, "bg_color": "#FFE699", "align": "center"})
    ttl = wb.add_format({**base, "bold": True, "font_size": 12, "bg_color": "#FFF2CC"})
    txt, n = wb.add_format(base), wb.add_format({**base, "num_format": "#,##0"})
    mon = wb.add_format({**base, "num_format": "mmm-yy", "align": "left"})
    tt, tn = wb.add_format({**base, "bold": True, "bg_color": "#FFE699"}), wb.add_format({**base, "bold": True, "bg_color": "#FFE699", "num_format": "#,##0"})
    mh = wb.add_format({**base, "bold": True, "bg_color": "#FFC000", "align": "center", "num_format": "mmm-yy"})
    day = wb.add_format({"num_format": "dd-mmm-yy"})

    ws = wb.add_worksheet(SHEET)
    for j, c in enumerate(COLUMNS):
        ws.write(0, j, c, hdr)
        ws.set_column(j, j, max(len(c) + 3, 14 if "AWB" in c or "ID" in c else 11))
    for i, row in enumerate(out.select(COLUMNS).iter_rows(), start=1):
        for j, v in enumerate(row):
            if v is None or v == "" or (isinstance(v, float) and v != v):
                continue
            if isinstance(v, datetime):
                ws.write_datetime(i, j, v, day)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                ws.write_number(i, j, v)
            else:
                ws.write_string(i, j, str(v))
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, out.height, len(COLUMNS) - 1)

    s = wb.add_worksheet("SUMMARY")
    s.merge_range(0, 0, 0, 3, "RETURNS BY MONTH (QTY, BY GRN DATE)", ttl)
    for j, h in enumerate(["Month", "ERP Return", "OMS Accepted", "Pending"]):
        s.write(1, j, h, hdr)
    r = 2
    for m in months:
        s.write_datetime(r, 0, m, mon)
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
        s.merge_range(r, 1 + 3 * i, r, 3 + 3 * i, m, mh)
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
    wb.close()


def message(out: pl.DataFrame, results: dict, jobs: list[dict], stopped: bool, test: bool) -> str:
    qty = dict(out.group_by("ACTION").agg(pl.col("QTY").fill_null(0).sum()).iter_rows())
    done, total = int(qty.get(DONE, 0)), int(out["QTY"].fill_null(0).sum())
    others = sorted(((k, int(v)) for k, v in qty.items() if k not in (DONE, NO_ID)), key=lambda x: (-x[1], x[0]))
    accepted_now = sum(1 for res in results.values() if res is not None and res.outcome == "Accepted")
    no_qty = int(out["QTY"].is_null().sum())
    lines = ["↩️ <b>ERP to OMSGuru returns</b>", f"<i>{date.today():%d %b %Y}</i>", "",
             f"Accepted today: <b>{accepted_now:,}</b> of {len(jobs):,} AWBs tried",
             f"ERP returns {total:,}, OMS accepted {done:,}, pending {total - done:,}",
             f"No id in the ERP: {int(qty.get(NO_ID, 0)):,}"]
    if no_qty:
        lines.append(f"GRN lines with no qty (left out of the totals): {no_qty:,}")
    lines += [f"{telegram.esc(k[:44])}: {v:,}" for k, v in others[:6]]
    if stopped:
        lines.append(f"\n❌ Stopped after {FAILS_IN_A_ROW} failures in a row: the next run goes on")
    if test:
        lines.append("\n<i>test run: nothing accepted, Drive not changed</i>")
    return "\n".join(lines)


def run(args) -> int:
    work = Path(tempfile.mkdtemp(prefix="erp_oms_return_"))
    folder = agent_folder()
    erp = Erp.from_env()
    erp.login()
    out = with_known(erp_lines(erp), last_sheet(folder, work))
    jobs = jobs_of(out)
    jobs = jobs[:args.limit] if args.limit else jobs
    log.info("GRN lines %d, AWBs to try %d", out.height, len(jobs))
    results, stopped = work_returns(jobs, args.dry_run or args.no_upload)
    out = with_results(out, results, jobs)

    path = output_dir("erp_oms_return") / FILE
    write(out, path)
    if not args.no_upload and not args.dry_run:
        folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    text = message(out, results, jobs, stopped, args.dry_run or args.no_upload)
    print(text) if args.no_telegram else telegram.send(text)
    return 1 if stopped else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py erp-oms-return", description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true", help="nothing accepted, Drive not changed")
    p.add_argument("--no-upload", action="store_true", help="test run: nothing accepted, Drive not changed")
    p.add_argument("--limit", type=int, default=0, help="at most this many AWBs (a test)")
    return run_bot("ERP to OMSGuru returns", p, run, argv)
