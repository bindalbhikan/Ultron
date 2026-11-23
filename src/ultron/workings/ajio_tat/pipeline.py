"""Daily run: OMSGuru -> courier tracking -> TAT rules -> Google Sheet -> Telegram."""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from ultron.core.style import MOBILE, tidy

from ..awb_tracker import CourierRegistry, Job, track_all
from ..core import clients, dashboard, telegram
from ..core.app import run_bot
from ..core.config import ROOT, csv_list, env, num, output_dir
from ..portals.omsguru import OmsGuruClient
from .tat_engine import (NOT_PICKED_COURIER_STATUSES, OPEN_PICKUP, apply_status, apply_tracking,
                         dispatch_deadlines, needs_oms_refresh, build_report, merge_master,
                         normalize_master, pickup_times, prepare_tracking, summarize, write_excel)
from ..core.tables import pclean_id, read_excel_text

KEEP_BACKUPS = 30
MASTER_NAME = "AJIO_TAT_MASTER.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
log = logging.getLogger("bindal.ajio_tat")


def _key(e: pl.Expr) -> pl.Expr:
    """An id to match on: text, outer spaces out, upper case, no ".0" (an empty one is the text "NAN", as before)."""
    return pclean_id(e.cast(pl.Utf8).fill_null("nan").str.strip_chars().str.to_uppercase())


def ajio_order_report(first, last) -> pl.DataFrame:
    """The AJIO Dropship order report for order dates first..last, read 30 days at a time."""
    from ..core.tables import read_excel_text
    client = clients.ajio()
    frames, a = [], first
    while a <= last:
        b = min(a + timedelta(days=29), last)
        data = client.order_report_or_empty(a, b)
        if data:
            frames.append(read_excel_text(data, 0))
        a = b + timedelta(days=1)
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def ajio_report(df: pl.DataFrame, errors: list[str], since=None) -> pl.DataFrame:
    """From the AJIO Dropship order report: Cust Order No (AJIO's FN... order number, matched on
    the seller order = Order ID) where missing, and the Pickup Time: AJIO's "Pickup Timestamp"
    (the report's last column, matched on AWB, else seller invoice) is THE pickup time, so it
    replaces the courier tracking's time wherever AJIO has one; courier tracking only fills
    orders AJIO shows no pickup for yet. Read 30 days at a time over the order dates from `since`
    (AJIO_PICKUP_DAYS, 30 days back) plus older orders still missing either; every order the
    report has a pickup for takes it. An AJIO failure is noted and the courier / OMSGuru values
    stand. (23 Oct 2026: of 2,139 AJIO pickups since 1 Sep, 45 differed from the courier's scan,
    AJIO 4 to 11 hours later.)"""
    if not env("AJIO_USERNAME"):
        return df
    no_pick = pl.col("Pickup Time").is_null() & pl.col("AWB").is_not_null()
    no_cust = pl.col("Cust Order No").is_null()
    recent = (pl.col("Order Time") >= since).fill_null(False) if since is not None else pl.lit(False)
    want = (no_pick | no_cust | (recent & pl.col("AWB").is_not_null())) & pl.col("Order Time").is_not_null()
    wanted = df.filter(want)
    if not wanted.height:
        return df
    first, last = wanted["Order Time"].min().date(), wanted["Order Time"].max().date()
    try:
        rep = ajio_order_report(first, last)
    except Exception as exc:  # noqa: BLE001 - courier / OMSGuru values stand
        log.exception("AJIO order report not read")
        errors.append(f"AJIO order report not read: {str(exc)[:100]}")
        return df
    if not rep.height:
        return df
    named = rep.filter(pl.col("Cust Order No").is_not_null())
    cust = named.group_by(_key(pl.col("FWD Seller Order NO")).alias("_k"), maintain_order=True).agg(pl.col("Cust Order No").first().alias("_c1"))
    cust_awb = named.group_by(_key(pl.col("FWD AWB")).alias("_k"), maintain_order=True).agg(pl.col("Cust Order No").first().alias("_c2"))
    ts = pl.col("Pickup Timestamp").cast(pl.Utf8).fill_null("nan").str.replace(" IST", "", literal=True) \
        .str.to_datetime("%a %b %d %H:%M:%S %Y", strict=False, time_unit="us")
    picked = rep.with_columns(ts.alias("_ts")).filter(pl.col("_ts").is_not_null())
    by_awb = picked.group_by(_key(pl.col("FWD AWB")).alias("_k")).agg(pl.col("_ts").min().alias("_p1"))
    by_inv = picked.group_by(_key(pl.col("Seller Invoice No")).alias("_k")).agg(pl.col("_ts").min().alias("_p2"))
    x = (df.with_columns(want.alias("_want"), no_pick.alias("_nopick"), no_cust.alias("_nocust"),
                         _key(pl.col("Order ID")).alias("_ko"), _key(pl.col("AWB")).alias("_ka"), _key(pl.col("Invoice No")).alias("_ki"))
           .join(cust, left_on="_ko", right_on="_k", how="left", maintain_order="left")
           .join(cust_awb, left_on="_ka", right_on="_k", how="left", maintain_order="left")
           .join(by_awb, left_on="_ka", right_on="_k", how="left", maintain_order="left")
           .join(by_inv, left_on="_ki", right_on="_k", how="left", maintain_order="left"))
    got, found = pl.coalesce("_c1", "_c2"), pl.coalesce("_p1", "_p2")
    fill_cust = pl.col("_want") & pl.col("_nocust") & got.is_not_null()
    x = x.with_columns(fill_cust.alias("_fc"), found.alias("_found"))
    hit = pl.col("_found").is_not_null()
    n = x.select(hit.sum().alias("a"), (hit & pl.col("_nopick")).sum().alias("b"),
                 (hit & ~pl.col("_nopick") & (pl.col("Pickup Time") != pl.col("_found")).fill_null(True)).sum().alias("c"),
                 pl.col("_fc").sum().alias("d")).row(0)
    out = x.with_columns(pl.when("_fc").then(got).otherwise(pl.col("Cust Order No")).alias("Cust Order No"),
                         pl.coalesce("_found", "Pickup Time").alias("Pickup Time")).select(df.columns)
    log.info("AJIO order report %s..%s: %d lines, %d pickup times from AJIO (%d new, %d replacing the "
             "courier's time), %d Cust Order Nos filled", first, last, rep.height, *n)
    return out


def erp_labels(df, since: datetime, errors: list[str]):
    """ERP Label Time / ERP Label By from the ERP packing report (Shipping Label Print), portal
    AJIO, whose "Order ID" is the AWB. Read from the OMSGuru window's start (a week at least).
    An ERP failure is noted and the old values stay."""
    if not env("ERP_USERNAME"):
        log.info("ERP not configured: label prints not checked")
        return df
    from ..portals.erp import Erp
    from .tat_engine import apply_erp_labels
    first = min(since.date(), (datetime.now() - timedelta(days=7)).date())
    try:
        erp = Erp.from_env()
        erp.login()
        labels: dict[str, tuple] = {}
        for line in erp.packed("AJIO", first):
            awb = str(line.get("Order ID") or "").strip().upper()
            when = line.get("Created On") or line.get("Voucher Date")
            if awb and when is not None and (awb not in labels or str(when) < str(labels[awb][0])):
                labels[awb] = (when, line.get("Created By") or "")
    except Exception as exc:  # noqa: BLE001 - the TAT report still goes out
        log.warning("ERP label prints not read: %s", exc)
        errors.append(f"ERP label prints not read: {exc}")
        return df
    df, n = apply_erp_labels(df, labels)
    log.info("ERP: %d AJIO label prints since %s, %d new in the master", len(labels), first, n)
    return df


