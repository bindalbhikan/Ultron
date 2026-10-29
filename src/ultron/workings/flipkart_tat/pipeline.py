"""Flipkart dispatch TAT (6 PM): the AJIO TAT working for the Flipkart channel, sheet only.

Orders = OMSGuru's Flipkart channel (FLIPKART_CHANNEL_IDS, 37863), the last FK_TAT_DAYS (4) days
plus master orders whose pickup is still open. Deadline = OMSGuru's SLA Date of the order (Flipkart's
dispatch-by, 4 PM). Processing is on time when ready by the end of that day, the pickup when Ekart's
first movement scan ("Dispatched to ...", after "Shipment Created") is by the SLA time; the status
rules are the AJIO engine's (ajio_tat/tat_engine.py).

The master is FLIPKART_TAT_MASTER.xlsx in Drive AGENT WORK/FLIPKART (Summary, TAT Report, Late
Orders), updated in place every run. No Flipkart ticket, no form: the sheet and a Telegram summary.
"""
from __future__ import annotations

import argparse
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..ajio_tat.pipeline import (XLSX, awbs_to_track, read_master_xlsx, save_master_xlsx, telegram_report,
                                 track, warehouse_ids)
from ..ajio_tat.tat_engine import (apply_status, apply_tracking, build_report, merge_master, needs_oms_refresh,
                                   normalize_master, parse_oms, summarize)
from ..core import telegram
from ..core.app import run_bot
from ..core.config import csv_list, env, num, output_dir
from ..portals.omsguru import OmsGuruClient

log = logging.getLogger("bindal.flipkart_tat")

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
AREA = "FLIPKART"
MASTER_NAME = "FLIPKART_TAT_MASTER.xlsx"
TITLE = "Flipkart Dispatch TAT Summary"
RULE = ("Rule: dispatch by Flipkart's SLA (OMSGuru SLA Date, usually 4 PM): processing by the end of that day, "
        "Ekart pickup (first movement scan) by the SLA time.")


def fetch_oms(start: datetime, end: datetime, skip_channel_orders: set[str]):
    client = OmsGuruClient.from_env(workers=num("OMSGURU_WORKERS", 6))
    client.login()
    channels = csv_list("FLIPKART_CHANNEL_IDS", "37863")
    log.info("Listing Flipkart orders %s -> %s (channels %s)", start, end, channels)
    o, hist, errors = client.fetch_window(start, end, channels, warehouse_ids(), skip_channel_orders)
    log.info("%d Flipkart order lines fetched", len(o))
    hist["ts"] = pd.to_datetime(hist["Timestamp"], format="%B %d, %Y %I:%M:%S %p", errors="coerce")
    return o, hist, errors


def sla_deadlines(o: pd.DataFrame) -> pd.Series:
    """Invoice No (OMSGuru's input identifier) -> the order's SLA Date."""
    if o.empty:
        return pd.Series(dtype="datetime64[ns]")
    sla = o.drop_duplicates("Input Identifier").set_index("Input Identifier")["SLA Date"]
    return parse_oms(sla).dropna()


def master_folder():
    from ..core.drive import DriveFolder
    return DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK)).subfolder(AREA, create=True)


def run(args) -> int:
    out = output_dir("flipkart_tat")
    # the working copy stays off Google Drive for desktop (see ajio_tat: a file saved under G:\My Drive came out damaged)
    work = (out if "my drive" not in str(out).lower() else Path(tempfile.gettempdir()) / "bindal" / "flipkart_tat")
    copy = work / "drive" / MASTER_NAME
    folder = drive = None
    if args.no_drive:
        copy = out / MASTER_NAME
    else:
        from ..core.drive import DriveFile
        folder = master_folder()
        found = folder.children().get(MASTER_NAME)
        drive = DriveFile(found["id"]) if found else None
        if not found:
            log.info("No %s in AGENT WORK/%s yet: it will be created", MASTER_NAME, AREA)

    # 1) master
    old, old_as_of = read_master_xlsx(drive.download(copy, need_edit=True) if drive else copy)
    log.info("Master loaded: %d orders", len(old))

    # 2) OMSGuru: order pages only for orders that are new or still open
    old_status = apply_status(old, pd.Timestamp.now()) if len(old) else old.assign(**{"Pickup Status": None})
    complete = set(old_status.loc[~needs_oms_refresh(old_status), "Order ID"].dropna().astype(str))
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = (datetime.strptime(args.to_date, "%Y-%m-%d") if args.to_date else today) + timedelta(days=1)
    start = datetime.strptime(args.from_date, "%Y-%m-%d") if args.from_date else today - timedelta(days=args.days)
    o, hist, errors = fetch_oms(start, end, complete)

    # 3) Ekart tracking where the pickup is not confirmed yet
    (summ, ev), n_awbs, track_errors = track(awbs_to_track(o, old_status))
    errors += track_errors
    new, as_of = (normalize_master(pd.DataFrame()), pd.Timestamp.now()) if o.empty else build_report(o, hist, summ, ev)

    # 4) merge; the deadline is Flipkart's SLA, not AJIO's 10:10 rule
    new["Dispatch Deadline"] = new["Invoice No"].map(sla_deadlines(o))
    merged, stats = merge_master(old, new)
    merged = apply_tracking(merged, summ, ev)
    no_sla = int(merged["Dispatch Deadline"].isna().sum())
    if no_sla:
        log.warning("%d orders without an SLA Date in OMSGuru", no_sla)
    if len(ev):
        as_of = max(as_of, ev["ts"].max())
    if old_as_of is not None and pd.notna(old_as_of):
        as_of = max(as_of, old_as_of)
    df = apply_status(merged, as_of)
    note = (f"OMSGuru Flipkart {start:%d-%b} to {end - timedelta(days=1):%d-%b} ({len(o)} lines read) "
            f"+ Ekart tracking ({n_awbs} open AWBs)")
    log.info("Master after merge: %d (new %d, updated %d, kept %d)", len(df), stats["new"], stats["updated"],
             stats["kept (not in input)"])

    # 5) the sheet
    save_master_xlsx(df, copy, note, as_of, title=TITLE, rule=RULE)
    if drive:
        drive.upload(copy)
    elif folder:
        folder.put(copy, XLSX)
    (out / "errors.log").write_text("\n".join(errors), encoding="utf-8")

    s = summarize(df)
    report = telegram_report(df).replace("AJIO Dispatch", "Flipkart Dispatch", 1)
    report += f"\n\nTAT {s['tat_pct']:.1%} · sheet: AGENT WORK/{AREA}/{MASTER_NAME}"
    if errors:
        report += f"\n\u26a0\ufe0f {len(errors)} order page / tracking lookups failed (they keep their last status)"
    if args.no_telegram:
        print(report)
    else:
        telegram.send(report)
    print(df["TAT Result"].value_counts().to_string())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py flipkart-tat", description="Flipkart dispatch TAT (sheet only)")
    p.add_argument("--days", type=int, default=num("FK_TAT_DAYS", 4),
                   help="OMSGuru window: today plus this many previous days (default 4)")
    p.add_argument("--from", dest="from_date", help="OMSGuru order date from, YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", help="OMSGuru order date to, YYYY-MM-DD (default today)")
    p.add_argument("--no-drive", action="store_true", help="local master in output/flipkart_tat only")
    return run_bot("Flipkart Dispatch TAT report", p, run, argv)


if __name__ == "__main__":
    raise SystemExit(main())
