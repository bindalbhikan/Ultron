"""The owner's hand-run Myntra colour-grouping checker (LISTING/MYNTRA/Grouping2/main.py), unchanged:
its loaders, portal spider, rules and report, except changes of the owner: NOT GROUPED is reported as
NOT DONE (2 Nov 2026), and no DONE IN OTHER ACCOUNT: a group listed in two accounts is checked and
submitted in each account on its own (6 Nov 2026). pipeline.py points its folders at the run's work folder and gives it the bot's
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

from typing import NamedTuple

import polars as pl

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
REMARK_NO_ANSWER = "NO ANSWER FROM MYNTRA"   # not checked: never counted as not live
REMARK_NOT_LISTED = "NOT LISTED"
# Owner's rule (2 Nov 2026): a style in no colour group is as pending as one in an incomplete group -
# one remark, NOT DONE, for both (its own fill and Summary column dropped).
REMARK_NOT_GROUPED = REMARK_NOT_DONE
REMARK_DUPLICATE = "DUPLICATE - NOT IN GROUP"
REMARK_SINGLE = "ONLY 1 LISTED"

COLUMNS = [
    "Unique ID", "Group Type", "Category", "Article Type", "Style ID", "SKU", "FINAL SKU", "Brand",
    "GROUPING REMARK", "STATUS", "REMARK", "INV", "SALE", "REMARK2", "ACTION",
    "PORTAL COLOR", "MISSING IN PORTAL", "PORTAL GROUP",
]


def norm(value):
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip().upper()


def pnorm(e: pl.Expr) -> pl.Expr:
    """norm() of a column: text, outer spaces out, upper case, empty for a missing value."""
    return e.cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase()


class Style(NamedTuple):
    """One listed style of an account (load_listings)."""
    account: str
    style_id: str
    brand: str
    article: str
    my_sku: str
    status: str


def style_rows(df: pl.DataFrame) -> list[Style]:
    return [Style(**r) for r in df.select(Style._fields).iter_rows(named=True)]


def first_of(df: pl.DataFrame, key: str, value: str) -> dict:
    """key -> value of the first row of each key."""
    return dict(df.unique(key, keep="first", maintain_order=True).select(key, value).iter_rows())


# ---------------------------------------------------------------- loaders

def load_grouping_sheet(path):
    """Return a list of (category, [sku, ...]) groups in sheet order."""
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(str(path))
    groups = []
    for name in wb.sheet_names:
        category = name.strip()
        current = []
        for row in wb.get_sheet_by_name(name).to_python(skip_empty_area=False):
            sku = norm(row[0] if row else None)
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
    return groups


def load_master(path):
    from ..core.tables import read_excel_text
    cols = ["Channel Name", "MY SKU", "SIZE SKU", "FINAL MY SKU", "MYNTRA STYLE ID", "MYNTRA SKU CODE"]
    m = read_excel_text(path, "Master")
    df = m.select(*[pnorm(pl.col(c) if c in m.columns else pl.lit(None)).alias(c) for c in cols])
    final_map = first_of(df.filter(pl.col("MY SKU") != ""), "MY SKU", "FINAL MY SKU")
    size_final_map = first_of(df.filter(pl.col("SIZE SKU") != ""), "SIZE SKU", "FINAL MY SKU")
    myntra = df.filter(pl.col("Channel Name").str.starts_with("MYNTRA") & (pl.col("MYNTRA SKU CODE") != ""))
    code_map = first_of(myntra, "MYNTRA SKU CODE", "MY SKU")
    style_map = first_of(myntra.filter(pl.col("MYNTRA STYLE ID") != ""), "MYNTRA STYLE ID", "MY SKU")
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


def _csv(path) -> pl.DataFrame:
    """A report CSV as text, read the way pandas' read_csv(dtype=str) did (its missing-value words are empty)."""
    from ..core.tables import read_text_csv
    return read_text_csv(path, na_words=True)


