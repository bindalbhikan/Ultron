"""Flipkart Seller Hub: FBF (Flipkart warehouse) units per day.

Login is a plain JSON POST; the CSRF token for the dashboard APIs comes from
/getFeaturesForSeller. Units come from the Seller Insights metrics API filtered on
Flipkart's own warehouses (location_id), so only FBF orders are counted.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import date, datetime

import requests

log = logging.getLogger(__name__)

BASE = "https://seller.flipkart.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
DEFAULT_FBF_LOCATIONS = ["bhi_vas_wh_nl_01nl", "frk_bts", "gur_san_wh_nl_01nl", "malur_bts", "ulub_bts"]


class FlipkartError(RuntimeError):
    pass


class FlipkartQuota(FlipkartError):
    """The report centre takes 20 new requests a day; asking again today cannot work."""


class FlipkartClient:
    def __init__(self, username: str, password: str, timeout: int = 60):
        self.username, self.password, self.timeout = username, password, timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        self.csrf = ""
        self.seller_id = ""

    def login(self, tries: int = 3) -> None:
        """Log in; a dropped connection (Flipkart resets some, 18 Oct backfill) is tried again.
        A refused login is not retried."""
        for attempt in range(1, tries + 1):
            try:
                return self._login()
            except requests.ConnectionError as exc:
                if attempt == tries:
                    raise
                log.warning("Flipkart login: connection dropped (%s), trying again", exc)
                time.sleep(20 * attempt)

    def _login(self) -> None:
        xhr = {"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest"}
        self.s.get(f"{BASE}/", timeout=self.timeout)
        r = self.s.post(f"{BASE}/login", headers={**xhr, "Content-Type": "application/json",
                                                   "Origin": BASE, "Referer": f"{BASE}/"},
                        json={"authName": "flipkart", "username": self.username,
                              "password": self.password, "userNameType": "email"},
                        timeout=self.timeout)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or body.get("code") != 1000:
            raise FlipkartError(f"Flipkart login failed: HTTP {r.status_code} {str(body)[:200] or r.text[:200]}")
        f = self.s.get(f"{BASE}/getFeaturesForSeller", headers=xhr, timeout=self.timeout).json()
        self.csrf, self.seller_id = f.get("csrfToken", ""), f.get("sellerId", "")
        if not self.csrf:
            raise FlipkartError("Flipkart CSRF token not found after login")
        log.info("Logged in to Flipkart Seller Hub (seller %s)", self.seller_id)

    def _metrics(self, body: dict, view: str) -> dict:
        r = self.s.post(f"{BASE}/napi/metrics/search", json=body, timeout=self.timeout,
                        headers={"fk-csrf-token": self.csrf, "x-view-name": view,
                                 "Content-Type": "application/json", "Origin": BASE,
                                 "Referer": f"{BASE}/index.html"})
        if r.status_code != 200:
            raise FlipkartError(f"Flipkart metrics API failed: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def earn_more(self, first: date, last: date) -> dict[str, float]:
        """Seller Hub > NXT Insights > Earn More for first..last, every warehouse: gross, cancellation and return units and
        amounts by order date. Interval MONTHLY is what the screen uses and reaches back further (Nov-25) than DAILY
        (May-26), and only it gives the screen's exact figures. Cancellation holds RTO too. All 0 = no data for the range."""
        metrics = ["gross_units", "gross_amount", "cancellation_units", "cancellation_amount", "return_units", "return_amount"]
        total = dict.fromkeys(metrics, 0.0)
        page, pages = 0, 1
        while page < pages:
            data = self._metrics({
                "filters": [{"field_name": "date", "filter_type": "RANGE_MATCH", "range_from": f"{first:%Y-%m-%d}",
                             "range_to": f"{last:%Y-%m-%d}"}],
                "sort": [], "metrics": [{"metric_name": m, "metric_field": m, "metric_type": "longSum"} for m in metrics],
                "derived_metrics": [], "aggregate_by": "all", "interval": "MONTHLY", "pivot": ["address_state_code"],
                "page_number": page, "page_size": 500}, "sell_more_aggregated_groupby_view")
            for row in data.get("data") or []:
                for m in metrics:
                    total[m] += float(row.get(m) or 0)
            pages = int(data.get("total_pages") or 1)
            page += 1
        return total

    def fbf_units(self, days: list[date], locations: list[str] | None = None) -> tuple[Counter, Counter]:
        """(gross units per day, cancelled units per day) for the FBF warehouses.
        The API sums the whole requested range into one row, so each day is queried on its own."""
        locations = locations or DEFAULT_FBF_LOCATIONS
        gross, cancel = Counter(), Counter()
        for day in days:
            page, pages = 0, 1
            while page < pages:
                body = {
                    "filters": [
                        {"field_name": "date", "filter_type": "RANGE_MATCH",
                         "range_from": f"{day:%Y-%m-%d}", "range_to": f"{day:%Y-%m-%d}"},
                        {"field_name": "location_id", "filter_type": "FULL_TEXT_MATCH",
                         "text_match_filter_values": locations},
                    ],
                    "sort": [],
                    "metrics": [
                        {"metric_name": "gross_units", "metric_field": "gross_units", "metric_type": "longSum"},
                        {"metric_name": "cancellation_units", "metric_field": "cancellation_units",
                         "metric_type": "longSum"},
                    ],
                    "derived_metrics": [], "aggregate_by": "all", "interval": "DAILY",
                    "pivot": ["address_state_code"], "page_number": page, "page_size": 500,
                }
                data = self._metrics(body, "sell_more_aggregated_groupby_view")
                for row in data.get("data") or []:
                    gross[day] += int(row.get("gross_units") or 0)
                    cancel[day] += int(row.get("cancellation_units") or 0)
                pages = int(data.get("total_pages") or 1)
                page += 1
        log.info("Flipkart FBF: gross %s, cancel %s",
                 {f"{d}": gross[d] for d in days}, {f"{d}": cancel[d] for d in days})
        return gross, cancel

    # ------------------------------------------------------------ report centre
    def _report_api(self, method: str, path: str, **kw) -> requests.Response:
        r = self.s.request(method, f"{BASE}/napi/metrics/bizReport/{path}", timeout=self.timeout,
                           headers={"fk-csrf-token": self.csrf, "Content-Type": "application/json",
                                    "Origin": BASE, "Referer": f"{BASE}/index.html"}, **kw)
        if "daily quota" in r.text:     # the answer is HTTP 500 around a 429
            raise FlipkartQuota("Flipkart's daily quota of 20 reports is used up: run it again tomorrow")
        if r.status_code != 200:
            raise FlipkartError(f"Flipkart report centre {path.split('?')[0]}: HTTP {r.status_code} {r.text[:200]}")
        return r

    # the report centre's groups (reportCategories); "Analytics Report" holds the DBD breach reports
    REPORT_GROUPS = ("Fulfilment Reports", "Tax Reports", "Payment Reports", "Invoices", "Analytics Report")

    def report_requests(self, pages: int = 3, name: str | None = None) -> list[dict]:
        """The report centre's one-time report requests, newest first. Since 1 Nov 2026 the list of
        every group together answers HTTP 500, so it is read group by group; a group whose list
        fails is left out (logged)."""
        out = []
        for group in self.REPORT_GROUPS:
            for page in range(1, pages + 1):
                try:
                    data = self._report_api("POST", "report/getReportsV2", json={
                        "reportGroup": group, "reportName": name, "enable": True, "status": None,
                        "page_size": 50, "starting_page": page}).json()
                except FlipkartError as exc:
                    log.warning("Flipkart report list of %s not read: %s", group, str(exc)[:120])
                    break
                out += data.get("report_requests") or []
                if not data.get("has_more"):
                    break
        once = {q.get("request_id"): q for q in out}               # a request can come in more than one group
        return sorted(once.values(), key=lambda q: q.get("created_at") or 0, reverse=True)

    @staticmethod
    def _dates(req: dict) -> list[str]:
        return next((f.get("value") for f in req.get("filters") or [] if f.get("name") == "date"), [])

    def request_report(self, name: str, start: date, end: date, fresh: bool = False,
                       made_from: date | None = None) -> str:
        """Request id of a report centre report (e.g. "Sales Report", "Returns") for exactly
        start..end: a finished or running request for the same dates is reused (unless fresh; with
        made_from only one asked for on or after that day), else one is submitted."""
        want = [f"{start}", f"{end}"]
        since = datetime.combine(made_from, datetime.min.time()).timestamp() * 1000 if made_from else 0
        req = None if fresh else next((q for q in self.report_requests(name=name) if q.get("report_name") == name
                                       and self._dates(q) == want and q.get("status") not in ("FAILED", "ERROR")
                                       and (q.get("created_at") or 0) >= since),
                                      None)
        if req:
            log.info("Flipkart %s %s..%s already requested (%s)", name, start, end, req.get("status"))
            return req["request_id"]
        body = {"from_date": want[0], "to_date": want[1], "file_format": "EXCEL", "type": "ONETIME",
                "filters": [{"values": want, "operator": "RANGE", "name": "date"}]}
        rid = self._report_api("POST", f"submitReport?reportName={requests.utils.quote(name)}",
                               json=body).json()["request_id"]["request_id"]
        log.info("Flipkart %s %s..%s requested (%s)", name, start, end, rid)
        return rid

    def report(self, name: str, start: date, end: date, wait_minutes: int = 45,
               poll_seconds: int = 30, made_from: date | None = None) -> tuple[str, bytes]:
        """(file name, xlsx bytes) of a report centre report for exactly start..end, waited for
        until it is stored (Flipkart says up to 30 minutes). When an existing (old) request will
        not download, a new one is submitted and waited for."""
        try:
            return self._report(name, start, end, self.request_report(name, start, end, made_from=made_from),
                                wait_minutes, poll_seconds)
        except FlipkartQuota:
            raise
        except (FlipkartError, requests.RequestException) as exc:
            log.warning("Flipkart %s %s..%s not downloaded (%s): asking for it again", name, start, end, exc)
            rid = self.request_report(name, start, end, fresh=True)
            return self._report(name, start, end, rid, wait_minutes, poll_seconds)

    def _report(self, name, start, end, rid, wait_minutes, poll_seconds) -> tuple[str, bytes]:
        req = None
        deadline = time.time() + wait_minutes * 60
        while True:
            # an old request can sit beyond the first page of the list
            req = next((q for q in self.report_requests(1, name=name) if q.get("request_id") == rid), None) or \
                next((q for q in self.report_requests(name=name) if q.get("request_id") == rid), req)
            status = (req or {}).get("status")
            if status == "FILE_STORED":
                break
            if status in ("FAILED", "ERROR"):
                raise FlipkartError(f"Flipkart {name} report {rid} {status}")
            if time.time() > deadline:
                raise FlipkartError(f"Flipkart {name} report not ready after {wait_minutes} min ({status})")
            log.info("Flipkart %s report: %s, waiting", name, status or "?")
            time.sleep(poll_seconds)
        file_name = f"{rid}_{req['created_at']}.xlsx"
        r = self._report_api("GET", f"downloadReport/{file_name}?token={rid}&sellerId={self.seller_id}")
        log.info("Flipkart %s report downloaded (%d bytes)", name, len(r.content))
        return f"Flipkart {name} {start} to {end}.xlsx", r.content

    # ------------------------------------------------------------ listings and prices
    # Seller Hub > Listings: the table, the settlement calculator and the price update (captured
    # 7 Nov 2026, tested 14 Nov). esp = bank settlement ("TP"), ssp = selling price.
    _CALC_QUERY = (
        "query settlements_calculator_web_getAverageSettlementPrice($darwin_tier: String, $listings: "
        "[OptionalInputParams], $reward_params: IRewardParams, $page_name: String, $include_returns: Boolean, "
        "$new_reverse_api: Boolean) {\n  getAverageSettlementPrice: getAverageSettlementPrice(\n"
        "    darwin_tier: $darwin_tier\n    listings: $listings\n    reward_params: $reward_params\n"
        "    page_name: $page_name\n    include_returns: $include_returns\n    new_reverse_api: $new_reverse_api\n  )\n}")
    _FEE_PARAMS = ("fixedRate prepaid postpaid localFee zonalFee nationalFee localAdditionalCharges "
                   "zonalAdditionalCharges nationalAdditionalCharges startSlab incrementalSlab")
    # rate card parts (orchestrator query) by their field in the answer
    FEES = {"platformFee": "GetPlatformFeeOrchestrator", "closingFee": "GetClosingFeeOrchestrator",
            "collectionFee": "GetCollectionFeeOrchestrator", "reverseShippingFee": "GetReverseShippingFeeOrchestrator"}

    def _json_headers(self) -> dict:
        return {"fk-csrf-token": self.csrf, "Content-Type": "application/json", "Origin": BASE,
                "Referer": f"{BASE}/index.html"}

    def _post(self, path: str, body: dict, tries: int = 3) -> dict:
        """POST JSON; an HTTP 5xx or a dropped connection is tried again (only when tries > 1),
        any other refusal is raised."""
        r = None
        for attempt in range(1, tries + 1):
            try:
                r = self.s.post(f"{BASE}{path}", json=body, headers=self._json_headers(), timeout=self.timeout)
            except requests.ConnectionError:
                if attempt == tries:
                    raise
                time.sleep(5 * attempt)
                continue
            if r.status_code < 500 or attempt == tries:
                break
            time.sleep(5 * attempt)
        if r.status_code != 200:
            raise FlipkartError(f"Flipkart {path.split('?')[0]}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def tier(self) -> str:
        """The seller's tier (bronze, silver ...): the calculator and the rate card depend on it."""
        r = self.s.get(f"{BASE}/napi/darwin/finalTier", headers=self._json_headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise FlipkartError(f"Flipkart tier: HTTP {r.status_code}")
        return r.json().get("tier") or "bronze"

    def listings(self, state: str = "ACTIVE", page_size: int = 100) -> list[dict]:
        """Every listing in a state: sku_id, listing_id, product_id (FSN), vertical, mrp, ssp, esp ...
        No sort: a sorted list (demand_weight) repeats and skips rows across pages (14 Nov: 6,388
        rows, 5,389 listings), and 500 a page is refused. Raises unless every listing was read."""
        rows, count = {}, None
        for _ in range(4):           # unsorted paging still drops a few rows now and then (14 Nov: 6,384 of
            page = 0                 # 6,388): read again and merge until every listing is in
            while True:
                data = self._post("/napi/listing/listingsDataForStates", {
                    "search_text": "", "search_filters": {"internal_state": state},
                    "column": {"pagination": {"batch_no": page, "batch_size": page_size}}})
                got = data.get("listing_data_response") or []
                count = data.get("count", count)
                for x in got:
                    rows[x["listing_id"]] = x
                page += 1
                if not got or page * page_size >= (count or 0):
                    break
            if count is not None and len(rows) >= count:
                break
            log.info("Flipkart listings: %d of %s read, reading again", len(rows), count)
        if count is None or len(rows) != count:
            raise FlipkartError(f"Flipkart listings: read {len(rows)} of {count}")
        log.info("Flipkart %s listings: %d", state, len(rows))
        return list(rows.values())

    def calculator(self, items: list[dict], tier: str, chunk: int = 50) -> dict[str, dict]:
        """Flipkart's own settlement calculator, by listing id. Each item is
        {"listing_id", "selling_price"} (forward: SP -> settlement) or {"listing_id", "type": "reverse",
        "settlement_value"} (reverse: settlement -> SP). The answer per listing has selling_price,
        settlement_value, settlement_status (reverse), total_fees_and_taxes, zone_level_splits ..."""
        out = {}
        for i in range(0, len(items), chunk):
            data = self._post("/napi/graphql", {
                "operationName": "settlements_calculator_web_getAverageSettlementPrice", "query": self._CALC_QUERY,
                "variables": {"listings": items[i:i + chunk], "darwin_tier": tier, "reward_params": {},
                              "page_name": "", "include_returns": False, "new_reverse_api": True}})
            out.update(((data.get("data") or {}).get("getAverageSettlementPrice")) or {})
        return out

    def rate_card(self, fsn: str, tier: str, service_profile: str = "NON_FBF") -> dict:
        """The rate card of one FSN: commission, fixed (closing) fee, collection fee and reverse
        shipping, each with its price (asp) or weight (shippingSlab) slabs, as Seller Hub shows it."""
        slab = f"asp {{ start end agreementParameters {{ {self._FEE_PARAMS} }} }}"
        ship = (f"shippingSlab {{ start end {slab} agreementParameters "
                "{ localFee zonalFee nationalFee startSlab incrementalSlab } }")
        out = {}
        for field, op in self.FEES.items():
            q = (f"query {op}($input: SettlementInput!) {{ settlement(input: $input) {{ {field} {{ displayName "
                 f"namespace agreementIds serviceProfile slabs {{ {slab} {ship} }} }} }} }}")
            data = self._post("/orchestrator/graphql?", {"operationName": op, "query": q, "variables": {"input": {
                "serviceProfile": service_profile, "partnerContext": "flipkart", "darwinTier": tier,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "fsn": fsn}}})
            out[field] = ((data.get("data") or {}).get("settlement") or {}).get(field)
        return out

    def price_history(self, listing_id: str, attribute: str = "esp") -> list[dict]:
        """Past changes of a listing's esp (settlement) or ssp (selling price), newest first:
        channel, timestamp (ms), old_value, new_value."""
        r = self.s.get(f"{BASE}/napi/listing/priceUpdateHistory", params={"id": listing_id, "attribute": attribute},
                       headers=self._json_headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise FlipkartError(f"Flipkart price history: HTTP {r.status_code}")
        return r.json() or []

    def update_settlement(self, sku: str, fsn: str, mrp: float, selling_price: int, esp: int,
                          user_name: str) -> dict:
        """CHANGES THE LIVE PRICE. Sets a listing's bank settlement (esp) with the selling price the
        calculator gives for it, as Seller Hub's "Edit settlement" does. Answers {"status": "SUCCESS"}
        or {"status": "FAILURE", "errors": [{"code", "description"}]} (limits: +20% / -30% a time,
        2 increases a day, discount up to 90%, Rs 109 floor). Not retried."""
        data = self._post(f"/napi/listing/updateSellingPrice?userName={requests.utils.quote(user_name)}", {
            "listingUpdate": {sku: {"product_id": fsn, "price": {
                "mrp": mrp, "selling_price": int(selling_price), "currency": "INR", "esp": int(esp)}}},
            "priceRecoUpdate": {}}, tries=1)
        return data.get(sku) or {"status": "FAILURE", "errors": [{"description": f"no answer for {sku}"}]}

    def seller_name(self) -> str:
        """The display name Seller Hub sends as userName on a price update."""
        f = self.s.get(f"{BASE}/getFeaturesForSeller", headers={"X-Requested-With": "XMLHttpRequest"},
                       timeout=self.timeout).json()
        return (f.get("sellerDetails") or {}).get("displayName") or f.get("displayName") or ""
