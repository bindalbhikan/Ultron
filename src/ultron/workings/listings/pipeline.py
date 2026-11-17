"""Listing health (11:30 AM): OMSGuru's channel listings against its stock, channels with inventory
sync on only.

* in stock but 0 listed on the channel (and not capped): the stock is not reaching the channel
* listed more than in stock: the channel can sell what is not there (oversell, cancels)
* capped at 0 (Max Listed Qty 0) while in stock: on purpose or forgotten
* sync failures of the last LISTING_FAIL_DAYS (7) days, the Failed tab, and the UnManaged count

Telegram only, nothing written. The SKUs are listed in the message when they fit in one,
otherwise every one of them comes in an attached Excel.
"""
from __future__ import annotations

import argparse
import logging
import re
from collections import Counter
from types import SimpleNamespace
from datetime import datetime, timedelta

import polars as pl

from ..core import telegram
from ..core.app import run_bot
from ..core.config import num
from ..core.tables import pnum, read_text_csv
from ..morning.pipeline import channel_line
from ..stock.pipeline import stock_of
from ..core import clients

log = logging.getLogger("bindal.listings")

FAIL_AT = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2}:\d{2} [AP]M)")


def table_of(blob: bytes) -> "pl.DataFrame":
    """The channel listing export as a Polars table (an empty text "nan", as pandas' astype(str) made it)."""
    df = read_text_csv(blob, pandas_na=True)
    names = {n: channel_line(n) for n in df["Channel Name"].fill_null("nan").unique().to_list()}
    return df.select(
        pl.col("Channel ID").fill_null("nan").str.strip_chars().alias("channel_id"),
        pl.col("Channel Name").fill_null("nan").replace_strict(names, return_dtype=pl.Utf8).alias("channel"),
        pl.coalesce(pl.col("Channel Listing SKU Code"), pl.col("Channel Listing Id")).fill_null("nan").alias("listing"),
        pl.col("Product SkuCode").fill_null("nan").str.strip_chars().str.to_uppercase().alias("sku"),
        pnum(pl.col("Channel Listed Qty")).fill_null(0).cast(pl.Int64).alias("listed"),
        pnum(pl.col("Channel Max Listed Qty")).fill_null(-1).cast(pl.Int64).alias("max"),
        pl.col("Failure Reason").fill_null("").alias("failure"))


def failed_since(text: str, since: datetime) -> bool:
    m = FAIL_AT.match(text or "")
    try:
        return bool(m) and datetime.strptime(m.group(1), "%B %d, %Y %I:%M:%S %p") >= since
    except ValueError:
        return False


def check(listings: "pl.DataFrame", stock: Counter, active: set[str], since: datetime) -> dict:
    df = listings.filter(pl.col("channel_id").is_in(list(active)))
    df = df.with_columns(pl.Series("stock", [max(stock.get(s, 0), 0) for s in df["sku"].to_list()], dtype=pl.Int64),
                         pl.Series("_failed", [failed_since(f, since) for f in df["failure"].to_list()], dtype=pl.Boolean))
    instock = pl.col("stock") > 0
    return {
        "listings": df.height,
        "not_listed": df.filter(instock & (pl.col("max") != 0) & (pl.col("listed") == 0)).drop("_failed"),
        "over": df.filter(pl.col("listed") > pl.col("stock")).drop("_failed"),
        "capped": df.filter(instock & (pl.col("max") == 0)).drop("_failed"),
        "failed": df.filter(pl.col("_failed")).drop("_failed"),
    }