def load_listings(master):
    """Return one row per (account, style id) with brand, MY SKU and status (Polars, keys A to Z), and SKU code -> style id."""
    frames = []
    for path in glob.glob(os.path.join(INPUT_DIR, "*Seller_Listings_Report*.csv")):
        match = re.search(r"_(\d+)\.csv$", path)
        if not match:
            continue
        frames.append(_csv(path).fill_null("").with_columns(account=pl.lit(match.group(1))))
    if not frames:
        sys.exit("No Seller_Listings_Report CSV found in input/")
    df = pl.concat(frames, how="diagonal_relaxed").fill_null("")
    df = df.with_columns(pnorm(pl.col("sku code")).replace_strict(master["code"], default="").alias("my_sku"))
    for source in ("van", "seller sku code"):              # a MY SKU from the VAN, then from the seller SKU
        want = df.filter(pl.col("my_sku") == "")[source].unique().to_list()
        guess = {v: guess_my_sku(v, master["my_skus"]) for v in want}
        df = df.with_columns(pl.when(pl.col("my_sku") == "").then(pl.col(source).replace_strict(guess, default=""))
                               .otherwise(pl.col("my_sku")).alias("my_sku"))
    styles = (
        df.group_by("account", "style id", maintain_order=True)
        .agg(pl.col("brand").first(), pl.col("article type").first().alias("article"),
             pl.col("my_sku").filter(pl.col("my_sku") != "").first().fill_null("").alias("my_sku"),
             pl.when((pl.col("listing status description") == "Active").any()).then(pl.lit("Active"))
               .otherwise(pl.col("listing status description").first()).alias("status"))
        .rename({"style id": "style_id"})
        .sort("account", "style_id")
    )
    sku_to_style = first_of(df, "sku code", "style id")
    return styles, sku_to_style


def load_sales(sku_to_style):
    files = glob.glob(os.path.join(SALE_DIR, "*.csv"))
    if not files:
        print("WARNING: no sale files found in sale/")
        return {}
    cols = ["sale_order_code", "product_sku_code", "order_item_status", "party_id_to"]
    df = pl.concat([_csv(f).select(cols) for f in files], how="vertical_relaxed")
    df = (df.unique("sale_order_code", keep="first", maintain_order=True)
            .filter(pl.col("order_item_status").str.to_lowercase().is_in(sorted(SALE_STATUSES)).fill_null(False))
            .with_columns(pl.col("product_sku_code").replace_strict(sku_to_style, default=None, return_dtype=pl.Utf8).alias("style_id"))
            .filter(pl.col("style_id").is_not_null() & pl.col("party_id_to").is_not_null()))
    counts = df.group_by("party_id_to", "style_id").len()
    return {(str(a), str(s)): int(n) for a, s, n in counts.iter_rows()}


def load_inventory(master):
    """Optional inventory file -> {FINAL SKU: qty}."""
    from ..core.tables import pnum, read_excel_text
    files = [
        f for f in glob.glob(os.path.join(INPUT_DIR, "*"))
        if "inventory" in os.path.basename(f).lower() and f.lower().endswith((".xlsx", ".xls", ".csv"))
    ]
    if not files:
        return None
    inv = {}
    for path in files:
        df = _csv(path) if path.lower().endswith(".csv") else read_excel_text(path, 0)
        sku_col = next((c for c in df.columns if "sku" in str(c).lower()), None)
        qty_col = next(
            (c for c in df.columns if re.search(r"qty|quantity|inventory|stock|inv", str(c), re.I) and c != sku_col),
            None,
        )
        if not sku_col or not qty_col:
            print(f"WARNING: could not find SKU/qty columns in {os.path.basename(path)}, skipped")
            continue
        for sku, qty in df.select(pnorm(pl.col(sku_col)), pnum(pl.col(qty_col)).fill_null(0)).iter_rows():
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

def portal_components(cache):
    """Colour groups connected by explicit product links, including one-way/shared-partner links."""
    parent = {}

    def root(sid):
        parent.setdefault(sid, sid)
        while parent[sid] != sid:
            parent[sid] = parent[parent[sid]]
            sid = parent[sid]
        return sid

    for sid, record in cache.items():
        if not record.get("live"):
            continue
        root(sid)
        for colour in record.get("colours", []):
            other = str(colour.get("styleId") or "")
            if other.isdigit():
                parent[root(other)] = root(sid)
    members = {}
    for sid in parent:
        members.setdefault(root(sid), set()).add(sid)
    frozen = {key: frozenset(value) for key, value in members.items()}
    return {sid: frozen[root(sid)] for sid in parent}