def master_xlsx() -> Path:
    return Path(env("TAT_XLSX_PATH") or ROOT / "data" / "AJIO_TAT_MASTER.xlsx")


def read_master_xlsx(path: Path):
    if not path.exists():
        return normalize_master(None), None
    m = normalize_master(read_excel_text(path, "_data"))
    try:
        meta = pl.read_excel(path, sheet_name="_meta", engine="calamine")
        as_of = meta["as_of"][0]
        as_of = as_of if isinstance(as_of, datetime) else datetime.fromisoformat(str(as_of))
    except Exception:
        as_of = None
    return m, as_of


def save_master_xlsx(df, path: Path, note: str, as_of, **summary) -> None:
    """Backup the current master, write a temp file, verify it, then swap it in. summary: title /
    rule of the Summary tab (Flipkart TAT)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bdir = path.parent / "backup"
        bdir.mkdir(exist_ok=True)
        shutil.copy2(path, bdir / f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
        for old in sorted(bdir.glob(f"{path.stem}_*.xlsx"))[:-KEEP_BACKUPS]:
            old.unlink()
    tmp = path.with_name(path.stem + "_tmp.xlsx")
    write_excel(df, tmp, note, as_of, **summary)
    if read_master_xlsx(tmp)[0].height != df.height:
        raise RuntimeError(f"New master failed verification; old master left unchanged ({tmp})")
    try:
        os.replace(tmp, path)
    except PermissionError:
        raise RuntimeError(f"Master file is open in Excel - close it and run again: {path}") from None
    # in a Google Drive for desktop folder (a local run from G:) the swapped-in file came out
    # broken once (bad CRC in docProps/core.xml): never upload such a file
    try:
        bad = zipfile.ZipFile(path).testzip()
    except zipfile.BadZipFile as exc:
        bad = str(exc)
    if bad:
        raise RuntimeError(f"Saved master is damaged ({bad}), not uploaded: {path}")
    log.info("Master xlsx saved: %s", path)


# ------------------------------------------------------------------ steps

def warehouse_ids() -> list[str]:
    return csv_list("OMSGURU_WAREHOUSE_IDS")


def csv_list_of(text: str | None) -> list[str]:
    return list(dict.fromkeys(t.upper() for t in re.split(r"[\s,]+", text or "") if t))


def seller_orders(numbers: list[str]) -> list[str]:
    """AJIO numbers as OMSGuru knows them: a customer order number (FN... / EX...) becomes the
    seller order number through the AJIO order report of the last ORDERS_LOOKBACK_DAYS (180);
    seller order numbers, invoices and AWBs are kept as they are."""
    cust = [n for n in numbers if re.fullmatch(r"[A-Z]{2}\d{8,}", n)]
    if not cust:
        return numbers
    today = datetime.now().date()
    rep = ajio_order_report(today - timedelta(days=num("ORDERS_LOOKBACK_DAYS", 180)), today)
    to_seller = (dict(rep.filter(pl.col("Cust Order No").is_not_null()).unique("Cust Order No", keep="first", maintain_order=True)
                         .select("Cust Order No", "FWD Seller Order NO").iter_rows()) if rep.height else {})
    missing = [n for n in cust if n not in to_seller]
    if missing:
        log.warning("Not in the AJIO order report: %s", ", ".join(missing))
    return [n for n in numbers if n not in cust] + [to_seller[n] for n in cust if n in to_seller]


def fetch_oms(start: datetime, end: datetime, skip_channel_orders: set[str], extra: list[str] = ()):
    """The window's AJIO orders; extra: order numbers to read too, whatever their date (--orders)."""
    client = OmsGuruClient.from_env(workers=num("OMSGURU_WORKERS", 6))
    client.login()
    channels = csv_list("AJIO_CHANNEL_IDS", "57285,34958")
    log.info("Listing AJIO orders %s -> %s (channels %s)", start, end, channels)
    o, hist, errors = client.fetch_window(start, end, channels, warehouse_ids(), skip_channel_orders)
    if extra:
        terms, ids = seller_orders(list(extra)), []
        for wh in warehouse_ids() or list(client.warehouses()) or [None]:
            if wh:
                client.set_warehouse(wh)
            for t in terms:
                ids += [i for i in client.search(t, "order") if i not in ids]
        log.info("--orders: %d numbers, %d OMSGuru orders found", len(extra), len(ids))
        o2, h2, e2 = client.fetch_orders(ids)
        o, hist, errors = pl.concat([o, o2], how="vertical_relaxed"), pl.concat([hist, h2], how="vertical_relaxed"), errors + e2
    log.info("%d AJIO order lines fetched", o.height)
    hist = hist.with_columns(pl.col("Timestamp").cast(pl.Utf8).str.strip_chars()
                             .str.to_datetime("%B %d, %Y %I:%M:%S %p", strict=False, time_unit="us").alias("ts"))
    return o, hist, errors


def oms_window(args) -> tuple[datetime, datetime]:
    """OMSGuru order-date window: yesterday + today by default (--days 1), or --from/--to."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = (datetime.strptime(args.to_date, "%Y-%m-%d") if args.to_date else today) + timedelta(days=1)
    start = datetime.strptime(args.from_date, "%Y-%m-%d") if args.from_date else today - timedelta(days=args.days)
    return start, end


def track_results(pairs: pl.DataFrame) -> list:
    """pairs: AWB + Courier columns, one row per AWB to track; the tracker's result per AWB."""
    jobs = [Job(a, p) for a, p in pairs.select("AWB", "Courier").iter_rows()]
    if not jobs:
        return []
    cfg_path = ROOT / "tracking_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if env("SHADOWFAX_TOKEN"):
        cfg.setdefault("couriers", {}).setdefault("SHADOWFAX", {})["token"] = env("SHADOWFAX_TOKEN")
    log.info("Tracking %d AWBs (pickup not confirmed yet)", len(jobs))
    return track_all(jobs, CourierRegistry(cfg), workers=num("TRACK_WORKERS", 8), progress=False)


def track(pairs: pl.DataFrame):
    """pairs: AWB + Courier columns, one row per AWB to track."""
    results = track_results(pairs)
    if not results:
        return prepare_tracking([], []), 0, []
    summary = [r.summary_row() for r in results]
    events = [e for r in results for e in r.event_rows()]
    # NOT_FOUND is normal for a fresh AWB the courier has not manifested yet: not an error
    failed = [f"{r.partner} {r.awb}: {r.error}" for r in results
              if not r.ok and r.error and r.status != "NOT_FOUND"]
    return prepare_tracking(summary, events), len(results), failed


