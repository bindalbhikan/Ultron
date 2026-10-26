"""Myntra's buyer side (www.myntra.com) for a list of style ids: each style's product data from the
site's own product API, /gateway/v2/product/<style id>, the one the product page
(https://www.myntra.com/<style id>) reads.

A Scrapy spider: the home page first (the API answers 401 without the session cookie it sets),
then every style, a few at a time (AutoThrottle). A 401 later in the run (the cookie expired)
takes the home page again and asks for the style once more.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger("bindal.myntra_zero_td")

HOME = "https://www.myntra.com/"
API = "https://www.myntra.com/gateway/v2/product/{}"
HEADERS = {"x-meta-app": "channel=web", "x-myntraweb": "Yes", "Accept": "application/json"}
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")


def fetch(style_ids: list[int], concurrency: int = 8) -> dict[int, dict | str]:
    """{style id: the API's "style" object, or "NOT FOUND", or an error text}."""
    import scrapy
    from scrapy.crawler import CrawlerProcess

    results: dict[int, dict | str] = {}

    class Styles(scrapy.Spider):
        name = "myntra_styles"

        def _style(self, sid: int, again: int = 0):
            return scrapy.Request(API.format(sid), headers=HEADERS, callback=self.parse, errback=self.failed,
                                  meta={"sid": sid, "again": again}, dont_filter=True)

        async def start(self):
            yield scrapy.Request(HOME, callback=self.home, dont_filter=True, meta={"first": True})

        def home(self, response):
            if response.status != 200:
                log.warning("Myntra home page: %s", response.status)
            if response.meta.get("first"):
                yield from (self._style(sid) for sid in style_ids)
            else:
                yield self._style(response.meta["sid"], 1)

        def parse(self, response):
            sid = response.meta["sid"]
            if response.status == 401 and not response.meta["again"]:
                yield scrapy.Request(HOME, callback=self.home, dont_filter=True, meta={"sid": sid})
                return
            if response.status == 404:
                results[sid] = "NOT FOUND"
                return
            if response.status != 200:
                results[sid] = f"HTTP {response.status}"
                return
            try:
                results[sid] = json.loads(response.text)["style"]
            except (ValueError, KeyError, TypeError) as exc:
                results[sid] = f"bad answer: {str(exc)[:80]}"

        def failed(self, failure):
            sid = failure.request.meta.get("sid")
            if sid is not None:
                results[sid] = f"{type(failure.value).__name__}: {str(failure.value)[:80]}"

    process = CrawlerProcess({
        "USER_AGENT": USER_AGENT,
        "LOG_LEVEL": "WARNING",
        "HTTPERROR_ALLOW_ALL": True,
        "CONCURRENT_REQUESTS": concurrency,
        "CONCURRENT_REQUESTS_PER_DOMAIN": concurrency,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.1,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": concurrency,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [408, 429, 500, 502, 503, 504, 522, 524],
        "DOWNLOAD_TIMEOUT": 30,
        "TELNETCONSOLE_ENABLED": False,
    }, install_root_handler=False)
    logging.getLogger("scrapy").setLevel(logging.WARNING)   # its INFO stats would fill the run log
    process.crawl(Styles)
    process.start()
    for sid in style_ids:
        results.setdefault(sid, "no answer")
    return results


def sizes_in_stock(style: dict) -> list[dict]:
    """Each size that can be bought now: label, stock (every seller's availableCount), MRP and the
    lowest selling price among the sellers that have it."""
    out = []
    for size in style.get("sizes") or []:
        sellers = [s for s in size.get("sizeSellerData") or [] if int(s.get("availableCount") or 0) > 0]
        if not size.get("available") or not sellers:
            continue
        mrp = max(float(s.get("mrp") or style.get("mrp") or 0) for s in sellers)
        price = min(float(s.get("discountedPrice") or s.get("mrp") or mrp) for s in sellers)
        out.append({"size": size.get("label") or "", "stock": sum(int(s["availableCount"]) for s in sellers),
                    "mrp": mrp, "price": price})
    return out