def build_account_rows(account, groups, styles, master, sales, inventory, cache):
    connected = portal_components(cache)
    acc = style_rows(styles.filter(pl.col("account") == account))
    by_brand_sku = {}
    for r in acc:
        by_brand_sku.setdefault((r.brand, r.my_sku), []).append(r)
    style_info = {r.style_id: r for r in acc}
    brands = sorted({r.brand for r in acc}, key=str.lower)
    # Article type of a SKU across all accounts, used when the SKU is not listed in this brand: the most common one
    # (of equally common ones the first seen).
    any_article = dict(
        styles.with_row_index("_i").filter(pl.col("article") != "")
        .group_by("my_sku", "article").agg(pl.len().alias("_n"), pl.col("_i").min())
        .sort(["my_sku", "_n", "_i"], descending=[False, True, False]).unique("my_sku", keep="first")
        .select("my_sku", "article").iter_rows()
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
                "_portal_group": connected.get(sid, frozenset()),
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
        grouped_ids = {sid for sid in live_expected if len(connected.get(sid, ())) > 1}

        def covered(sid):
            group = connected.get(sid, {sid})
            return frozenset(s for s in live_skus if any(x in group for x in live_by_sku[s]))

        # Main portal group = the live group covering most SKUs of this block. Its styles are DONE
        # even if some SKUs are still missing (those are flagged on their own rows).
        main_sid = max(
            (sid for sid in sorted(live_expected) if len(connected.get(sid, ())) > 1),
            key=lambda sid: len(covered(sid)), default=None,
        )
        main_cover = covered(main_sid) if main_sid else frozenset()
        main_group = connected.get(main_sid, frozenset())

        for sku, listed in members:
            if not listed:
                rows.append(make_row("", sku, REMARK_NOT_LISTED, "", status=""))
                continue
            for r in listed:
                sid = r.style_id
                p = portal(sid)
                if not p.get("live"):
                    if sid in portal_union:
                        rows.append(make_row(sid, sku, REMARK_DONE, "ADD"))
                    elif sid in cache:
                        rows.append(make_row(sid, sku, REMARK_NOT_LIVE, "ADD"))
                    else:
                        rows.append(make_row(sid, sku, REMARK_NO_ANSWER, "CHECK"))
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
                # Colour lists can be asymmetric: an inactive style may list the whole group
                # while the other members omit it. Membership in the main group's response
                # is sufficient even when this member's own colour list is empty.
                if (len(main_cover) >= 2 and sid in main_group) or len(covered(sid)) == len(live_skus):
                    remark = REMARK_DONE
                elif not p.get("colours"):
                    remark = REMARK_NOT_GROUPED
                else:
                    remark = REMARK_NOT_DONE
                missing_txt = ", ".join(f"{s} ({'/'.join(live_by_sku[s])})" for s in missing)
                rows.append(make_row(sid, sku, remark, "ADD", missing=missing_txt))

        for sid in sorted(portal_union - expected):
            rows.append(make_row(sid, sku_of_style(sid), REMARK_EXTRA, "REMOVE"))
    return rows


PENDING_REMARKS = {REMARK_NOT_DONE, REMARK_NOT_GROUPED}


TEMPLATE_SKIP_REMARKS = {REMARK_NOT_LISTED, REMARK_EXTRA, REMARK_NOT_LIVE, REMARK_NO_ANSWER}


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
        ids_of = lambda sid: by_sid[sid].get("_portal_group") or {x for x in str(by_sid[sid]["PORTAL GROUP"]).split(", ") if x}  # noqa: E731
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
    """One upload file per pending group, in the layout of 'portal template.xlsx' (its sheet name and header row; the
    Unique ID as text): output/templates/<date>/ACC-<account>/<unique id>_<brand>_<article>.xlsx (xlsxwriter)."""
    import xlsxwriter
    from python_calamine import CalamineWorkbook
    if not os.path.exists(PORTAL_TEMPLATE_FILE):
        print("WARNING: 'portal template.xlsx' not found, portal templates skipped")
        return
    template = CalamineWorkbook.from_path(PORTAL_TEMPLATE_FILE)
    sheet = template.sheet_names[0]
    header = (template.get_sheet_by_name(sheet).to_python(nrows=1) or [[]])[0]
    for account, rows in account_rows.items():
        folder = os.path.join(TEMPLATE_DIR, stamp, f"ACC-{account}")
        os.makedirs(folder, exist_ok=True)
        # Drop files of an earlier run today, so only current pending groups remain.
        for old in glob.glob(os.path.join(folder, "*.xlsx")):
            os.remove(old)
        groups = pending_group_styles(rows)
        styles_total = 0
        for uid, group in groups.items():
            name = re.sub(r'[\\/:*?"<>|]+', "-", f"{uid}_{group['brand']}_{group['article']}")
            wb = xlsxwriter.Workbook(os.path.join(folder, f"{name}.xlsx"), {"strings_to_numbers": False})
            ws = wb.add_worksheet(sheet)
            text = wb.add_format({"num_format": "@"})
            for j, h in enumerate(header):
                if h not in ("", None):
                    ws.write(0, j, h)
            for r, sid in enumerate(group["style_ids"], start=1):
                ws.write_string(r, 0, str(uid), text)
                ws.write_string(r, 1, GROUP_TYPE)
                ws.write(r, 2, sid)
            wb.close()
            styles_total += len(group["style_ids"])
        print(f"  ACC-{account}: {len(groups)} group files, {styles_total} styles -> {folder}")


FILLS = {
    REMARK_DONE: "C6EFCE",
    REMARK_NOT_DONE: "FFC7CE",
    REMARK_EXTRA: "FFEB9C",
    REMARK_NOT_LIVE: "D9D9D9",
    REMARK_NO_ANSWER: "F8CBAD",
    REMARK_NOT_LISTED: "EDEDED",
    REMARK_DUPLICATE: "BDD7EE",
    REMARK_SINGLE: "FFFFFF",
}


def write_tables(path, sheets: list[tuple[str, list, list]]) -> None:
    """A new workbook of [(sheet, headers, rows)] in the grouping look (xlsxwriter): a dark blue header, the header frozen,
    a filter, GROUPING REMARK coloured, a line above each new Unique ID, widths from the values (10 to 60)."""
    import xlsxwriter
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "strings_to_formulas": False, "strings_to_urls": False,
                                         "nan_inf_to_errors": True})
    looks: dict = {}

    def look(fill=None, top=False, head=False):
        key = (fill, top, head)
        if key not in looks:
            f = {}
            if head:
                f.update(bold=True, font_color="#FFFFFF", bg_color="#1F4E78", pattern=1, align="center", valign="vcenter")
            if fill:
                f.update(bg_color="#" + fill, pattern=1)
            if top:
                f.update(top=2, top_color="#1F4E78")
            looks[key] = wb.add_format(f) if f else None
        return looks[key]

    for name, headers, rows in sheets:
        ws = wb.add_worksheet(name)
        widths = [len(str(h)) for h in headers]
        for j, h in enumerate(headers):
            ws.write_string(0, j, str(h), look(head=True))
        remark = headers.index("GROUPING REMARK") if "GROUPING REMARK" in headers else None
        uid = headers.index("Unique ID") if "Unique ID" in headers else None
        prev = None
        n = 0
        for i, row in enumerate(rows, start=1):
            n = i
            top = uid is not None and prev is not None and row[uid] != prev
            if uid is not None:
                prev = row[uid]
            for j in range(len(headers)):
                v = row[j] if j < len(row) else None
                f = look(FILLS.get(v) if j == remark else None, top)
                if v is not None:
                    widths[j] = max(widths[j], len(str(v)))
                if v is None or v == "" or (isinstance(v, float) and v != v):     # an empty text is an empty cell
                    if f is not None:
                        ws.write_blank(i, j, None, f)
                elif isinstance(v, bool):
                    ws.write_boolean(i, j, v, f)
                elif isinstance(v, (int, float)):
                    ws.write_number(i, j, v, f)
                elif isinstance(v, datetime):
                    ws.write_datetime(i, j, v, f)
                else:
                    ws.write_string(i, j, str(v), f)
        ws.freeze_panes(1, 0)
        if headers:
            ws.autofilter(0, 0, n, len(headers) - 1)
        for j, w in enumerate(widths):
            ws.set_column(j, j, min(max(w + 2, 10), 60))
    wb.close()