def awbs_to_track(o: pl.DataFrame, old_status: pl.DataFrame) -> pl.DataFrame:
    """AWBs whose pickup is still open: orders just read from OMS, plus master orders
    still 'Pending Pickup' from the last TRACK_DAYS days. Picked / cancelled ones are skipped."""
    fresh = o.select(pl.col("AWB / Shipment Tracker").cast(pl.Utf8).fill_null("nan").str.extract(r"^\s*([A-Za-z0-9]+)", 1).alias("AWB"),
                     pl.col("Shipping Company").cast(pl.Utf8).alias("Courier"),
                     pl.col("Item Status").cast(pl.Utf8).fill_null("nan").alias("Status")) if o.height else \
        pl.DataFrame(schema={"AWB": pl.Utf8, "Courier": pl.Utf8, "Status": pl.Utf8})
    fresh = fresh.filter(~pl.col("Status").str.contains("(?i)cancel"))
    since = _today() - timedelta(days=num("TRACK_DAYS", 15))
    is_open = pl.col("Pickup Status").is_in(list(OPEN_PICKUP)).fill_null(False)
    pend = old_status.filter(is_open & (pl.col("Order Time") >= since).fill_null(False)).select("AWB", "Courier")
    picked = set(old_status.filter(~is_open)["AWB"].cast(pl.Utf8).fill_null("nan").to_list())
    pairs = pl.concat([fresh.select("AWB", "Courier"), pend.cast({"AWB": pl.Utf8, "Courier": pl.Utf8})], how="vertical")
    return (pairs.filter(pl.col("AWB").is_not_null() & (pl.col("AWB").str.len_chars() > 3) & ~pl.col("AWB").is_in(sorted(picked)))
                 .unique("AWB", keep="first", maintain_order=True))


def _today() -> datetime:
    return datetime.combine(date.today(), datetime.min.time())


# ------------------------------------------------------------------ report

PICKED = ["On Time", "Late", "Picked (Time N/A)"]


def awaiting_pickup() -> pl.Expr:
    """Processed, not picked up, not cancelled."""
    return ~pl.col("Pickup Status").is_in(PICKED + ["Cancelled"]).fill_null(False) & (pl.col("Process Status") != "Not Processed").fill_null(True)


def pickup_pending(now: datetime) -> pl.Expr:
    """Awaiting pickup and the TAT deadline has passed."""
    return awaiting_pickup() & (pl.col("Dispatch Deadline") < now).fill_null(False)


# Telegram on a phone shows ~28 monospace characters per line: every <pre> table stays within that.
SHORT_COURIER = {"BLUEDART": "BluDart", "DELHIVERY": "Delhvry", "SHADOWFAX": "Shdwfax",
                 "XPRESSBEES": "XpresBz", "EKART": "Ekart", "E-KART": "Ekart", "VALMO": "Valmo", "UNKNOWN": "?"}


def short_courier(name) -> str:
    key = str(name or "UNKNOWN").upper().replace(" ", "")
    for k, v in SHORT_COURIER.items():
        if k in key:
            return v
    return str(name).title()[:7]


def _counts(df: pl.DataFrame, col: str) -> dict:
    return dict(df.group_by(col).len().iter_rows()) if df.height else {}


def _summary_block(part: pl.DataFrame, title: str, now: datetime) -> list[str]:
    """Order count, processing on time / late / pending, and a narrow per-courier table:
    Done = picked up, Pend = pickup pending: processed but not picked and the TAT deadline has passed,
    Due = processed, not picked, deadline not reached yet, Proc = not processed."""
    proc = _counts(part, "Process Status")
    lines = ["", f"<b>{title} · {part.height} orders</b>",
             f"✅ {proc.get('On Time', 0)} on time · ⏰ {proc.get('Late', 0)} late · "
             f"⏳ {proc.get('Not Processed', 0)} pending"]
    if not part.height:
        return lines
    not_proc, picked = pl.col("Process Status") == "Not Processed", pl.col("Pickup Status").is_in(PICKED).fill_null(False)
    over = pickup_pending(now)
    g = (part.group_by(pl.col("Courier").fill_null("UNKNOWN").alias("_c")).agg(
            picked.sum().alias("d"), over.sum().alias("p"), (~picked & ~not_proc & ~over).sum().alias("x"), not_proc.sum().alias("n"))
            .sort("_c"))
    rows = [(short_courier(c), int(d), int(p), int(x), int(n)) for c, d, p, x, n in g.iter_rows()]
    table = [f"{'Courier':<8}{'Done':>5}{'Pend':>5}{'Due':>5}{'Proc':>5}"]
    table += [f"{c:<8}{d:>5}{p:>5}{x:>5}{n:>5}" for c, d, p, x, n in rows]
    table.append(f"{'Total':<8}" + "".join(f"{sum(r[i] for r in rows):>5}" for i in range(1, 5)))
    lines.append("<pre>" + telegram.esc("\n".join(table)) + "</pre>")
    return lines


def telegram_report(df: pl.DataFrame) -> str:
    """Mobile-friendly summary: yesterday, today, and the current month to date
    (by order date, cancelled orders left out)."""
    now = datetime.now()
    today = _today()
    live = df.filter((pl.col("Pickup Status") != "Cancelled").fill_null(True)).with_columns(pl.col("Order Time").dt.truncate("1d").alias("_d"))
    lines = [f"📦 <b>AJIO Dispatch · {today:%d %b %Y}</b>"]
    for day in (today - timedelta(days=1), today):
        lines += _summary_block(live.filter(pl.col("_d") == day), f"📅 {day:%d %b}", now)
    month_start = today.replace(day=1)
    lines += _summary_block(live.filter((pl.col("_d") >= month_start) & (pl.col("_d") <= today)),
                            f"🗓 {today:%B} 1-{today.day}", now)
    lines += ["", "<i>Done = picked up",
              "Pend = not picked up, TAT passed",
              "Due = not picked up, still within TAT",
              "Proc = processing pending</i>"]
    return "\n".join(lines)


def _text(v) -> str:
    return "" if v is None else str(v)


def pickup_pending_report(df: pl.DataFrame, now=None) -> list:
    """Third Telegram message: every processed AWB still waiting for pickup (last TRACK_DAYS days),
    TAT passed ("Over") first, then still within TAT ("Due"), with a short ready-to-copy mail
    for the courier / AJIO. The mail is plain text (wraps on a phone, pastes cleanly); the AWB list
    is a narrow table when it fits in the one message, and every AWB, with its order, times and AJIO
    pickup ticket id, comes in the attached Excel (to forward with the mail). A telegram report;
    [] when nothing is waiting."""
    now = now or datetime.now()
    since = datetime.combine(now.date(), datetime.min.time()) - timedelta(days=num("TRACK_DAYS", 15))
    pend = (df.filter(awaiting_pickup() & (pl.col("Order Time") >= since).fill_null(False))
              .with_columns((pl.col("Dispatch Deadline") < now).fill_null(False).alias("_over"))
              .sort(["_over", "Courier", "RTS Time"], descending=[True, False, False], nulls_last=True, maintain_order=True))
    if not pend.height:
        return []
    n_over = int(pend["_over"].sum())
    pob = env("POB_ID", "DV00348890")
    recs = list(pend.iter_rows(named=True))
    table = [f"{str(r['AWB'])[:15]:<15} {short_courier(r['Courier'])[:7]:<7} {'Over' if r['_over'] else 'Due'}" for r in recs]
    rows = [{"AWB": _text(r["AWB"]), "Courier": _text(r["Courier"]), "TAT": "Over" if r["_over"] else "Due",
             "Order ID": _text(r["Order ID"]), "Order Time": r["Order Time"],
             "Ready (RTS)": r["RTS Time"], "Pickup Deadline": r["Dispatch Deadline"],
             "Pickup Ticket": _text(r.get("Pickup Ticket"))} for r in recs]
    n_ticket = sum(1 for r in rows if r["Pickup Ticket"])
    return [f"📮 <b>Pickup Pending · {pend.height} AWB</b>",
            f"🔴 Over (TAT passed) {n_over} · 🟡 Due {pend.height - n_over} · 🎫 AJIO ticket {n_ticket}",
            "",
            f"<b>Subject:</b> Pickup Pending - POB ID {pob} - {pend.height} shipments",
            "",
            "Dear Team,",
            "Below shipments are packed and ready, but pickup is still pending. "
            "Kindly arrange the pickup today on priority.",
            f"POB ID: {pob}",
            telegram.Listing("", ["<pre>" + telegram.esc(f"{'AWB':<15} {'Courier':<7} TAT\n" + "\n".join(table)) + "</pre>"],
                             rows, "Pickup pending"),
            "Regards,", "Bindal Exports"]