def message(res: dict, failed_tab: list[dict], unmanaged: int, now: datetime, days: int) -> list:
    """A telegram report: the SKU lists inline when the whole report fits in one message, else in an Excel."""
    def per_channel(part: "pl.DataFrame") -> str:
        """Channel counts, the most first (ties in the order they first come)."""
        return " · ".join(f"{telegram.esc(c)} {n}" for c, n in Counter(part["channel"].to_list()).most_common())

    def listing(title: str, part: "pl.DataFrame", show, sheet: str) -> telegram.Listing:
        """One line per channel + SKU (a SKU can have several listings on one channel); the Excel
        has every listing."""
        recs = [SimpleNamespace(**r) for r in part.iter_rows(named=True)]
        n = Counter((r.channel, r.sku) for r in recs)
        uniq = list({(r.channel, r.sku): r for r in reversed(recs)}.values())[::-1]     # the first of each, in order
        lines = [f"• {telegram.esc(r.channel)} · {telegram.esc(r.sku)} · {show(r)}"
                 + (f" · {n[(r.channel, r.sku)]} listings" if n[(r.channel, r.sku)] > 1 else "")
                 for r in uniq]
        rows = [{"Channel": r.channel, "SKU": r.sku, "Listing": r.listing, "Stock": int(r.stock),
                 "Listed": int(r.listed), "Max listed": int(r.max) if r.max >= 0 else None} for r in recs]
        return telegram.Listing(title, lines, rows, sheet)

    out = [f"🏪 <b>Listing health · {now:%d %b}</b>",
           f"<i>{res['listings']:,} listings on channels with inventory sync on, against OMSGuru stock</i>"]
    nl = res["not_listed"].sort("stock", descending=True, maintain_order=True)
    ov = res["over"].sort("listed", descending=True, maintain_order=True)
    out += ["", listing(f"📭 <b>In stock, 0 on the channel: {len(nl)}</b>" + (f" ({per_channel(nl)})" if len(nl) else ""),
                        nl, lambda r: f"stock {r.stock}", "In stock not listed")]
    out += ["", listing(f"⚠️ <b>Listed more than in stock: {len(ov)}</b>" + (f" ({per_channel(ov)})" if len(ov) else ""),
                        ov, lambda r: f"listed {r.listed}, stock {r.stock}", "Listed over stock")]
    fl = res["failed"]
    out += ["", f"❌ <b>Sync failures in the last {days} days: {len(fl)}</b>" + (f" ({per_channel(fl)})" if len(fl) else "")]
    reasons = Counter(re.sub(r"^.*?[AP]M:", "", f).strip()[:70] for f in fl["failure"].to_list())
    out += [f"• {telegram.esc(r)}: {n}" for r, n in reasons.most_common(5)]
    if failed_tab:
        out += ["", telegram.Listing(
            f"🚫 <b>Failed listings tab: {len(failed_tab)}</b>",
            [f"• {telegram.esc(channel_line(f['channel']))} · {telegram.esc(f['sku'])} · "
             f"{telegram.esc(re.sub(r'^.*?[AP]M:', '', f['failure'])[:80])}" for f in failed_tab],
            [{"Channel": channel_line(f["channel"]), "SKU": f["sku"],
              "Failure": re.sub(r"^.*?[AP]M:", "", f["failure"]).strip()} for f in failed_tab],
            "Failed tab")]
    cp = res["capped"]
    out += ["", f"🔒 Capped at 0 while in stock: {len(cp)}" + (f" ({per_channel(cp)})" if len(cp) else ""),
            f"🔗 Not mapped to an OMSGuru SKU (UnManaged): {unmanaged:,}",
            "", "<i>Fix: push inventory / check the mapping for 📭, re-sync or lower the listed qty for ⚠️.</i>"]
    return out


def run(args) -> int:
    now = datetime.now()
    days = int(num("LISTING_FAIL_DAYS", 7))
    client = clients.omsguru()
    active = {c["id"] for c in client.channels() if c["inventory_sync"]}
    warehouses = list(client.warehouses()) or [None]
    blobs = []
    for wh in warehouses:
        if wh:
            client.set_warehouse(wh)
        blobs.append(client.export_inventory(wait_minutes=num("STOCK_EXPORT_WAIT_MINUTES", 12)))
    stock = stock_of(blobs)
    if warehouses[0]:
        client.set_warehouse(warehouses[0])     # the listing pages show the current warehouse's listings
    listings = table_of(client.export_listings(wait_minutes=num("LISTING_EXPORT_WAIT_MINUTES", 15)))
    if not listings.height:
        raise RuntimeError("The channel listing export came back empty")
    res = check(listings, stock, active, now - timedelta(days=days))
    failed_tab, unmanaged = client.failed_listings(), client.unmanaged_count()
    log.info("Listings: %d checked, %d in stock not listed, %d over stock, %d capped, %d failed lately, "
             "%d in the Failed tab, %d unmanaged", res["listings"], len(res["not_listed"]), len(res["over"]),
             len(res["capped"]), len(res["failed"]), len(failed_tab), unmanaged)
    telegram.send_report(message(res, failed_tab, unmanaged, now, days), "Listing_health", dry=args.no_telegram)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py listings", description="Channel listings against OMSGuru stock")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    return run_bot("Listing health", p, run, argv)