def write_report(path, account_rows):
    """ACC-<account> per account (COLUMNS) and Summary."""
    summary = []
    for account, rows in account_rows.items():
        df = pl.DataFrame({"uid": [r.get("Unique ID") for r in rows], "remark": [r.get("GROUPING REMARK") for r in rows]},
                          schema={"uid": pl.Utf8, "remark": pl.Utf8}, strict=False)
        counts = dict(df.group_by("remark").len().iter_rows())
        summary.append({"Account": account, "Groups": df["uid"].drop_nulls().n_unique(), "Rows": df.height,
                        **{k: int(counts.get(k, 0)) for k in FILLS}})
    heads = ["Account", "Groups", "Rows", *FILLS]
    write_tables(path, [(f"ACC-{account}", COLUMNS, [[r.get(c) for c in COLUMNS] for r in rows]) for account, rows in account_rows.items()]
                 + [("Summary", heads, [[s[h] for h in heads] for s in summary])])


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
    styles = styles.filter(pl.col("brand").str.strip_chars().str.to_lowercase().is_in(sorted(wanted)))
    print(f"  brands: {', '.join(sorted(styles['brand'].unique().to_list(), key=str.lower))}")
    accounts = sorted(styles["account"].unique().to_list())
    print(f"  accounts: {', '.join(accounts)}")
    print("Loading sales ...")
    sales = load_sales(sku_to_style)
    inventory = load_inventory(master)
    if inventory is None:
        print("  no inventory file in input/, INV column left blank")

    group_skus = {sku for _, skus in groups for sku in skus}
    to_check = sorted(styles.filter(pl.col("my_sku").is_in(sorted(group_skus)))["style_id"].unique().to_list())
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
    stamp = f"{datetime.now():%Y-%m-%d}"
    out = os.path.join(OUTPUT_DIR, f"GROUPING_ACCOUNT_WISE_{stamp}.xlsx")
    write_report(out, account_rows)
    print(f"Report saved: {out}")
    print("Building portal templates for pending groups ...")
    write_portal_templates(account_rows, stamp)


if __name__ == "__main__":
    main()