def pickup_ticket_candidates(df: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """Packed, not picked up, ordered in the last TRACK_DAYS (15) days: one AJIO ticket per order,
    whether its pickup deadline has passed (Over) or not yet (Due) - every order of the pickup
    pending list gets one. TICKET_ONLY_OVER=1: only orders whose deadline passed
    TICKET_GRACE_HOURS (24) ago, as before 24 Oct 2026."""
    since = datetime.combine(now.date(), datetime.min.time()) - timedelta(days=num("TRACK_DAYS", 15))
    due = (awaiting_pickup() & (pl.col("Order Time") >= since).fill_null(False)
           & pl.col("Order ID").is_not_null() & pl.col("AWB").is_not_null())
    if env("TICKET_ONLY_OVER", "").lower() in ("1", "true", "yes"):
        due = due & (pl.col("Dispatch Deadline") + timedelta(hours=num("TICKET_GRACE_HOURS", 24)) < now).fill_null(False)
    return df.filter(due).sort("Dispatch Deadline", nulls_last=True, maintain_order=True)


ORDER_IN_TICKET = re.compile(r"Order ID (\d+)")


def _order_lines(rows: list[dict]) -> str:
    return "\n".join(f"{i}. Order ID {r['Order ID']} - AWB {r['AWB']}" for i, r in enumerate(rows, 1))


def pickup_ticket_text(courier: str, rows: list[dict], part: int = 1, parts: int = 1) -> tuple[str, str]:
    """One ticket for a courier's pending pickups; every order on its own "Order ID ..." line (read
    back from the description by the next runs)."""
    more = f" ({part}/{parts})" if parts > 1 else ""
    one = len(rows) == 1
    subject = f"PICKUP NOT DONE | {courier} | {len(rows)} {'order' if one else 'orders'}{more}"
    description = (f"Hi Team,\n\nThe below {len(rows)} {courier} {'shipment was' if one else 'shipments were'} "
                   f"ready to ship on time, but the pickup is still pending. Kindly arrange the pickup, and no "
                   f"penalty should be applied to {'this order' if one else 'these orders'}.\n\n"
                   f"{_order_lines(rows)}\n\nThanks & regards,\nBindal Exports")
    return subject, description


def pickup_followup_text(rows: list[dict]) -> str:
    these = "this order" if len(rows) == 1 else "these orders"
    which = "this order" if len(rows) == 1 else f"these {len(rows)} orders"
    return (f"Pickup is still pending for {which}. Kindly arrange the pickup today, and no penalty should "
            f"be applied to {these}.\n\n{_order_lines(rows)}")


def pickup_ticket_file(courier: str, rows: list[dict], now) -> tuple[str, bytes]:
    """The ticket's attachment: its orders as an Excel (Order ID, AWB, Courier), nothing else."""
    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "strings_to_numbers": False})
    ws = wb.add_worksheet("Pickup pending")
    bold = wb.add_format({"bold": True, "border": 1, "align": "center"})
    for j, h in enumerate(("Order ID", "AWB", "Courier")):
        ws.write_string(0, j, h, bold)
    for i, r in enumerate(rows, start=1):
        for j, v in enumerate((r["Order ID"], r["AWB"], courier)):
            ws.write_string(i, j, str(v))
    wb.close()
    return f"PICKUP PENDING {courier} {now:%d-%m-%y}.xlsx", buf.getvalue()


def pickup_ticket_ids(client, tickets: list[dict]) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """Order ID -> its AJIO pickup ticket ids, from the tickets listed: a one-per-order ticket (before
    27 Oct 2026, subject "PICKUP NOT DONE | Order ...") by its order id, a courier ticket by the
    orders in its description. Also the courier tickets' details (for the follow-ups)."""
    from ..portals.ajio import PICKUP_NOT_DONE, AjioError
    pickup = [t for t in tickets if str(t.get("subCategory") or "").upper() == PICKUP_NOT_DONE]
    courier_ids = [str(t["ticketId"]) for t in pickup if not str(t.get("subject") or "").startswith(
        "PICKUP NOT DONE | Order ")]
    details = {str(t["ticketId"]): t for t in client.ticket_details(courier_ids)}
    # a courier ticket's orders are only in its details: without them its orders look ticket-free and would get a second ticket
    unread = [t for t in courier_ids if t not in details]
    if unread:
        raise AjioError(f"{len(unread)} of {len(courier_ids)} pickup tickets' details not read; no ticket raised this run")
    ids: dict[str, list[str]] = {}
    for t in sorted(pickup, key=lambda t: str(t.get("createdDate"))):
        tid = str(t["ticketId"])
        orders = (ORDER_IN_TICKET.findall(str(details[tid].get("description") or "")) if tid in details
                  else [str(t.get("orderId") or "").strip()])
        for oid in filter(None, orders):
            ids.setdefault(oid, [])
            if tid not in ids[oid]:
                ids[oid].append(tid)
    return ids, details


def due_followup(ticket: dict, seller_id: str, now, hours: int) -> bool:
    """Our last word on the ticket (its creation, or our last comment) is `hours` old or more."""
    def at(v):
        try:
            t = datetime.fromisoformat(str(v)[:26].replace("Z", "+00:00"))
            return t.replace(tzinfo=None)
        except (TypeError, ValueError):
            return None
    ours = [at(c.get("createdAt")) for c in ticket.get("comments") or []
            if str(c.get("authorType") or "").upper() == "SELLER" or str(c.get("authorId") or "") == seller_id]
    last = max([x for x in ours + [at(ticket.get("createdDate"))] if x is not None], default=None)
    return last is None or now - last >= timedelta(hours=hours)


def courier_pickup_check(pairs: pl.DataFrame) -> dict[str, str]:
    """AWB -> "picked" / "not picked" / "not checked", from the courier's site right now. Picked: a
    pickup (or later) scan, or a status past pickup. NOT_FOUND (the courier has no such AWB yet) is
    not picked; any other tracking failure is not checked."""
    out = {}
    for r in track_results(pairs):
        summ, ev = prepare_tracking([r.summary_row()], r.event_rows())
        pk = pickup_times(ev)
        if (pk["Pickup Time"].is_not_null().any()
                or str(r.status) not in NOT_PICKED_COURIER_STATUSES):
            out[str(r.awb)] = "picked"
        elif not r.ok and r.status != "NOT_FOUND":
            out[str(r.awb)] = "not checked"
        else:
            out[str(r.awb)] = "not picked"
    return out


