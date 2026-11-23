"""Myntra courier scorecard (6:30 PM): pickups of the Myntra accounts against the dispatch SLA.

Pickup = the Seller_Orders_Report's "fmpu date" (first-mile pickup) of each account (MAIN, DBCC,
FMCC; reports already on the partner portal are reused - the Myntra SPF run asks for them every
morning). Deadline = OMSGuru's SLA Date of the same order, matched on the tracking number (OMSGuru's
AWB for Myntra). Orders of the last MYNTRA_TAT_DAYS (7) complete days (the SLA passed), cancelled
left out. Late on our side = packed after the SLA. Telegram only, nothing written.
"""
from __future__ import annotations

import argparse
import io
import logging
import time
import zipfile
from datetime import date, datetime, timedelta

import polars as pl

from ..core import telegram
from ..core.app import run_bot
from ..core.config import csv_list, env, num
from ..core.tables import read_text_csv
from ..sale.oms_sales import order_lines
from ..core import clients

log = logging.getLogger("bindal.myntra_tat")

ACCOUNTS = ["MAIN", "DBCC", "FMCC"]


def _when(c: str) -> "pl.Expr":
    """A Myntra report date-time ("2026-10-28 16:37:23.000"); empty or unreadable -> null."""
    s = pl.col(c).str.strip_chars()
    return pl.coalesce(s.str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False), s.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False),
                       s.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us")))


def report_frame(files: list[tuple[str, bytes]], account: str) -> "pl.DataFrame":
    """One row per order line of the account's Seller_Orders_Report files (newest file wins)."""
    frames = []
    for _, data in files:
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                data = z.read(next(n for n in z.namelist() if n.lower().endswith(".csv")))
        frames.append(read_text_csv(data, na_words=True))
    if not frames:
        return pl.DataFrame()
    df = pl.concat(frames, how="diagonal_relaxed").unique("order line id", keep="first", maintain_order=True)
    return df.select(
        pl.lit(account).alias("account"),
        pl.col("order tracking number").fill_null("").str.strip_chars().str.to_uppercase().alias("awb"),
        pl.col("courier code").fill_null("?").str.strip_chars().str.to_uppercase().alias("courier"),
        pl.col("order status").fill_null("").alias("status"),
        pl.col("seller order id").fill_null("").str.strip_chars().alias("so"),
        pl.col("po_type").fill_null("").str.strip_chars().str.to_uppercase().alias("po"),
        _when("created on").alias("created"), _when("packed on").alias("packed"),
        _when("fmpu date").alias("pickup"), _when("cancelled on").alias("cancelled"))


def score(rep: "pl.DataFrame", sla: dict[str, datetime], first: date, last: date, now: datetime,
          api_sla: dict[str, datetime] | None = None) -> "pl.DataFrame":
    """The orders of first..last with an SLA, each with on_time / late / ours (packed late). The SLA is Myntra's
    own pack-by time from the Seller API (`api_sla`, by seller order id) and OMSGuru's SLA (by AWB) when the API
    has none for the order (owner, 23 Nov 2026: the API is the main source, OMSGuru the backup)."""
    api_sla = api_sla or {}
    df = rep.filter(pl.col("created").dt.date().is_between(first, last) & pl.col("cancelled").is_null() & (pl.col("awb") != ""))
    sos = df["so"].to_list() if "so" in df.columns else [""] * df.height
    df = df.with_columns(pl.Series("sla", [api_sla.get(s) or sla.get(a) for s, a in zip(sos, df["awb"].to_list())],
                                   dtype=pl.Datetime("us")))
    df = df.filter(pl.col("sla").is_not_null()).unique(["account", "awb"], keep="first", maintain_order=True)
    on_time = pl.col("pickup").is_not_null() & (pl.col("pickup") <= pl.col("sla"))
    df = df.with_columns(on_time.fill_null(False).alias("on_time"))
    df = df.with_columns((~pl.col("on_time") & (pl.col("pickup").is_not_null() | (pl.col("sla") < now))).alias("late"))
    return df.with_columns((pl.col("late") & (pl.col("packed").is_null() | (pl.col("packed") > pl.col("sla"))).fill_null(False))
                           .alias("ours"))


def myntra_sla(client, rep: "pl.DataFrame", first: date, last: date, notes: list[str]) -> dict[str, datetime]:
    """{seller order id: Myntra's pack-by time} of each account's PPMP orders of first..last, from the Seller API
    (the order detail reads delivered and RTO orders too). It equals OMSGuru's SLA (285 of 285 on 23 Nov 2026);
    SJIT / FBM are not in the API and keep OMSGuru's. An account whose API fails keeps OMSGuru's SLA (named)."""
    from ..portals.myntra_api import MyntraApi
    out: dict[str, datetime] = {}
    if not rep.height or "po" not in rep.columns:
        return out
    window = rep.filter(pl.col("created").dt.date().is_between(first, last) & pl.col("cancelled").is_null()
                        & (pl.col("po") == "PPMP") & (pl.col("so") != ""))
    for account in sorted(set(window["account"].to_list())):
        sos = sorted(set(window.filter(pl.col("account") == account)["so"].to_list()))
        try:
            got = MyntraApi.for_account(account, client).lines_of(sos, skip_failed=True)
        except Exception as exc:  # noqa: BLE001 - OMSGuru's SLA stays for the account
            log.warning("Myntra TAT: %s Seller API failed, OMSGuru's SLA used: %s", account, exc)
            notes.append(f"{account}: Seller API failed, OMSGuru's SLA used ({str(exc)[:60]})")
            continue
        for x in got:
            if x["packByTime"]:
                out.setdefault(str(x["sellerOrderId"]), x["packByTime"])
        missing = len(sos) - len({str(x["sellerOrderId"]) for x in got})
        if missing:
            notes.append(f"{account}: {missing} of {len(sos)} PPMP orders not read from the Seller API (OMSGuru's SLA used)")
    return out


