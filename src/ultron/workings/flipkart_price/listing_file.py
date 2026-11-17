"""Flipkart listing file (11 AM daily): every ACTIVE and INACTIVE listing with its price, settlement
and stock, saved to Drive AGENT WORK > FLIPKART > LISTING FILE > <Mon-YY> as
"FLIPKART LISTING FILE <dd-Mon-yy>.xlsx" (owner, 14 Nov 2026). Reads only.

Built from Seller Hub's listing table and stock call: the listing file Seller Hub itself generates
(Listings > Download) gives a link whose download path is not known yet (docs/PORTALS.md). A
listing the table did not return (it shifts while prices change) is counted in the message.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime


from ..core import telegram
from ..core.app import run_bot
from ..core.config import output_dir
from ..core import clients
from ..core.xlsx import write_sheets

log = logging.getLogger("bindal.flipkart_listing_file")

FOLDER = ("FLIPKART", "LISTING FILE")
STATES = ("ACTIVE", "INACTIVE")


def rows_of(listings: list[dict], stock: dict[str, dict]) -> list[dict]:
    out = []
    for x in listings:
        st = stock.get(x["listing_id"]) or {}
        own = st.get("NON_FBF") or []
        fbf = st.get("FBF") or []
        pk = next(iter((x.get("packages") or {}).values()), {}) or {}
        mrp, ssp = x.get("mrp"), x.get("ssp")
        out.append({
            "Seller SKU Id": x.get("sku_id"), "Flipkart Serial Number": x.get("product_id"),
            "Listing ID": x.get("listing_id"), "Title": x.get("title"), "Brand": x.get("brand"),
            "Category": x.get("vertical_display_name") or x.get("vertical"), "Vertical": x.get("vertical"),
            "Listing Status": x.get("internal_state"), "MRP": mrp, "Selling Price": ssp,
            "Bank Settlement": x.get("esp"),
            "Discount %": round(1 - ssp / mrp, 4) if mrp and ssp is not None else None,
            "Service Profile": x.get("service_profile"),
            "Your Stock": sum(int(s.get("quantity") or 0) for s in own) if own else None,
            "Reserved": sum(int(s.get("reserved") or 0) for s in own) if own else None,
            "FBF Stock": sum(int(s.get("quantity") or 0) for s in fbf) if fbf else None,
            "Procurement Type": x.get("procurement_type"),
            "Shipping Days": int(x["shipping_days"] / 86400) if x.get("shipping_days") else None,
            "Shipping Provider": x.get("shipping_provider"), "HSN": x.get("hsn"),
            "Weight (kg)": pk.get("weight"), "Length (cm)": pk.get("length"), "Breadth (cm)": pk.get("breadth"),
            "Height (cm)": pk.get("height"), "Discoverable": x.get("is_discoverable"),
            "Visibility": x.get("visibilityStatePostQc"), "Live Since": x.get("fk_release_date"),
            "Deactivation Reason": ", ".join(map(str, x.get("reason_for_deactivation") or [])) or None,
            "Product URL": f"https://www.flipkart.com{x['url']}" if x.get("url") else None})
    return out


SORT = ("Listing Status", "Brand", "Category", "Seller SKU Id")


def sorted_rows(rows: list[dict]) -> list[dict]:
    """The rows by status, brand, category, SKU, an empty value last in each, ties kept in their order (as pandas'
    sort_values sorted them)."""
    return sorted(rows, key=lambda r: tuple((r.get(c) is None, "" if r.get(c) is None else r.get(c)) for c in SORT))


def run(args) -> int:
    now = datetime.now()
    client = clients.flipkart()
    listings, short = [], []
    for state in STATES:
        got = client.listings(state, complete=False)
        count = client.last_count or 0
        if len(got) < count:
            short.append(f"{state} {len(got):,} of {count:,}")
        listings += got
    stock = client.stock(listings)
    rows = sorted_rows(rows_of(listings, stock))
    name = f"FLIPKART LISTING FILE {now:%d-%b-%y}".upper() + ".xlsx"
    out = output_dir("flipkart-listing-file") / name
    headers = list(rows[0]) if rows else []
    write_sheets(out, {"Listings": (headers, rows)}, bold_header=True, autofilter=True, freeze=(1, 1), links=True,
                 column_widths=[(0, 3, 22), (4, max(len(headers) - 1, 4), 13)])
    log.info("Written %s (%d listings)", out, len(rows))

    link = ""
    if not args.no_upload:
        from ..core.drive import DriveFile, agent_folder
        folder = agent_folder()
        for part in (*FOLDER, f"{now:%b-%y}"):
            folder = folder.subfolder(part, create=True)
        link = DriveFile(folder.put(out, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")).url

    active = [r for r in rows if r["Listing Status"] == "ACTIVE"]
    own = [r["Your Stock"] or 0 for r in active]
    msg = [f"📄 <b>Flipkart listing file · {now:%d %b %H:%M}</b>",
           f"Active {len(active):,} · Inactive {len(rows) - len(active):,}",
           f"Your stock {int(sum(own)):,} units · "
           f"out of stock (active) {sum(1 for s in own if s <= 0):,}",
           *([f"⚠️ Not all listings read: {', '.join(short)}"] if short else []),
           *([f'<a href="{link}">{telegram.esc(name)}</a>'] if link else [])]
    text = "\n".join(msg)
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py flipkart-listing-file", description="Flipkart listing file, daily")
    p.add_argument("--no-upload", action="store_true", help="keep the file in output/, do not put it on Drive")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    return run_bot("Flipkart listing file", p, run, argv)