def raise_pickup_tickets(df, now, dry: bool) -> tuple[list[dict], dict[str, list[str]]]:
    """AJIO tickets (ORDERS > PICKUP NOT DONE / SHIPMENT NOT SCANNING) for the pickup pending orders
    whose pickup neither the AJIO order report (already read into df this run) nor the courier's
    site, checked again here, shows: ONE ticket per courier, all its orders listed in it (since 27 Oct
    2026; before, one per order; their Excel attached), TICKET_BATCH (50) orders a ticket at most. Never two tickets for one
    order: an order with any pickup ticket (one-per-order or courier, last 30 days, or a ticket id
    already in the master's Pickup Ticket) is not raised again; at most TICKET_CAP (200) orders per
    run. Instead, while some of its parcels are still not picked up, the order's latest ticket gets a
    follow-up comment listing them once our last word on it is TICKET_FOLLOWUP_HOURS (24) old (a
    comment re-opens a resolved ticket); at most TICKET_FOLLOWUP_CAP (40) tickets per run.
    Returns one record per candidate order and every order's pickup ticket ids (old and new)."""
    from ..portals.ajio import pickup_payload
    if not env("AJIO_USERNAME"):
        return [], {}
    client = clients.ajio()
    ids, courier_tickets = pickup_ticket_ids(
        client, client.ticket_list((now - timedelta(days=30)).date(), now.date()))
    cands = pickup_ticket_candidates(df, now)
    if not cands.height:
        return [], ids
    courier = courier_pickup_check(cands)
    pob, cap, batch, done = env("POB_ID", "DV00348890"), num("TICKET_CAP", 200), num("TICKET_BATCH", 50), []
    follow_cap, follow_hours = num("TICKET_FOLLOWUP_CAP", 40), num("TICKET_FOLLOWUP_HOURS", 22)
    gap = num("TICKET_DELAY_MS", 30) / 1000     # pause between two AJIO ticket / comment calls
    to_raise: dict[str, list[dict]] = {}
    to_follow: dict[str, list[dict]] = {}
    for r in cands.iter_rows(named=True):
        oid = str(r["Order ID"]).strip()
        rec = {"Order ID": oid, "AWB": str(r["AWB"]), "Courier": str(r["Courier"]),
               "Pickup Deadline": r["Dispatch Deadline"], "Ticket": ", ".join(ids.get(oid, [])), "Result": ""}
        seen = courier.get(str(r["AWB"]), "not checked")
        rec["Courier Site"] = seen
        in_master = [x.strip() for x in str(r.get("Pickup Ticket") or "").split(",")
                     if x.strip() and x.strip().lower() != "nan"]
        if ids.get(oid) or in_master:
            rec["Result"] = "already has ticket"
            if seen == "not picked" and ids.get(oid):
                to_follow.setdefault(ids[oid][-1], []).append(rec)
        elif seen != "not picked":
            rec["Result"] = f"courier: {seen}"
        elif sum(len(v) for v in to_raise.values()) >= cap:
            rec["Result"] = "over cap"
        else:
            to_raise.setdefault(short_courier(r["Courier"]), []).append(rec)
        done.append(rec)

    for tid, recs in list(to_follow.items())[:follow_cap]:
        try:
            ticket = courier_tickets.get(tid) or client.ticket_detail(tid) or {}
            if due_followup(ticket, client.seller_id, now, follow_hours):
                if not dry:
                    client.comment(tid, pickup_followup_text(recs))
                    time.sleep(gap)
                for rec in recs:
                    rec["Result"] = "follow-up due (dry run)" if dry else "followed up"
        except Exception as exc:  # noqa: BLE001 - the ticket keeps waiting for the next run
            for rec in recs:
                rec["Result"] = f"error: follow-up {exc}"[:200]

    for recs in to_raise.values():
        name = recs[0]["Courier"].strip().upper()
        parts = [recs[i:i + batch] for i in range(0, len(recs), batch)]
        for n, part in enumerate(parts, 1):
            if dry:
                for rec in part:
                    rec["Result"] = "dry-run"
                continue
            subject, description = pickup_ticket_text(name, part, n, len(parts))
            try:
                tid = client.create_ticket(pickup_payload(part[0]["Order ID"], subject, description, pob,
                                                          env("AJIO_USERNAME")))
                time.sleep(gap)
            except Exception as exc:  # noqa: BLE001 - the next courier still gets its ticket
                for rec in part:
                    rec["Result"] = f"error: {exc}"[:200]
                continue
            try:   # the orders are in the description too: a failed attachment is only logged
                client.attach(tid, *pickup_ticket_file(name, part, now), XLSX)
                time.sleep(gap)
            except Exception as exc:  # noqa: BLE001
                log.warning("Ticket %s: Excel not attached: %s", tid, exc)
            for rec in part:
                ids.setdefault(rec["Order ID"], []).append(tid)
                rec.update(Ticket=", ".join(ids[rec["Order ID"]]), Result="created", New=tid)
    log.info("Pickup tickets: %s", dict(Counter(d["Result"] for d in done).most_common()))
    return done, ids


def add_ticket_ids(df, ids: dict[str, list[str]]):
    """The master's "Pickup Ticket": every AJIO pickup ticket id of the order, old and new, comma
    separated (the ids already there are kept)."""
    if not ids:
        return df

    def joined(old, oid):
        if oid not in ids:
            return old
        have = [] if old is None else [x.strip() for x in str(old).split(",") if x.strip()]
        return ", ".join(dict.fromkeys(have + ids.get(oid, []))) or old

    keys = df.select(pclean_id(pl.col("Order ID").cast(pl.Utf8).fill_null("nan").str.strip_chars()))["Order ID"].to_list()
    tickets = [joined(o, k) for o, k in zip(df["Pickup Ticket"].to_list(), keys)]
    return df.with_columns(pl.Series("Pickup Ticket", tickets, dtype=pl.Utf8))


def pickup_tickets(df, args, errors: list[str]):
    """When on (--tickets / --tickets-dry / AJIO_PICKUP_TICKETS=1): raise the courier pickup tickets
    and write every order's pickup ticket ids (old one-per-order and courier tickets of the last 30
    days, and this run's) into the master's "Pickup Ticket" column. Not raised when this run could
    not read the AJIO order report (its Pickup Timestamp is the first pickup check).
    Returns the master and the Telegram report ([] when nothing to say)."""
    if not (args.tickets or args.tickets_dry or env("AJIO_PICKUP_TICKETS", "").lower() in ("1", "true", "yes")):
        return df, []
    if any(e.startswith("AJIO order report not read") for e in errors):
        return df, ["⚠️ AJIO pickup tickets not raised: the AJIO order report (pickup times) was not read"]
    try:
        done, ids = raise_pickup_tickets(df, datetime.now(), dry=args.tickets_dry)
    except Exception as exc:  # noqa: BLE001 - the TAT report still goes out
        log.exception("Pickup tickets not raised")
        return df, [f"⚠️ AJIO pickup tickets not raised: {telegram.esc(str(exc)[:150])}"]
    return add_ticket_ids(df, ids), pickup_ticket_report(done) + pickup_forms(done, dry=args.tickets_dry)