def message(df: "pl.DataFrame", first: date, last: date, matched: int, total: int) -> str:
    lines = [f"🛍 <b>Myntra Courier Pickup · {first:%d %b} - {last:%d %b}</b>",
             "<i>pickup (fmpu) against the OMSGuru SLA, by account and courier</i>"]
    table = [f"{'Acct':<5}{'Courier':<8}{'Ord':>5}{'Late':>5}{'OnT%':>5}"]   # 28 wide: a phone
    groups = (df.group_by(["account", "courier"])
                .agg(pl.len().alias("n"), pl.col("on_time").sum().alias("on"), pl.col("late").sum().alias("late"))
                .sort(["account", "courier"]))
    # by account, the most orders first; equal ones in courier order (as pandas' sorted groups gave them)
    for acct, courier, size, on, lt in sorted(groups.iter_rows(), key=lambda g: (g[0], -g[2])):
        n = int(on + lt)
        pct = f"{round(100 * on / n)}%" if n else "-"
        table.append(f"{acct:<5}{courier[:7]:<8}{size:>5}{int(lt):>5}{pct:>5}")
    on_all, late_all = int(df["on_time"].sum()), int(df["late"].sum())
    n = on_all + late_all
    table.append(f"{'Total':<13}{df.height:>5}{late_all:>5}"
                 + (f"{round(100 * on_all / n)}%" if n else "-").rjust(5))
    late = df.filter(pl.col("late"))
    ours = int(late["ours"].sum())
    lines += ["<pre>" + telegram.esc("\n".join(table)) + "</pre>",
              f"Late: <b>{late.height}</b> · our side (packed after the SLA) {ours} · "
              f"courier side {late.height - ours}",
              f"<i>{matched} of {total} report orders with an SLA (Myntra's pack-by time, else OMSGuru's)</i>"]
    return "\n".join(lines)


def run(args) -> int:
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    now = datetime.now()
    last = now.date() - timedelta(days=2)                  # every SLA passed
    first = last - timedelta(days=int(num("MYNTRA_TAT_DAYS", 7)) - 1)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    reps, notes = [], []
    for account in csv_list("MYNTRA_TAT_ACCOUNTS") or ACCOUNTS:
        try:
            try:
                portal = myntra_portal(account)
            except mp.SessionExpired:
                raise
            except Exception as exc:  # noqa: BLE001 - the portal answers 500 now and then: once more
                log.warning("Myntra %s portal check failed (%s): trying again", account, exc)
                time.sleep(20)
                portal = myntra_portal(account)
            files, covered = portal.reports(days, wait_minutes=num("MYNTRA_TAT_WAIT_MINUTES", 15))
            mp.save_to_worker(env, portal.cookies(), account)
            reps.append(report_frame(files, account))
            if set(days) - covered:
                notes.append(f"{account}: report does not cover {len(set(days) - covered)} of the days")
        except Exception as exc:  # noqa: BLE001 - the other accounts still count
            log.warning("Myntra %s report not read: %s", account, exc)
            notes.append(f"{account}: report not read ({str(exc)[:80]})")
    rep = pl.concat([r for r in reps if r.height], how="diagonal_relaxed") if any(r.height for r in reps) else pl.DataFrame()
    if not rep.height:
        raise RuntimeError("No Myntra order report could be read: " + "; ".join(notes))
    client = clients.omsguru()
    lines, _ = order_lines(client, [first - timedelta(days=1) + timedelta(days=i) for i in range(len(days) + 2)])
    sla = {l["awb"]: l["sla"] for l in lines if l["awb"] and l["sla"]}
    api_sla = myntra_sla(client, rep, first, last, notes)
    total = rep.filter(pl.col("created").dt.date().is_between(first, last) & pl.col("cancelled").is_null()).height
    df = score(rep, sla, first, last, now, api_sla)
    text = message(df, first, last, df.height, total) + ("\n\n⚠️ " + "\n⚠️ ".join(telegram.esc(n) for n in notes) if notes else "")
    log.info("Myntra TAT: %d orders scored of %d, %d late", df.height, total, int(df["late"].sum()))
    print(text) if args.no_telegram else telegram.send(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py myntra-tat", description="Myntra courier pickup scorecard")
    p.add_argument("--no-telegram", action="store_true", help="print the scorecard instead of sending it")
    return run_bot("Myntra courier scorecard", p, run, argv)
