"""Myntra colour grouping: the owner's grouping checker (engine.py, unchanged rules) run by the bot.

Inputs:
  Drive AGENT WORK/MYNTRA/LISTING GROUPING/GROUPING SHEET.xlsx  the groups the owner wants (one tab per
        category, column A = MY SKUs, a blank row between groups) - kept by the owner
  .../LISTING GROUPING/portal template.xlsx                     Myntra's grouping upload template
  AGENT WORK/MYNTRA/MYNTRA DAILY REPORTS/<day>/<ACC> Listings <day>.csv   the newest listings report of
        every account (myntra-reports, 10 AM daily)
  AGENT WORK/BUSINESS REPORTING/MasterSheet.xlsx               the SKU master
  AGENT WORK/PORTAL REPORTS/MYNTRA (ORDER REPORTs)              sales: the last SALE_MONTHS (3) months'
        order lines delivered (C) or on the way (SH), per account and style
  www.myntra.com/gateway/v2/product/<style>                     each style's live colour group: the
        engine's spider on the office PC, else (refused, or the PC off: MYNTRA_GROUPING_VIA=phone)
        Ultron Phone, which asks the same website API from a mobile line

Output (Drive AGENT WORK/MYNTRA/LISTING GROUPING):
  MYNTRA GROUPING MASTER.xlsx       one sheet per account (every group, style and remark: DONE, NOT DONE,
                                    DONE - EXTRA IN PORTAL, ...; a style in no group is NOT DONE too), on a NOT DONE
                                    style its newest job and reason + Summary; replaced each run
  GROUPING REASONS.xlsx             every row of every job's result report, what the portal said per style
  HISTORY/GROUPING_ACCOUNT_WISE_<date>.xlsx   the day's check with all its columns (MISSING IN PORTAL, PORTAL GROUP ...)
  TEMPLATES/<date>/ACC-<seller id>/<unique id>_<brand>_<article>.xlsx   one upload file per pending
                                    group (Unique ID, Group Type, Style ID), ready to submit on Myntra
Telegram: per account the groups, done and pending, and the template files made.

--status: only the portal's upload jobs are read again (8 PM daily, Myntra approves during the day): GROUPING
SUBMISSIONS.xlsx, GROUPING REASONS.xlsx and the job columns of the master. myntra.com is not asked, so GROUPING REMARK stays as of the
last full run. --only-changes: nothing written or sent unless a job changed.
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num
from ..core.drive import DriveFolder

log = logging.getLogger("bindal.myntra_grouping")

FOLDER = ("MYNTRA", "LISTING GROUPING")
DAILY = ("MYNTRA", "MYNTRA DAILY REPORTS")
SELLER_OF = {"MAIN": "19170", "DBCC": "32207", "FMCC": "35426"}
ACCOUNT_OF = {v: k for k, v in SELLER_OF.items()}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def agent_work() -> DriveFolder:
    return DriveFolder(env("AGENT_WORK_FOLDER_ID", pr.AGENT_WORK))


def subfolder(root: DriveFolder, names, create: bool = False) -> DriveFolder | None:
    f = root
    for n in names:
        f = f.subfolder(n, create=create)
        if f is None:
            return None
    return f


def latest_listings(dest: Path) -> dict[str, Path]:
    """The newest day folder of MYNTRA DAILY REPORTS holding a listings report, per account."""
    daily = subfolder(agent_work(), DAILY)
    if not daily:
        raise RuntimeError("AGENT WORK/MYNTRA/MYNTRA DAILY REPORTS not found")
    days = sorted((n for n in daily.children() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n)), reverse=True)
    found: dict[str, Path] = {}
    for day in days[:10]:
        folder = daily.subfolder(day)
        for name in folder.children():
            m = re.match(r"^(MAIN|DBCC|FMCC) Listings (\d{4}-\d{2}-\d{2})\.csv$", name)
            if m and m.group(1) not in found:
                # engine.py reads *Seller_Listings_Report_<seller id>.csv
                found[m.group(1)] = folder.download(name, dest / f"{m.group(2)}_Seller_Listings_Report_{SELLER_OF[m.group(1)]}.csv")
        if len(found) == len(SELLER_OF):
            break
    if not found:
        raise RuntimeError("no listings report in MYNTRA DAILY REPORTS (myntra-reports, 10 AM)")
    return found


def sales_counts(sku_to_style: dict, dest: Path, months: int) -> dict[tuple[str, str], int]:
    """{(seller id, style id): order lines delivered or on the way} over the last months' order
    reports in PORTAL REPORTS (in place of the hand-run tool's sales export)."""
    counts: dict[tuple[str, str], int] = {}
    month = date.today().replace(day=1)
    for _ in range(months):
        month = (month - timedelta(days=1)).replace(day=1)
        for f in pr.load("MYNTRA", month, "sale", dest / f"orders_{month:%Y%m}"):
            df = pd.read_csv(f, dtype=str, usecols=lambda c: c in ("seller id", "style id", "order status", "order line id"))
            df = df[df["order status"].isin(["C", "SH"])].drop_duplicates("order line id")
            for (seller, style), n in df.groupby(["seller id", "style id"]).size().items():
                key = (str(seller).replace(".0", ""), str(style).replace(".0", ""))
                counts[key] = counts.get(key, 0) + int(n)
    return counts


def omsguru_inventory(dest: Path) -> Path | None:
    """OMSGuru's stock of every warehouse, summed per SKU (as the stock-out alert reads it), as the
    inventory file engine.load_inventory takes (SKU, Qty); None when OMSGuru cannot be read."""
    from ...portals.omsguru import OmsGuruClient
    from ..stock.pipeline import stock_of
    try:
        client = OmsGuruClient.from_env()
        client.login()
        blobs = []
        for wh in list(client.warehouses()) or [None]:
            if wh:
                client.set_warehouse(wh)
            blobs.append(client.export_inventory(wait_minutes=num("STOCK_EXPORT_WAIT_MINUTES", 12)))
    except Exception as exc:  # noqa: BLE001 - the report goes on without INV
        log.warning("OMSGuru inventory not read: %s", exc)
        return None
    stock = stock_of(blobs)
    path = dest / "omsguru_inventory.csv"
    pd.DataFrame({"SKU": list(stock), "Qty": list(stock.values())}).to_csv(path, index=False)
    log.info("OMSGuru inventory: %d SKUs, %d units", len(stock), sum(stock.values()))
    return path


def phone_records(style_ids: list[str]) -> dict:
    """The styles' colour groups through Ultron Phone (the Android app on a mobile line asks the same
    www.myntra.com product API as the website), in the engine's cache shape."""
    from ..core import phone
    got = phone.run_job("myntra_style", [int(s) for s in style_ids], wait_minutes=num("GROUPING_PHONE_MINUTES", 40))
    out, old_app = {}, 0
    now = datetime.now().isoformat(timespec="seconds")
    for sid in style_ids:
        a = got.get(str(sid))
        if isinstance(a, dict):
            if "colours" not in a:
                old_app += 1
                continue
            out[sid] = {"http": 200, "fetched": now, "live": True, "color": a.get("baseColour") or "",
                        "colours": [{"styleId": str(c.get("styleId")), "label": c.get("label", "")} for c in a.get("colours") or []]}
        elif a == "NOT FOUND":
            out[sid] = {"http": 404, "fetched": now, "live": False, "colours": []}
    if old_app and not any(r.get("live") for r in out.values()):
        raise RuntimeError("Ultron Phone sends no colour groups yet: update the app on the phone (Ultron Phone build after 2 Nov 2026)")
    return out


def run_status(args) -> int:
    """The upload jobs read again, without the check on myntra.com."""
    from . import submit as sb
    work = Path(tempfile.mkdtemp(prefix="myntra_grouping_"))
    lg = subfolder(agent_work(), FOLDER, create=True)
    old = sb.read_record(lg.download(sb.RECORD, work / "old_record.xlsx"))
    record, problems = sb.sync_jobs(old)
    reasons = sb.read_reasons(lg.download(sb.REASONS, work / "old_reasons.xlsx"))
    record, reasons, more = sb.update_reasons(record, reasons)
    problems += more
    changed = sb.changed_jobs(old, record)
    if args.only_changes and not changed and not problems:
        log.info("No grouping job changed")
        return 0
    master = lg.download("MYNTRA GROUPING MASTER.xlsx", work / "MYNTRA GROUPING MASTER.xlsx")
    if not master:
        raise RuntimeError("MYNTRA GROUPING MASTER.xlsx not found in AGENT WORK/MYNTRA/LISTING GROUPING")
    states = sb.apply(master, record, reasons)
    lines = [f"🎨 <b>Myntra grouping status</b> {datetime.now():%Y-%m-%d %H:%M}",
             "<i>the portal's jobs read again; DONE / NOT DONE are as of the last full check</i>", ""]
    lines.append("Changed: " + (" · ".join(f"{s} {n}" for s, n in changed.most_common()) if changed else "no job"))
    lines += [f"<b>{ACCOUNT_OF.get(a, a)}</b> pending groups: {sb.state_line(t)}" for a, t in states.items()]
    lines += [f"❌ {telegram.esc(x)}" for x in problems[:15]]
    if args.no_upload:
        lines.append("\n<i>test run: Drive not changed</i>")
        print("\n".join(lines))
        Path("output/myntra_grouping").mkdir(parents=True, exist_ok=True)
        shutil.copy2(master, Path("output/myntra_grouping") / master.name)
        sb.write_record(record, Path("output/myntra_grouping") / sb.RECORD)
        sb.write_reasons(reasons, Path("output/myntra_grouping") / sb.REASONS)
        return 0
    lg.put(master, XLSX)
    lg.put(sb.write_record(record, work / sb.RECORD), XLSX)
    lg.put(sb.write_reasons(reasons, work / sb.REASONS), XLSX)
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    return 0


def run(args) -> int:
    if args.status:
        return run_status(args)
    from . import engine as e
    from . import submit as sb
    work = Path(tempfile.mkdtemp(prefix="myntra_grouping_"))
    for sub in ("input", "sale", "output"):
        (work / sub).mkdir()
    lg = subfolder(agent_work(), FOLDER, create=True)
    if not lg.download("GROUPING SHEET.xlsx", work / "input" / "GROUPING SHEET.xlsx"):
        raise RuntimeError("GROUPING SHEET.xlsx not found in AGENT WORK/MYNTRA/LISTING GROUPING")
    lg.download("portal template.xlsx", work / "portal template.xlsx")
    br = agent_work().subfolder("BUSINESS REPORTING")
    if not br or not br.download("MasterSheet.xlsx", work / "MasterSheet.xlsx"):
        raise RuntimeError("MasterSheet.xlsx not found in AGENT WORK/BUSINESS REPORTING")
    listings = latest_listings(work / "input")
    log.info("Listings: %s", {a: p.name for a, p in listings.items()})

    # the engine's folders -> this run's work folder
    e.BASE_DIR, e.INPUT_DIR, e.SALE_DIR, e.OUTPUT_DIR = str(work), str(work / "input"), str(work / "sale"), str(work / "output")
    e.MASTER_FILE, e.GROUPING_FILE = str(work / "MasterSheet.xlsx"), str(work / "input" / "GROUPING SHEET.xlsx")
    e.CACHE_FILE, e.PORTAL_TEMPLATE_FILE = str(work / "output" / "portal_cache.json"), str(work / "portal template.xlsx")
    e.TEMPLATE_DIR = str(work / "output" / "templates")

    groups = e.load_grouping_sheet(e.GROUPING_FILE)
    master = e.load_master(e.MASTER_FILE)
    styles, sku_to_style = e.load_listings(master)
    wanted = {b.strip().lower() for b in e.BRANDS}
    styles = styles[styles["brand"].str.strip().str.lower().isin(wanted)].reset_index(drop=True)
    accounts = sorted(styles["account"].unique())
    sales = sales_counts(sku_to_style, work / "sale", int(num("GROUPING_SALE_MONTHS", 3)))
    inv_file = omsguru_inventory(work / "input")
    inventory = e.load_inventory(master) if inv_file else None
    group_skus = {sku for _, skus in groups for sku in skus}
    to_check = sorted(styles.loc[styles["my_sku"].isin(group_skus), "style_id"].unique())
    cache: dict = {}
    log.info("%d groups, %d accounts, %d styles to check on myntra.com", len(groups), len(accounts), len(to_check))
    via = (env("MYNTRA_GROUPING_VIA") or "").lower()
    if via != "phone":
        e.fetch_portal(to_check, cache, int(num("GROUPING_CONCURRENCY", 16)))
    missing = [sid for sid in to_check if sid not in cache]
    if to_check and (via == "phone" or len(missing) > len(to_check) * 0.2):
        log.warning("myntra.com answered %d of %d styles here: asking Ultron Phone for the rest",
                    len(to_check) - len(missing), len(to_check))
        cache.update(phone_records(missing))
        missing = [sid for sid in to_check if sid not in cache]
    if to_check and len(missing) > len(to_check) * 0.2:
        raise RuntimeError(f"myntra.com answered for only {len(to_check) - len(missing)} of {len(to_check)} styles: "
                           "report not written (a blocked run would mark live groups as not live)")
    account_rows = {a: e.build_account_rows(a, groups, styles, master, sales, inventory, cache) for a in accounts}
    e.apply_cross_account_done(account_rows)
    stamp = f"{datetime.now():%Y-%m-%d}"
    report = work / "output" / f"GROUPING_ACCOUNT_WISE_{stamp}.xlsx"
    for rows in account_rows.values():
        e.pending_group_styles(rows)          # names on the rows the styles an upload cannot move
    e.write_report(str(report), account_rows)
    e.write_portal_templates(account_rows, stamp)

    # the portal's upload jobs, the pending groups submitted (only --submit), the record into the report
    record = sb.read_record(lg.download(sb.RECORD, work / "old_record.xlsx"))
    record, problems = sb.sync_jobs(record)
    submitted, skipped = 0, {}
    if args.submit and not args.no_upload:
        record, bad, submitted, skipped = sb.submit(Path(e.TEMPLATE_DIR) / stamp, record, args.submit_limit)
        problems += bad
        record, more = sb.sync_jobs(record)
        problems += more
    reasons = sb.read_reasons(lg.download(sb.REASONS, work / "old_reasons.xlsx"))
    record, reasons, more = sb.update_reasons(record, reasons)
    problems += more
    master_file = report.with_name("MYNTRA GROUPING MASTER.xlsx")      # HISTORY keeps the check's columns
    shutil.copy2(report, master_file)
    states = sb.apply(master_file, record, reasons)

    lines = [f"🎨 <b>Myntra colour grouping</b> {stamp}", ""]
    for a, rows in account_rows.items():
        df = pd.DataFrame(rows)
        rem = df["GROUPING REMARK"].value_counts() if len(df) else pd.Series(dtype=int)
        pending = e.pending_group_styles(rows)
        lines.append(f"<b>{ACCOUNT_OF.get(a, a)}</b>: {df['Unique ID'].nunique() if len(df) else 0} groups · DONE {int(rem.get(e.REMARK_DONE, 0))} · "
                     f"NOT DONE {int(rem.get(e.REMARK_NOT_DONE, 0))} · "
                     f"extra in portal {int(rem.get(e.REMARK_EXTRA, 0))} · {len(pending)} groups to submit")
        lines.append(f"   pending groups: {sb.state_line(states.get(a) or sb.Counter())}")
    open_jobs = record[~record["JOB STATUS"].astype(str).isin(sb.FINISHED)]
    open_jobs = open_jobs[open_jobs["JOB ID"].astype(str).str.fullmatch(r"\d+")]
    lines.append(f"\nSubmitted now: <b>{submitted}</b> groups" + "".join(f", {n} skipped ({why})" for why, n in skipped.items())
                 + f" · {len(open_jobs)} jobs waiting on Myntra")
    lines += [f"❌ {telegram.esc(x)}" for x in problems[:15]]
    if inventory is None:
        lines.append("\n<i>INV left blank: OMSGuru's inventory could not be read</i>")
    if missing:
        lines.append(f"\n<i>{len(missing)} styles had no answer from myntra.com (left as not live)</i>")
    if args.no_upload:
        lines.append("\n<i>test run: Drive not changed</i>")
        print("\n".join(lines))
        sb.write_reasons(reasons, work / "output" / sb.REASONS)
        shutil.copytree(work / "output", Path("output") / "myntra_grouping", dirs_exist_ok=True)
        return 0
    lg.put(master_file, XLSX)
    lg.subfolder("HISTORY", create=True).put(report, XLSX)
    lg.put(sb.write_record(record, work / sb.RECORD), XLSX)
    lg.put(sb.write_reasons(reasons, work / sb.REASONS), XLSX)
    tdir = Path(e.TEMPLATE_DIR) / stamp
    day = lg.subfolder("TEMPLATES", create=True).subfolder(stamp, create=True)
    n = 0
    for acc_dir in sorted(p for p in tdir.iterdir() if p.is_dir()):
        dest = day.subfolder(acc_dir.name, create=True)
        for f in sorted(acc_dir.glob("*.xlsx")):
            dest.put(f, XLSX)
            n += 1
    lines.append(f"\n<i>Drive AGENT WORK/MYNTRA/LISTING GROUPING: MYNTRA GROUPING MASTER.xlsx, {n} template files in TEMPLATES/{stamp}</i>")
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py myntra-grouping", description=__doc__.splitlines()[0])
    p.add_argument("--no-upload", action="store_true", help="build only (output/myntra_grouping), Drive not changed")
    p.add_argument("--submit", action="store_true", help="submit the pending groups on the Myntra partner portal")
    p.add_argument("--submit-limit", type=int, default=0, help="with --submit: at most that many groups (a test)")
    p.add_argument("--status", action="store_true", help="only read the portal's upload jobs again, myntra.com not asked")
    p.add_argument("--only-changes", action="store_true", help="with --status: nothing written or sent unless a job changed")
    return run_bot("Myntra colour grouping", p, run, argv)