FORM_LOG = "AJIO_PICKUP_FORMS.json"   # {"2026-10-29": ["Bluedart", ...]}: a courier's form once a day


def pickup_forms(done: list[dict], dry: bool) -> list[str]:
    """The AJIO "Seller Pickup Issue" form, once a day per courier with parcels not picked up past
    their deadline (pickup_form.py); the couriers sent each day are kept in FORM_LOG next to the
    master, so a second run that day does not send them again."""
    from .pickup_form import send_forms
    if dry:
        return []
    try:
        from ..core.drive import DriveFolder
        folder = DriveFolder(env("TAT_DRIVE_FOLDER_ID")) if env("TAT_DRIVE_FOLDER_ID") else None
        work = Path(tempfile.mkdtemp(prefix="ajio_form_"))
        log_path = folder.download(FORM_LOG, work / FORM_LOG) if folder else None
        sent_log = json.loads(log_path.read_text(encoding="utf-8")) if log_path else {}
        today = f"{date.today()}"
        lines, sent = send_forms(done, datetime.now(), set(sent_log.get(today, [])))
        if sent and folder:
            sent_log[today] = sorted(set(sent_log.get(today, [])) | sent)
            keep = sorted(sent_log)[-60:]
            (work / FORM_LOG).write_text(json.dumps({k: sent_log[k] for k in keep}, indent=1), encoding="utf-8")
            folder.put(work / FORM_LOG, "application/json")
        return lines
    except Exception as exc:  # noqa: BLE001 - the TAT report still goes out
        log.exception("Pickup forms not sent")
        return [f"⚠️ AJIO pickup form not sent: {telegram.esc(str(exc)[:150])}"]


def pickup_ticket_report(done: list[dict]) -> list:
    """Telegram: the courier pickup tickets this run raised (or would raise, dry run); [] when none."""
    new = [d for d in done if d["Result"] in ("created", "dry-run")]
    failed = [d for d in done if d["Result"].startswith("error")]
    followed = [d for d in done if d["Result"] == "followed up"]
    if not new and not failed and not followed:
        return []
    dry = any(d["Result"] == "dry-run" for d in new)
    per_ticket: dict[tuple[str, str], int] = {}
    for d in new:
        k = (short_courier(d["Courier"]), d.get("New", ""))
        per_ticket[k] = per_ticket.get(k, 0) + 1
    table = [f"{c[:7]:<7} {n:>6}  {t or '-'}" for (c, t), n in per_ticket.items()]
    n_tickets = len({t for _, t in per_ticket}) if not dry else len(per_ticket)
    lines = [f"🎫 <b>AJIO Pickup Tickets · {len(new)} orders, {n_tickets} courier "
             f"{'ticket' if n_tickets == 1 else 'tickets'}{' to raise (dry run)' if dry else ' raised'}</b>",
             "<i>ORDERS › Pickup not done, one ticket per courier with its orders listed</i>"]
    picked = sum(d["Result"] == "courier: picked" for d in done)
    unchecked = sum(d["Result"] == "courier: not checked" for d in done)
    if picked or unchecked:
        lines.append(f"Not raised: {picked} picked per the courier's site"
                     + (f", {unchecked} courier site not reachable" if unchecked else ""))
    if followed:
        tickets = list(dict.fromkeys(d["Ticket"].split(", ")[-1] for d in followed))
        lines.append(f"🔁 Followed up {len(tickets)} courier tickets ({len(followed)} orders still not picked "
                     f"up): " + ", ".join(tickets[:15]) + (" …" if len(tickets) > 15 else ""))
    if failed:
        lines.append(f"⚠️ {len(failed)} failed: " + ", ".join(d["Order ID"] for d in failed[:10]))
    if table:
        rows = [{k: v for k, v in d.items() if k != "New"} for d in done]
        lines.append(telegram.Listing("", ["<pre>" + telegram.esc(f"{'Courier':<7} {'Orders':>6}  Ticket\n"
                                                                 + "\n".join(table)) + "</pre>"],
                                      rows, "Pickup tickets"))
    return lines


SCORE_COMMENT = """You are the e-commerce manager of Bindal Exports, an AJIO seller. Below is the courier
pickup scorecard of the last 7 order days. Write 2 or 3 lines: which courier is the problem and how
bad, and whether the delay is on our side (processing late) or the courier's (pickup late). Say only
what the numbers show.""" + MOBILE


def courier_scorecard(df: pl.DataFrame, now: datetime | None = None) -> str:
    """Third Telegram message: per courier, orders of the last COURIER_DAYS (7) complete order
    days, pickups on time / late / overdue and the on-time %; who was late on the last day's NOT
    CORRECT orders (our processing or the courier's pickup); and an alert for a courier under
    COURIER_ALERT_PCT (70) % on time COURIER_ALERT_DAYS (3) order days in a row. "" when no orders.

    A day is complete when every deadline of its orders has passed: an order of day D is due by
    D + 1 (10:10 rule), so at the 5:30 PM run the last complete day is the day before yesterday."""
    now = now or datetime.now()
    yday = datetime.combine(now.date(), datetime.min.time()) - timedelta(days=2)       # the last complete order day
    first = yday - timedelta(days=num("COURIER_DAYS", 7) - 1)
    live = (df.filter((pl.col("Pickup Status") != "Cancelled").fill_null(True))
              .with_columns(pl.col("Order Time").dt.truncate("1d").alias("_day"))
              .filter((pl.col("_day") >= first) & (pl.col("_day") <= yday)))
    if not live.height:
        return ""
    live = live.with_columns((pl.col("Pickup Status") == "On Time").fill_null(False).alias("_on"),
                             ((pl.col("Pickup Status") == "Late").fill_null(False) | pickup_pending(now)).alias("_late"))
    names = {c: short_courier(c) for c in live["Courier"].fill_null("UNKNOWN").unique().to_list()}
    live = live.with_columns(pl.col("Courier").fill_null("UNKNOWN").replace_strict(names, return_dtype=pl.Utf8).alias("_c"))

    def pct(g: pl.DataFrame) -> int | None:
        on, late = int(g["_on"].sum()), int(g["_late"].sum())
        return round(100 * on / (on + late)) if on + late else None

    rows, alerts = [], []
    days = [first + timedelta(days=i) for i in range((yday - first).days + 1)]
    limit, run_len = num("COURIER_ALERT_PCT", 70), int(num("COURIER_ALERT_DAYS", 3))
    groups = sorted(((c, live.filter(pl.col("_c") == c)) for c in sorted(live["_c"].unique().to_list())), key=lambda kv: -kv[1].height)
    for courier, g in groups:
        y = pct(g.filter(pl.col("_day") == yday))
        rows.append(f"{courier[:7]:<7}{g.height:>5}{int(g['_late'].sum()):>5}"
                    f"{(str(pct(g)) + '%') if pct(g) is not None else '-':>5}{(str(y) + '%') if y is not None else '-':>6}")
        streak = []
        for d in reversed(days):
            gd = g.filter(pl.col("_day") == d)
            p = pct(gd)
            if p is None or gd.height < 5 or p >= limit:
                break
            streak.append(p)
        if len(streak) >= run_len:
            alerts.append(f"⚠️ {courier}: pickup on time under {limit:.0f}% for {len(streak)} days in a row "
                          f"({', '.join(f'{p}%' for p in reversed(streak))})")
    tot = pct(live)
    table = [f"{'Courier':<7}{'Ord':>5}{'Late':>5}{'OnT%':>5}{format(yday, '%d%b'):>6}", *rows,
             f"{'Total':<7}{live.height:>5}{int(live['_late'].sum()):>5}{(str(tot) + '%') if tot is not None else '-':>5}"]
    bad = live.filter((pl.col("_day") == yday) & (pl.col("TAT Result") == "NOT CORRECT"))
    ours = int((bad["Process Status"] != "On Time").fill_null(True).sum())
    lines = [f"🚚 <b>AJIO Courier Pickup · {first:%d %b} - {yday:%d %b}</b>",
             "<i>order days whose deadlines have all passed</i>",
             "<pre>" + telegram.esc("\n".join(table)) + "</pre>",
             f"NOT CORRECT on {yday:%d %b}: <b>{bad.height}</b> · our side (processing late) {ours} · "
             f"courier side (pickup late) {bad.height - ours}",
             *alerts,
             "<i>Late = picked after the deadline or still waiting past it; OnT% = on time / (on time + late); "
             "picked with no time known is left out</i>"]
    try:
        from ultron.core import llm
        plain = "\n".join(table) + f"\nNOT CORRECT on {yday:%d %b}: {bad.height}, ours {ours}, courier {bad.height - ours}\n" + "\n".join(alerts)
        note = tidy(llm.chat([{"role": "system", "content": SCORE_COMMENT}, {"role": "user", "content": plain}],
                             max_tokens=1200)["choices"][0]["message"].get("content") or "")
        if note:
            lines += ["", "🧠 <b>Ultron's take</b>\n" + telegram.md(note)]
    except Exception as exc:  # noqa: BLE001 - the scorecard goes out without the lines
        log.warning("No scorecard comment: %s", exc)
    return "\n".join(lines)


