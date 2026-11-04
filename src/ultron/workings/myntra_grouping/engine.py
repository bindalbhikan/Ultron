"""The owner's hand-run Myntra colour-grouping checker (LISTING/MYNTRA/Grouping2/main.py), unchanged:
its loaders, portal spider, rules and report, except one change of the owner (2 Nov 2026): NOT GROUPED
is reported as NOT DONE. pipeline.py points its folders at the run's work folder and gives it the bot's
inputs (Drive AGENT WORK/MYNTRA/LISTING GROUPING, the daily listings reports, OMSGuru's inventory).
"""
"""
Myntra color-grouping checker.

Inputs (relative to this file):
  input/GROUPING SHEET.xlsx          - one tab per category, column A holds MY SKUs,
                                       groups are separated by blank rows
  input/*Seller_Listings_Report_<ACCOUNT>.csv
                                     - Myntra listing report, one file per seller account
  input/*inventory*.xlsx|csv         - optional, columns: SKU + qty/inventory/stock
  sale/*.csv                         - Myntra sales export (party_id_to = account)
  MasterSheet.xlsx                   - sheet "Master" (MY SKU / FINAL MY SKU / MYNTRA SKU CODE)

Portal check:
  For every style in a group, the public product API
  https://www.myntra.com/gateway/v2/product/<styleId> is fetched with Scrapy.
  Its "colours" list is the live color group on the portal.
  Responses are cached in output/portal_cache.json.

Output:
  output/GROUPING_ACCOUNT_WISE_<YYYY-MM-DD>.xlsx - one sheet per account + Summary

Usage:
  python main.py                 # fetch missing styles, build report
  python main.py --refresh       # re-fetch every style from the portal
  python main.py --no-fetch      # use cache only (offline)
  python main.py --concurrency 8 # fewer parallel requests if the portal rate-limits
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
SALE_DIR = os.path.join(BASE_DIR, "sale")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
MASTER_FILE = os.path.join(BASE_DIR, "MasterSheet.xlsx")
GROUPING_FILE = os.path.join(INPUT_DIR, "GROUPING SHEET.xlsx")
CACHE_FILE = os.path.join(OUTPUT_DIR, "portal_cache.json")
PORTAL_TEMPLATE_FILE = os.path.join(BASE_DIR, "portal template.xlsx")
TEMPLATE_DIR = os.path.join(OUTPUT_DIR, "templates")

HOME_URL = "https://www.myntra.com/"
PRODUCT_API = "https://www.myntra.com/gateway/v2/product/{}"
# Same request setup as the "Myntra Style ID Scraper" desktop tool.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HOME_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": HOME_URL,
    "x-myntraweb": "yes",
    "x-requested-with": "XMLHttpRequest",
}
CONCURRENT_REQUESTS = 64
DOWNLOAD_DELAY = 0
DOWNLOAD_TIMEOUT = 10
SAVE_EVERY = 200
RETRY_ROUNDS = 3       # automatic re-tries of blocked/failed styles within one run
RETRY_PAUSE = 5        # seconds to wait before round 2 (round 3 waits 2x)

GROUP_TYPE = "Color"
# Only these brands are checked (exact name, case-insensitive).
BRANDS = ["Fashfun", "Murcia", "all about you", "DressBerry"]
HIGH_SALES_MIN = 20
# Sale statuses counted as a sale (returns / restocked are excluded).
SALE_STATUSES = {"delivered", "in_transit"}

REMARK_DONE = "DONE"
REMARK_NOT_DONE = "NOT DONE"
REMARK_EXTRA = "DONE - EXTRA IN PORTAL"
REMARK_NOT_LIVE = "NOT LIVE ON PORTAL"
REMARK_NOT_LISTED = "NOT LISTED"
# Owner's rule (2 Nov 2026): a style in no colour group is as pending as one in an incomplete group -
# one remark, NOT DONE, for both (its own fill and Summary column dropped).
REMARK_NOT_GROUPED = REMARK_NOT_DONE
REMARK_DUPLICATE = "DUPLICATE - NOT IN GROUP"
REMARK_SINGLE = "ONLY 1 LISTED"
REMARK_DONE_OTHER = "DONE IN OTHER ACCOUNT"

COLUMNS = [
    "Unique ID", "Group Type", "Category", "Article Type", "Style ID", "SKU", "FINAL SKU", "Brand",
    "GROUPING REMARK", "STATUS", "REMARK", "INV", "SALE", "REMARK2", "ACTION",
    "PORTAL COLOR", "MISSING IN PORTAL", "PORTAL GROUP", "COMPLETE IN",
]


def norm(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().upper()


# ---------------------------------------------------------------- loaders

def load_grouping_sheet(path):
    """Return a list of (category, [sku, ...]) groups in sheet order."""
    wb = load_workbook(path, read_only=True, data_only=True)
    groups = []
    for ws in wb.worksheets:
        category = ws.title.strip()
        current = []
        for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
            sku = norm(row[0])
            if sku.startswith("GROUPING"):
                continue
            if not sku:
                if current:
                    groups.append((category, current))
                current = []
            elif sku not in current:
                current.append(sku)
        if current:
            groups.append((category, current))
    wb.close()
    return groups


def load_master(path):
    cols = ["Channel Name", "MY SKU", "SIZE SKU", "FINAL MY SKU", "MYNTRA STYLE ID", "MYNTRA SKU CODE"]
    df = pd.read_excel(path, sheet_name="Master", usecols=cols, dtype=str)
    for c in cols:
        df[c] = df[c].map(norm)
    final_map = (
        df[df["MY SKU"] != ""].drop_duplicates("MY SKU").set_index("MY SKU")["FINAL MY SKU"].to_dict()
    )
    size_final_map = (
        df[df["SIZE SKU"] != ""].drop_duplicates("SIZE SKU").set_index("SIZE SKU")["FINAL MY SKU"].to_dict()
    )
    myntra = df[df["Channel Name"].str.startswith("MYNTRA") & (df["MYNTRA SKU CODE"] != "")]
    code_map = myntra.drop_duplicates("MYNTRA SKU CODE").set_index("MYNTRA SKU CODE")["MY SKU"].to_dict()
    style_map = (
        myntra[myntra["MYNTRA STYLE ID"] != ""]
        .drop_duplicates("MYNTRA STYLE ID").set_index("MYNTRA STYLE ID")["MY SKU"].to_dict()
    )
    return {
        "my_skus": set(final_map),
        "final": final_map,
        "size_final": size_final_map,
        "code": code_map,
        "style": style_map,
    }


def guess_my_sku(van, my_skus):
    """Strip brand prefix (and size suffix) from a VAN / seller SKU until it matches a MY SKU."""
    parts = norm(van).split("-")
    for end in (len(parts), len(parts) - 1):
        for start in range(min(3, end)):
            candidate = "-".join(parts[start:end])
            if candidate in my_skus:
                return candidate
    return ""


def load_listings(master):
    """Return one row per (account, style id) with brand, MY SKU and status."""
    frames = []
    for path in glob.glob(os.path.join(INPUT_DIR, "*Seller_Listings_Report*.csv")):
        match = re.search(r"_(\d+)\.csv$", path)
        if not match:
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        df["account"] = match.group(1)
        frames.append(df)
    if not frames:
        sys.exit("No Seller_Listings_Report CSV found in input/")
    df = pd.concat(frames, ignore_index=True)
    df["my_sku"] = df["sku code"].map(norm).map(master["code"]).fillna("")
    missing = df["my_sku"] == ""
    df.loc[missing, "my_sku"] = df.loc[missing, "van"].map(lambda v: guess_my_sku(v, master["my_skus"]))
    missing = df["my_sku"] == ""
    df.loc[missing, "my_sku"] = df.loc[missing, "seller sku code"].map(
        lambda v: guess_my_sku(v, master["my_skus"])
    )

    def style_status(values):
        values = list(values)
        return "Active" if "Active" in values else (values[0] if values else "")

    styles = (
        df.groupby(["account", "style id"])
        .agg(
            brand=("brand", "first"),
            article=("article type", "first"),
            my_sku=("my_sku", lambda s: next((x for x in s if x), "")),
            status=("listing status description", style_status),
        )
        .reset_index()
        .rename(columns={"style id": "style_id"})
    )
    sku_to_style = df.drop_duplicates("sku code").set_index("sku code")["style id"].to_dict()
    return styles, sku_to_style


def load_sales(sku_to_style):
    files = glob.glob(os.path.join(SALE_DIR, "*.csv"))
    if not files:
        print("WARNING: no sale files found in sale/")
        return {}
    cols = ["sale_order_code", "product_sku_code", "order_item_status", "party_id_to"]
    df = pd.concat([pd.read_csv(f, usecols=cols, dtype=str) for f in files], ignore_index=True)
    df = df.drop_duplicates("sale_order_code")
    df = df[df["order_item_status"].str.lower().isin(SALE_STATUSES)]
    df["style_id"] = df["product_sku_code"].map(sku_to_style)
    counts = df.dropna(subset=["style_id"]).groupby(["party_id_to", "style_id"]).size()
    return {(str(a), str(s)): int(n) for (a, s), n in counts.items()}


def load_inventory(master):
    """Optional inventory file -> {FINAL SKU: qty}."""
    files = [
        f for f in glob.glob(os.path.join(INPUT_DIR, "*"))
        if "inventory" in os.path.basename(f).lower() and f.lower().endswith((".xlsx", ".xls", ".csv"))
    ]
    if not files:
        return None
    inv = {}
    for path in files:
        df = pd.read_csv(path, dtype=str) if path.lower().endswith(".csv") else pd.read_excel(path, dtype=str)
        sku_col = next((c for c in df.columns if "sku" in str(c).lower()), None)
        qty_col = next(
            (c for c in df.columns if re.search(r"qty|quantity|inventory|stock|inv", str(c), re.I) and c != sku_col),
            None,
        )
        if not sku_col or not qty_col:
            print(f"WARNING: could not find SKU/qty columns in {os.path.basename(path)}, skipped")
            continue
        for sku, qty in zip(df[sku_col].map(norm), pd.to_numeric(df[qty_col], errors="coerce").fillna(0)):
            final = master["size_final"].get(sku) or master["final"].get(sku) or sku
            inv[final] = inv.get(final, 0) + int(qty)
    return inv


# ---------------------------------------------------------------- portal (Scrapy)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return cacheable(json.load(f))
    return {}


def save_cache(cache):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1)


def cacheable(results):
    """Only definitive answers (200 / 404) are cached; blocked or failed styles are retried next run."""
    return {sid: r for sid, r in results.items() if r.get("http") in (200, 404)}


def fetch_portal(style_ids, cache, concurrency=CONCURRENT_REQUESTS):
    """Fetch the live color group of each style with Scrapy and merge into cache."""
    if not style_ids:
        return
    import scrapy
    from scrapy import signals
    from scrapy.crawler import CrawlerProcess
    from scrapy.exceptions import DontCloseSpider
    from twisted.internet.task import LoopingCall

    results = {}

    class MyntraColorSpider(scrapy.Spider):
        name = "myntra_colors"
        custom_settings = {"HTTPERROR_ALLOW_ALL": True}

        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super().from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider.on_idle, signal=signals.spider_idle)
            return spider

        async def start(self):
            self.started_at = time.time()
            self.round = 1
            self.round_ended_at = None
            self.ticker = LoopingCall(self.show_progress)
            self.ticker.start(1, now=False)
            yield self.seed_request(style_ids)

        def seed_request(self, sids):
            # Seed session cookies from the home page (fresh jar per round), then dispatch the API calls.
            return scrapy.Request(
                HOME_URL, headers=HOME_HEADERS, callback=self.dispatch, errback=self.dispatch,
                cb_kwargs={"sids": sids}, meta={"cookiejar": self.round, "handle_httpstatus_all": True},
                dont_filter=True,
            )

        def dispatch(self, _, sids=None):
            for sid in sids if sids is not None else _.request.cb_kwargs["sids"]:
                yield scrapy.Request(
                    PRODUCT_API.format(sid), headers=API_HEADERS, callback=self.parse,
                    errback=self.on_error, cb_kwargs={"sid": sid}, dont_filter=True,
                    meta={"cookiejar": self.round, "handle_httpstatus_all": True},
                )

        def on_idle(self):
            """When a round finishes, automatically retry blocked/failed styles with a fresh session."""
            pending = [sid for sid in style_ids if sid in results and results[sid].get("http") not in (200, 404)]
            if not pending or self.round >= RETRY_ROUNDS:
                return
            if self.round_ended_at is None:
                self.round_ended_at = time.time()
            wait = RETRY_PAUSE * self.round
            if time.time() - self.round_ended_at < wait:
                raise DontCloseSpider
            self.round += 1
            self.round_ended_at = None
            self.slow_down()
            print(f"\n  Round {self.round}/{RETRY_ROUNDS}: retrying {len(pending)} blocked/failed styles ...",
                  flush=True)
            self.crawler.engine.crawl(self.seed_request(pending))
            raise DontCloseSpider

        def slow_down(self):
            """Halve per-domain concurrency for retry rounds (portal may be rate-limiting)."""
            try:
                for slot in self.crawler.engine.downloader.slots.values():
                    slot.concurrency = max(4, slot.concurrency // 2)
            except AttributeError:
                pass

        def parse(self, response, sid):
            record = {"http": response.status, "fetched": datetime.now().isoformat(timespec="seconds")}
            try:
                style = json.loads(response.text).get("style") or {}
            except ValueError:
                style = {}
            if response.status == 200 and style.get("id"):
                record.update(
                    live=True,
                    color=style.get("baseColour") or "",
                    colours=[
                        {"styleId": str(c.get("styleId")), "label": c.get("label", "")}
                        for c in (style.get("colours") or [])
                    ],
                )
            else:
                record.update(live=False, colours=[])
            self.store(sid, record)

        def on_error(self, failure):
            sid = failure.request.cb_kwargs["sid"]
            self.store(sid, {"http": 0, "live": False, "colours": [], "error": repr(failure.value)[:200]})

        def store(self, sid, record):
            results[sid] = record
            if len(results) % SAVE_EVERY == 0:
                save_cache({**cache, **cacheable(results)})

        def show_progress(self, final=False):
            total = len(style_ids)
            done = len(results)
            live = sum(r["live"] for r in results.values())
            codes = Counter(r.get("http", 0) for r in results.values())
            failed = sum(n for code, n in codes.items() if code not in (200, 404))
            elapsed = time.time() - self.started_at
            rate = done / elapsed if elapsed else 0
            eta = f"{(total - done) / rate:.0f}s" if rate else "-"
            line = (
                f"  [{done}/{total}] {done * 100 // total}%  live: {live}  "
                f"not live: {done - live - failed}  blocked/errors: {failed}  "
                f"{rate:.1f}/s  ETA {eta}  elapsed {elapsed:.0f}s"
            )
            if self.round > 1:
                line = f"  round {self.round}" + line
            if done == 0 and elapsed >= 10:
                line += "  (no reply from portal yet...)"
            print("\r" + line.ljust(110), end="\n" if final else "", flush=True)

        def closed(self, reason):
            if self.ticker.running:
                self.ticker.stop()
            self.show_progress(final=True)

    settings = {
        "LOG_LEVEL": "ERROR",
        "CONCURRENT_REQUESTS": concurrency,
        "CONCURRENT_REQUESTS_PER_DOMAIN": concurrency,
        "DOWNLOAD_DELAY": DOWNLOAD_DELAY,
        "DOWNLOAD_TIMEOUT": DOWNLOAD_TIMEOUT,
        "AUTOTHROTTLE_ENABLED": False,
        "RETRY_TIMES": 1,
        "RETRY_HTTP_CODES": [429, 500, 502, 503, 504, 522, 524, 408],
        "COOKIES_ENABLED": True,
        "TELNETCONSOLE_ENABLED": False,
    }
    if USER_AGENT:
        settings["USER_AGENT"] = USER_AGENT

    print(f"Fetching {len(style_ids)} styles from Myntra ...")
    process = CrawlerProcess(settings)
    process.crawl(MyntraColorSpider)
    process.start()

    good = cacheable(results)
    cache.update(good)
    save_cache(cache)
    failed = len(results) - len(good)
    if failed:
        codes = Counter(r.get("http", 0) for r in results.values() if r.get("http") not in (200, 404))
        print(f"WARNING: {failed} styles still failed after {RETRY_ROUNDS} rounds {dict(codes)} - "
              "they will be retried automatically on the next run.")
    if results and not good:
        print("WARNING: every request was blocked by the portal. Run again after some time.")


# ---------------------------------------------------------------- report

def build_account_rows(account, groups, styles, master, sales, inventory, cache):
    acc = styles[styles["account"] == account]
    by_brand_sku = {}
    for r in acc.itertuples():
        by_brand_sku.setdefault((r.brand, r.my_sku), []).append(r)
    style_info = {r.style_id: r for r in acc.itertuples()}
    brands = sorted(acc["brand"].unique(), key=str.lower)
    # Article type of a SKU across all accounts, used when the SKU is not listed in this brand.
    any_article = (
        styles[styles["article"] != ""].groupby("my_sku")["article"]
        .agg(lambda s: s.value_counts().index[0]).to_dict()
    )

    def split_by_article(skus, brand):
        """Myntra only groups styles of the same article type (e.g. Shirts and Tops cannot be grouped).

        Split is done per style: one SKU listed as both Shirts and Tops lands in both blocks.
        Returns [(article, [(sku, [styles of that article]), ...]), ...].
        """
        parts = {}
        for sku in skus:
            listed = by_brand_sku.get((brand, sku), [])
            if not listed:
                parts.setdefault(any_article.get(sku, ""), []).append((sku, []))
                continue
            by_article = {}
            for r in listed:
                by_article.setdefault(r.article, []).append(r)
            for article, rs in by_article.items():
                parts.setdefault(article, []).append((sku, rs))
        if "" in parts and len(parts) > 1:
            # Unknown article type: keep with the largest known part.
            unknown = parts.pop("")
            max(parts.values(), key=len).extend(unknown)
        return list(parts.items())

    def sku_of_style(sid):
        info = style_info.get(sid)
        if info is not None and info.my_sku:
            return info.my_sku
        return master["style"].get(sid, "")

    def portal(sid):
        return cache.get(sid) or {}

    rows = []
    uid = 0
    blocks = [
        (gi, category, brand, article, part)
        for gi, (category, group_skus) in enumerate(groups)
        for brand in brands
        for article, part in split_by_article(group_skus, brand)
    ]
    for gi, category, brand, article, members in blocks:
        skus = [sku for sku, _ in members]
        if not any(listed for _, listed in members):
            continue
        uid += 1
        expected = {r.style_id for _, listed in members for r in listed}
        live_expected = {sid for sid in expected if portal(sid).get("live")}
        portal_union = set()
        for sid in live_expected:
            portal_union.add(sid)
            portal_union.update(c["styleId"] for c in portal(sid).get("colours", []))

        def make_row(sid, sku, remark, action, missing="", status=None):
            final = master["final"].get(sku, sku) if sku else ""
            sale = sales.get((account, sid), 0) if sid else ""
            p = portal(sid) if sid else {}
            group_ids = sorted({sid, *(c["styleId"] for c in p.get("colours", []))}) if p.get("live") else []
            return {
                "_key": (gi, brand, article),
                "Unique ID": f"{uid:03d}",
                "Group Type": GROUP_TYPE,
                "Category": category,
                "Article Type": style_info[sid].article if sid in style_info else article,
                "Style ID": int(sid) if sid and sid.isdigit() else sid,
                "SKU": sku,
                "FINAL SKU": final,
                "Brand": brand,
                "GROUPING REMARK": remark,
                "STATUS": status if status is not None else (style_info[sid].status if sid in style_info else ""),
                "REMARK": "",
                "INV": inventory.get(final, 0) if inventory is not None and final else "",
                "SALE": sale,
                "REMARK2": "HIGH SALES" if isinstance(sale, int) and sale >= HIGH_SALES_MIN else "",
                "ACTION": action,
                "PORTAL COLOR": p.get("color", ""),
                "MISSING IN PORTAL": missing,
                "PORTAL GROUP": ", ".join(group_ids),
            }

        # A SKU can have several style ids (relisted). The group is checked SKU-wise:
        # a SKU is covered when any one of its live styles is in the portal group.
        live_by_sku = {
            sku: [r.style_id for r in listed if r.style_id in live_expected] for sku, listed in members
        }
        live_skus = [sku for sku in skus if live_by_sku.get(sku)]
        grouped_ids = {
            c["styleId"] for sid in live_expected for c in portal(sid).get("colours", [])
        }

        def covered(sid):
            group = {sid, *(c["styleId"] for c in portal(sid).get("colours", []))}
            return frozenset(s for s in live_skus if any(x in group for x in live_by_sku[s]))

        # Main portal group = the live group covering most SKUs of this block. Its styles are DONE
        # even if some SKUs are still missing (those are flagged on their own rows).
        main_sid = max(
            (sid for sid in sorted(live_expected) if portal(sid).get("colours")),
            key=lambda sid: len(covered(sid)), default=None,
        )
        main_cover = covered(main_sid) if main_sid else frozenset()
        main_group = {main_sid, *(c["styleId"] for c in portal(main_sid).get("colours", []))} if main_sid else set()

        for sku, listed in members:
            if not listed:
                rows.append(make_row("", sku, REMARK_NOT_LISTED, "", status=""))
                continue
            for r in listed:
                sid = r.style_id
                p = portal(sid)
                if not p.get("live"):
                    remark = REMARK_DONE if sid in portal_union else REMARK_NOT_LIVE
                    rows.append(make_row(sid, sku, remark, "ADD"))
                    continue
                if len(live_skus) < 2:
                    rows.append(make_row(sid, sku, REMARK_SINGLE, ""))
                    continue
                siblings = [s for s in live_by_sku[sku] if s != sid]
                if sid not in grouped_ids and any(s in grouped_ids for s in siblings):
                    rows.append(make_row(sid, sku, REMARK_DUPLICATE, "CHECK"))
                    continue
                own_group = {sid, *(c["styleId"] for c in p.get("colours", []))}
                missing = [
                    s for s in live_skus
                    if s != sku and not any(x in own_group for x in live_by_sku[s])
                ]
                if not p.get("colours"):
                    remark = REMARK_NOT_GROUPED
                # Colour lists can be asymmetric: an inactive style may list the whole group
                # while the other members omit it. Membership in the main group's response
                # is sufficient; equal SKU coverage on every product page is not required.
                elif not missing or (len(main_cover) >= 2 and sid in main_group):
                    remark = REMARK_DONE
                else:
                    remark = REMARK_NOT_DONE
                missing_txt = ", ".join(f"{s} ({'/'.join(live_by_sku[s])})" for s in missing)
                rows.append(make_row(sid, sku, remark, "ADD", missing=missing_txt))

        for sid in sorted(portal_union - expected):
            rows.append(make_row(sid, sku_of_style(sid), REMARK_EXTRA, "REMOVE"))
    return rows


PENDING_REMARKS = {REMARK_NOT_DONE, REMARK_NOT_GROUPED}


def apply_cross_account_done(account_rows):
    """A group (sheet group + brand + article type) that is complete in one account
    is not shown as pending in the other accounts."""
    by_key = {}
    for account, rows in account_rows.items():
        for row in rows:
            by_key.setdefault((row["_key"], account), []).append(row["GROUPING REMARK"])
    complete = {}
    for (key, account), remarks in by_key.items():
        if REMARK_DONE in remarks and not PENDING_REMARKS & set(remarks):
            complete.setdefault(key, []).append(account)
    for account, rows in account_rows.items():
        for row in rows:
            done_in = [a for a in complete.get(row["_key"], []) if a != account]
            if done_in and row["GROUPING REMARK"] in PENDING_REMARKS:
                row["GROUPING REMARK"] = REMARK_DONE_OTHER
                row["ACTION"] = ""
                row["COMPLETE IN"] = ", ".join(f"ACC-{a}" for a in done_in)


TEMPLATE_SKIP_REMARKS = {REMARK_NOT_LISTED, REMARK_EXTRA, REMARK_NOT_LIVE}


def pending_group_styles(rows):
    """For every pending group, the style ids to upload: one style per SKU.

    Per SKU the style already in a portal group is preferred over a duplicate,
    then an Active listing, then the one with the most sales.
    Returns {unique id: {"brand", "article", "style_ids"}} in report order.
    """
    by_uid = {}
    for row in rows:
        by_uid.setdefault(row["Unique ID"], []).append(row)
    result = {}
    for uid, group_rows in by_uid.items():
        if not any(r["GROUPING REMARK"] in PENDING_REMARKS for r in group_rows):
            continue
        best = {}
        for r in group_rows:
            if r["GROUPING REMARK"] in TEMPLATE_SKIP_REMARKS or not r["Style ID"]:
                continue
            score = (
                r["GROUPING REMARK"] != REMARK_DUPLICATE,
                r["STATUS"] == "Active",
                r["SALE"] if isinstance(r["SALE"], int) else 0,
            )
            if r["SKU"] not in best or score > best[r["SKU"]][0]:
                best[r["SKU"]] = (score, r["Style ID"])
        style_ids = [sid for _, sid in best.values()]
        # Myntra refuses a whole upload holding more than one style that already has a colour group
        # (job report, 2 Nov 2026). So: the style of the biggest existing group, plus the ungrouped
        # ones. Styles of that same group are together already; a style in another group cannot be
        # moved by an upload and is named in REMARK.
        by_sid = {r["Style ID"]: r for r in group_rows}
        ids_of = lambda sid: {x for x in str(by_sid[sid]["PORTAL GROUP"]).split(", ") if x}  # noqa: E731
        grouped = [sid for sid in style_ids if len(ids_of(sid)) > 1]
        if len(grouped) > 1:
            anchor = max(grouped, key=lambda sid: len(ids_of(sid)))
            for sid in grouped:
                if sid != anchor and str(sid) not in ids_of(anchor):
                    by_sid[sid]["REMARK"] = "IN ANOTHER GROUP: UNGROUP FIRST"
            style_ids = [sid for sid in style_ids if sid == anchor or sid not in grouped]
        if len(style_ids) >= 2:
            first = group_rows[0]
            result[uid] = {"brand": first["Brand"], "article": first["Article Type"], "style_ids": style_ids}
    return result


def write_portal_templates(account_rows, stamp):
    """One copy of 'portal template.xlsx' per pending group:
    output/templates/<date>/ACC-<account>/<unique id>_<brand>_<article>.xlsx"""
    if not os.path.exists(PORTAL_TEMPLATE_FILE):
        print("WARNING: 'portal template.xlsx' not found, portal templates skipped")
        return
    for account, rows in account_rows.items():
        folder = os.path.join(TEMPLATE_DIR, stamp, f"ACC-{account}")
        os.makedirs(folder, exist_ok=True)
        # Drop files of an earlier run today, so only current pending groups remain.
        for old in glob.glob(os.path.join(folder, "*.xlsx")):
            os.remove(old)
        groups = pending_group_styles(rows)
        styles_total = 0
        for uid, group in groups.items():
            wb = load_workbook(PORTAL_TEMPLATE_FILE)
            ws = wb.worksheets[0]
            if ws.max_row > 1:
                ws.delete_rows(2, ws.max_row - 1)
            for r, sid in enumerate(group["style_ids"], start=2):
                ws.cell(r, 1, uid).number_format = "@"
                ws.cell(r, 2, GROUP_TYPE)
                ws.cell(r, 3, sid)
            name = re.sub(r'[\\/:*?"<>|]+', "-", f"{uid}_{group['brand']}_{group['article']}")
            wb.save(os.path.join(folder, f"{name}.xlsx"))
            styles_total += len(group["style_ids"])
        print(f"  ACC-{account}: {len(groups)} group files, {styles_total} styles -> {folder}")


FILLS = {
    REMARK_DONE: "C6EFCE",
    REMARK_NOT_DONE: "FFC7CE",
    REMARK_EXTRA: "FFEB9C",
    REMARK_NOT_LIVE: "D9D9D9",
    REMARK_NOT_LISTED: "EDEDED",
    REMARK_DONE_OTHER: "E2EFDA",
    REMARK_DUPLICATE: "BDD7EE",
    REMARK_SINGLE: "FFFFFF",
}


def write_report(path, account_rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary = []
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for account, rows in account_rows.items():
            df = pd.DataFrame(rows, columns=COLUMNS)
            df.to_excel(writer, sheet_name=f"ACC-{account}", index=False)
            counts = df["GROUPING REMARK"].value_counts()
            summary.append({
                "Account": account,
                "Groups": df["Unique ID"].nunique(),
                "Rows": len(df),
                **{k: int(counts.get(k, 0)) for k in FILLS},
            })
        pd.DataFrame(summary).to_excel(writer, sheet_name="Summary", index=False)
        # Format in memory: re-opening the saved file on a synced drive can read a half-written file.
        format_workbook(writer.book)


def format_workbook(wb):
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for ws in wb.worksheets:
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        headers = [c.value for c in ws[1]]
        remark_idx = headers.index("GROUPING REMARK") if "GROUPING REMARK" in headers else None
        uid_idx = headers.index("Unique ID") if "Unique ID" in headers else None
        prev_uid = None
        for row in ws.iter_rows(min_row=2):
            if remark_idx is not None:
                color = FILLS.get(row[remark_idx].value)
                if color:
                    row[remark_idx].fill = PatternFill("solid", fgColor=color)
            if uid_idx is not None:
                uid = row[uid_idx].value
                if prev_uid is not None and uid != prev_uid:
                    for cell in row:
                        cell.border = Border(top=Side(style="medium", color="1F4E78"))
                prev_uid = uid
        for i, col in enumerate(ws.columns, start=1):
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)


def main():
    parser = argparse.ArgumentParser(description="Myntra color-grouping checker")
    parser.add_argument("--refresh", action="store_true", help="re-fetch every style from the portal")
    parser.add_argument("--no-fetch", action="store_true", help="use cached portal data only")
    parser.add_argument("--concurrency", type=int, default=CONCURRENT_REQUESTS,
                        help=f"parallel portal requests (default {CONCURRENT_REQUESTS})")
    args = parser.parse_args()

    print("Loading grouping sheet ...")
    groups = load_grouping_sheet(GROUPING_FILE)
    print(f"  {len(groups)} groups")
    print("Loading master sheet ...")
    master = load_master(MASTER_FILE)
    print("Loading listing reports ...")
    styles, sku_to_style = load_listings(master)
    wanted = {b.strip().lower() for b in BRANDS}
    styles = styles[styles["brand"].str.strip().str.lower().isin(wanted)].reset_index(drop=True)
    print(f"  brands: {', '.join(sorted(styles['brand'].unique(), key=str.lower))}")
    accounts = sorted(styles["account"].unique())
    print(f"  accounts: {', '.join(accounts)}")
    print("Loading sales ...")
    sales = load_sales(sku_to_style)
    inventory = load_inventory(master)
    if inventory is None:
        print("  no inventory file in input/, INV column left blank")

    group_skus = {sku for _, skus in groups for sku in skus}
    to_check = sorted(styles.loc[styles["my_sku"].isin(group_skus), "style_id"].unique())
    cache = {} if args.refresh else load_cache()
    if not args.no_fetch:
        fetch_portal([sid for sid in to_check if sid not in cache], cache, args.concurrency)
    not_cached = [sid for sid in to_check if sid not in cache]
    if not_cached:
        print(f"WARNING: {len(not_cached)} styles have no portal data")

    account_rows = {
        account: build_account_rows(account, groups, styles, master, sales, inventory, cache)
        for account in accounts
    }
    apply_cross_account_done(account_rows)
    stamp = f"{datetime.now():%Y-%m-%d}"
    out = os.path.join(OUTPUT_DIR, f"GROUPING_ACCOUNT_WISE_{stamp}.xlsx")
    write_report(out, account_rows)
    print(f"Report saved: {out}")
    print("Building portal templates for pending groups ...")
    write_portal_templates(account_rows, stamp)


if __name__ == "__main__":
    main()