def dashboard_data(df: pl.DataFrame) -> dict:
    """Day-wise TAT for the last 45 order days, the month's courier table, and every AWB
    still waiting for pickup."""
    now = datetime.now()
    today = _today()
    live = (df.filter((pl.col("Pickup Status") != "Cancelled").fill_null(True))
              .with_columns(pl.col("Order Time").dt.truncate("1d").alias("_day")))
    picked = pl.col("Pickup Status").is_in(PICKED).fill_null(False)
    not_proc = (pl.col("Process Status") == "Not Processed").fill_null(False)
    over = pickup_pending(now)
    count = lambda col, v: (pl.col(col) == v).fill_null(False).sum()  # noqa: E731
    g = (live.filter((pl.col("_day") >= today - timedelta(days=44)).fill_null(False)).group_by("_day")
             .agg(pl.len().alias("orders"), count("Process Status", "On Time").alias("on_time"), count("Process Status", "Late").alias("late"),
                  count("Process Status", "Not Processed").alias("not_processed"), picked.sum().alias("picked"),
                  over.sum().alias("pickup_overdue"), count("TAT Result", "CORRECT").alias("correct"),
                  count("TAT Result", "NOT CORRECT").alias("not_correct"), count("TAT Result", "PENDING").alias("pending"))
             .sort("_day"))
    days = [{"date": r["_day"].date(), **{k: int(v) for k, v in r.items() if k != "_day"}} for r in g.iter_rows(named=True)]
    month = live.filter((pl.col("_day") >= today.replace(day=1)).fill_null(False))
    c = (month.group_by(pl.col("Courier").fill_null("UNKNOWN").alias("_c"))
              .agg(pl.len().alias("orders"), picked.sum().alias("done"), over.sum().alias("pend"),
                   (~picked & ~not_proc & ~over).sum().alias("due"), not_proc.sum().alias("proc")).sort("_c"))
    couriers = [{"courier": short_courier(r["_c"]), **{k: int(r[k]) for k in ("orders", "done", "pend", "due", "proc")}}
                for r in c.iter_rows(named=True)]
    since = today - timedelta(days=num("TRACK_DAYS", 15))
    pend = df.filter(awaiting_pickup() & (pl.col("Order Time") >= since).fill_null(False)).sort("Order Time", nulls_last=True, maintain_order=True)
    pickup = [{"awb": str(r["AWB"]), "courier": short_courier(r["Courier"]),
               "over": bool(r["Dispatch Deadline"] is not None and r["Dispatch Deadline"] < now),
               "order_time": r["Order Time"], "ready": r["RTS Time"]}
              for r in pend.head(500).iter_rows(named=True)]
    return {"at": now, "days": days, "couriers": couriers, "pickup_pending": pickup}


# ------------------------------------------------------------------ main

def run(args) -> int:
    mode = env("RUN_MODE", "local")
    out = output_dir("ajio_tat")
    sheet = None
    sheet_id = env("TAT_GOOGLE_SHEET_ID")
    if sheet_id and not args.no_sheet:
        from .sheets import MasterSheet
        sheet = MasterSheet(sheet_id)
    drive = folder = None
    if not args.no_drive and env("TAT_DRIVE_FOLDER_ID"):
        # the master lives in a Drive folder (AGENT WORK/AJIO/Ajio Daily Order Tat Check Working) by name:
        # updated in place when it is there, created when it is not (e.g. moved or deleted)
        from ..core.drive import DriveFile, DriveFolder
        folder = DriveFolder(env("TAT_DRIVE_FOLDER_ID"))
        found = folder.children().get(MASTER_NAME)
        drive = DriveFile(found["id"]) if found else None
        if not found:
            log.info("No %s in the Drive folder yet: it will be created", MASTER_NAME)
    elif not args.no_drive and env("TAT_DRIVE_FILE_ID"):
        from ..core.drive import DriveFile
        drive = DriveFile(env("TAT_DRIVE_FILE_ID"))
    # the working copy of the Drive master stays off Google Drive for desktop: saved under G:\My Drive
    # the file came out damaged (bad CRC) after the save check passed, and that copy got uploaded
    drive_copy = (out if "my drive" not in str(out).lower() else
                  Path(tempfile.gettempdir()) / "bindal" / "ajio_tat") / "drive" / MASTER_NAME

    # 1) master state
    if args.seed_xlsx:
        old = normalize_master(read_excel_text(Path(args.seed_xlsx), "_data"))
        old_as_of = None
        log.info("Seeding from %s: %d orders", args.seed_xlsx, old.height)
        if sheet:
            cur, _ = sheet.read_master()
            old = pl.concat([old, cur], how="vertical_relaxed").unique("Invoice No", keep="last", maintain_order=True)
    elif drive:
        old, old_as_of = read_master_xlsx(drive.download(drive_copy, need_edit=True))
    elif folder and env("TAT_DRIVE_FILE_ID"):
        # no master in the folder yet: start from the old master file (readable even in the trash)
        from ..core.drive import DriveFile
        old_file = DriveFile(env("TAT_DRIVE_FILE_ID"))
        old, old_as_of = read_master_xlsx(old_file.download(out / "seed" / MASTER_NAME))
        log.info("Master seeded from the old file %s", old_file.name)
    elif folder:
        old, old_as_of = normalize_master(None), None
    elif sheet:
        old, old_as_of = sheet.read_master()
    else:
        old, old_as_of = read_master_xlsx(master_xlsx())
    log.info("Master loaded: %d orders", old.height)

    # 2) OMSGuru, date-wise: open order pages only for orders that are new or still open
    old_status = apply_status(old, datetime.now()) if old.height else old.with_columns(pl.lit(None, dtype=pl.Utf8).alias("Pickup Status"))
    complete = set(old_status.filter(~needs_oms_refresh())["Order ID"].drop_nulls().cast(pl.Utf8).to_list())
    start, end = oms_window(args)
    o, hist, errors = fetch_oms(start, end, complete, csv_list_of(args.orders))

    # 3) courier tracking, only where pickup is not confirmed yet
    (summ, ev), n_awbs, track_errors = track(awbs_to_track(o, old_status))
    errors += track_errors
    if not o.height:
        new, as_of = normalize_master(None), datetime.now()
    else:
        new, as_of = build_report(o, hist, summ, ev)

    # 4) merge + rules
    merged, stats = merge_master(old, new)
    merged = merged.with_columns(dispatch_deadlines(merged))
    merged = apply_tracking(merged, summ, ev)
    if ev.height:
        as_of = max(as_of, ev["ts"].max())
    if old_as_of is not None:
        as_of = max(as_of, old_as_of)
    merged = ajio_report(erp_labels(merged, start, errors), errors,
                         since=datetime.now() - timedelta(days=num("AJIO_PICKUP_DAYS", 30)))
    df = apply_status(merged, as_of)
    df, tickets = pickup_tickets(df, args, errors)
    if tickets:     # at once: what was posted on the portal must be told even if the master's upload then fails (3 Nov 2026)
        telegram.send_report(tickets, "AJIO_pickup_tickets", dry=args.no_telegram)
    s = summarize(df)
    note = (f"OMSGuru {start:%d-%b} to {end - timedelta(days=1):%d-%b} ({o.height} lines read) "
            f"+ courier tracking ({n_awbs} open AWBs)")
    log.info("Master after merge: %d (new %d, updated %d, kept %d)", df.height, stats["new"],
             stats["updated"], stats["kept (not in input)"])

    # 5) outputs
    if drive:
        if not drive.meta:  # seeded run: fetch Drive's current file (backup + change check on upload)
            drive.download(drive_copy, need_edit=True)
        save_master_xlsx(df, drive_copy, note, as_of)
        drive.upload(drive_copy)
    elif folder:
        save_master_xlsx(df, drive_copy, note, as_of)
        folder.put(drive_copy, XLSX)
    if args.xlsx or not (sheet or drive):
        save_master_xlsx(df, master_xlsx(), note, as_of)
    if sheet:
        sheet.write_all(df, as_of, note, s)
        sheet.append_run_log([datetime.now(), mode, o.height, n_awbs, df.height, stats["new"], stats["updated"],
                              s["tat"]["CORRECT"], s["tat"]["NOT CORRECT"], s["tat"]["PENDING"],
                              s["tat"]["CHECK"], round(s["tat_pct"], 4), len(errors)])
    (out / "errors.log").write_text("\n".join(errors), encoding="utf-8")   # emptied on a clean run
    report = telegram_report(df)
    if errors:
        report += ("\n\n\u26a0\ufe0f <b>Notes</b>\n"
                   f"\u2022 {len(errors)} order page / tracking lookups failed; those orders keep their "
                   "last known status (list in the run's errors.log)")
    score = courier_scorecard(df)
    if args.no_telegram:
        print(report)
        print(score)
    else:
        telegram.send(report)
        if score:
            telegram.send(score)
        pending = pickup_pending_report(df)
        if pending:
            telegram.send_report(pending, "AJIO_pickup_pending", excel=True)   # the Excel has the ticket ids
    dashboard.publish("ajio_tat", {**dashboard_data(df), "lookup_errors": len(errors)})
    for result, n in df.group_by("TAT Result").len().sort("len", descending=True, maintain_order=True).iter_rows():
        print(f"{result}  {n}")
    return 0


def probe(args) -> int:
    """Login + list only: checks credentials and page layout without writing anything."""
    client = clients.omsguru()
    end = datetime.now() + timedelta(days=1)
    channels = csv_list("AJIO_CHANNEL_IDS", "57285,34958")
    whs = warehouse_ids() or list(client.warehouses()) or [None]
    sample = []
    for wh in whs:
        if wh:
            client.set_warehouse(wh)
        ids = client.list_order_ids(end - timedelta(days=args.days + 1), end, channels)
        print(f"Warehouse {wh or 'current'}: {len(ids)} AJIO orders in the last {args.days} days")
        if ids and not sample:
            sample = ids[:3]
            o, h, err = client.fetch_orders(sample)
            shown = [c for c in ("Input Identifier", "Channel Order ID", "Item Status", "Order Date", "Invoice Date",
                                 "Dispatch Log", "AWB / Shipment Tracker", "Shipping Company") if c in o.columns]
            with pl.Config(tbl_cols=-1, tbl_width_chars=250, fmt_str_lengths=60):
                print(o.select(shown))
            print(f"{len(h)} status-history rows; errors: {err}")
    print("Login OK.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py ajio-tat", description="AJIO dispatch TAT bot")
    p.add_argument("--days", type=int, default=num("TAT_LOOKBACK_DAYS", 1),
                   help="OMSGuru window: today plus this many previous days (default 1 = yesterday + today)")
    p.add_argument("--from", dest="from_date", help="OMSGuru order date from, YYYY-MM-DD (overrides the automatic window)")
    p.add_argument("--to", dest="to_date", help="OMSGuru order date to, YYYY-MM-DD (default today)")
    p.add_argument("--xlsx", action="store_true", help="also write the xlsx master (data/AJIO_TAT_MASTER.xlsx or TAT_XLSX_PATH)")
    p.add_argument("--no-sheet", action="store_true", help="skip Google Sheets (local xlsx master only)")
    p.add_argument("--no-drive", action="store_true", help="ignore TAT_DRIVE_FILE_ID (use the local xlsx)")
    p.add_argument("--no-telegram", action="store_true", help="do not send the Telegram message")
    p.add_argument("--seed-xlsx", help="one-time: load an existing AJIO_TAT_MASTER.xlsx into the master")
    p.add_argument("--orders", help="also add these AJIO orders, whatever their date: comma / space separated "
                                     "FN... / EX... customer order numbers, seller order numbers, invoices or AWBs")
    p.add_argument("--tickets", action="store_true",
                   help="raise an AJIO 'pickup not done' ticket per order whose pickup deadline has passed "
                        "(also on with AJIO_PICKUP_TICKETS=1)")
    p.add_argument("--tickets-dry", action="store_true", help="list the pickup tickets that would be raised, raise none")
    p.add_argument("--probe", action="store_true", help="test OMSGuru login + listing only")
    return run_bot("AJIO Dispatch TAT report", p, lambda a: probe(a) if a.probe else run(a), argv, key="ajio_tat")
