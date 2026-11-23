"""Myntra Seller API V4 (official) — read-only client.

A second way into Myntra's data, separate from the partner-portal report jobs in `myntra.py`.
The portal (`partnersapi.myntrainfo.com`) needs a hand-made login session and serves CSV report
jobs with a 15-minute cooldown and once-a-day stale data; this API (`api-integration.myntra.com`)
needs only a bearer token, has no reCAPTCHA or session, and answers live — so it works from
GitHub's runners. See `docs/knowledge/myntra-seller-api.md` for the full endpoint reference.

**Token — borrowed, never minted.** The API authenticates with an `access_token` that is issued by
`POST /authorization/generate_token` (merchant id + secret key). We do **not** call that: minting a
new token can end OMSGuru's, which runs Myntra inventory and order sync on the same merchant id.
Instead we reuse the token OMSGuru already holds. It lives in OMSGuru's Myntra channel settings
(field `data[ChannelCompany][api_token]`, a JSON `{access_token, refresh_token}`), is a 30-day JWT,
and OMSGuru renews it itself, so a copy goes stale: `MyntraApi.for_account(account)` reads it live
from the account's channel (`CHANNELS`) at every run, in memory only, never stored or logged.

What it holds (tested 23 Nov 2026): the account's PPMP orders while open (WP / PK / RFR / SH), live,
line for line the portal report's PPMP lines; SJIT / FBM and closed orders are only in the portal.

Settings (GitHub secrets / `.env`):
  MYNTRA_API_DOMAIN        https://api-integration.myntra.com
  MYNTRA_API_STORE         the store code, e.g. C45111W17453 (the `x-partner-store` header)
  MYNTRA_API_ACCESS_TOKEN  the access token borrowed from OMSGuru

Read-only by rule: this client never calls a write endpoint (inventory/order/discount/store
updates). OMSGuru is the only writer; a second writer would clash (AGENTS.md).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Iterator

from ..core.config import env

log = logging.getLogger(__name__)

DEFAULT_DOMAIN = "https://api-integration.myntra.com"
TIMEOUT = 60

# getOrderList statuses that answer (C / F / L / RTO give HTTP 500: closed orders are only in the portal reports)
OPEN_STATUSES = ("WP", "PK", "RFR", "SH")
# getOrderList answers at most 7 days at a time (HTTP 400 "EndDate cannot be greater than 7 days from startDate")
MAX_WINDOW_DAYS = 7
# x-partner-store: MAIN's seller warehouse; the token decides the seller, so it serves every account (tested 23 Nov 2026)
DEFAULT_STORE = "C45111W17453"
# The OMSGuru Myntra channel of each account, whose API token Ultron borrows. PPMP (39078) is MAIN's own data.
# MYNTRA_OMSGURU_CHANNELS ("MAIN=45111,EXIM=64106") replaces or adds entries.
CHANNELS = {"MAIN": "45111", "DBCC": "47460", "FMCC": "49234", "EXIM": "64106"}
OMSGURU = "https://client.omsguru.com"
LINE_FIELDS = ("orderLineId", "status_code", "createdOn", "packedOn", "packByTime", "shipByTime", "invoiceDate",
               "cancelledOn", "sku", "mrp", "lineFinalAmount", "lineSellerFinalAmount", "quantity", "warehouse")
TIME_FIELDS = {"createdOn", "packedOn", "packByTime", "shipByTime", "invoiceDate", "cancelledOn"}


class MyntraApiError(RuntimeError):
    """A Myntra Seller API call failed or was refused."""


class MyntraApi:
    """Read-only wrapper over the Myntra Seller API V4, authenticated with a borrowed token.

    All dates are `datetime.date`. `x-partner-store` defaults to the store code; a few endpoints
    want the literal `MYNTRA` instead (pass `partner="MYNTRA"`)."""

    def __init__(self, token: str, store: str, domain: str = DEFAULT_DOMAIN):
        if not token:
            raise MyntraApiError("MYNTRA_API_ACCESS_TOKEN is not set")
        if not store:
            raise MyntraApiError("MYNTRA_API_STORE is not set")
        self.token = token
        self.store = store
        self.domain = domain.rstrip("/")

    @classmethod
    def from_env(cls) -> "MyntraApi":
        return cls(env("MYNTRA_API_ACCESS_TOKEN"), env("MYNTRA_API_STORE"),
                   env("MYNTRA_API_DOMAIN", DEFAULT_DOMAIN))

    # ---- transport -------------------------------------------------------
    def _call(self, method: str, path: str, partner: str | None = None,
              body: dict | list | None = None) -> dict:
        url = f"{self.domain}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("access_token", self.token)
        req.add_header("x-partner-store", partner or self.store)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:300]
            try:
                j = json.loads(text)
                raise MyntraApiError(
                    f"{method} {path}: HTTP {exc.code} "
                    f"{j.get('statusMessage') or j.get('message') or text}") from exc
            except json.JSONDecodeError:
                raise MyntraApiError(f"{method} {path}: HTTP {exc.code} {text}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MyntraApiError(f"{method} {path}: {exc}") from exc
        status = payload.get("statusType")
        if status == "ERROR":
            raise MyntraApiError(
                f"{method} {path}: {payload.get('statusMessage') or payload.get('message')}")
        return payload

    # ---- orders (tested) -------------------------------------------------
    def order_list_page(self, status_code: str, start: date, end: date, page: int = 0) -> dict:
        """One page of `GET /partner/v4/order/getOrderList`. Dates are ISO (YYYY-MM-DD).
        `status_code` is a Myntra order status such as PK (packed), SH (shipped), RFR
        (ready for release). The answer carries `totalCount`, `data` (orders, each
        `{orderId, orderLines[]}`), `pages`."""
        qs = urllib.parse.urlencode({"page": page, "statusCode": status_code,
                                     "startDate": start.isoformat(), "endDate": end.isoformat()})
        return self._call("GET", f"/partner/v4/order/getOrderList?{qs}")

    def order_list(self, status_code: str, start: date, end: date) -> Iterator[dict]:
        """Every order of a status in a date range, across pages. Yields order objects
        `{orderId, orderLines: [{orderLineId, sellerOrderId, status}, ...]}`."""
        page = 0
        while True:
            answer = self.order_list_page(status_code, start, end, page)
            rows = answer.get("data") or []
            for row in rows:
                yield row
            pages = answer.get("pages")
            if not rows or pages is None or page >= pages - 1:
                break
            page += 1

    def order(self, seller_order_id: str) -> dict:
        """`GET /partner/v4/order/:sellerOrderId` — the full order: address and customer
        fields, `orderLineEntries` (sku, mrp, packetId, invoiceNumber/Date, packedOn,
        status_code, taxEntries, quantity, ...), `charges`, `warehouse`, `trackingNumber`.
        Contains customer personal data; never log or print it."""
        return self._call("GET", f"/partner/v4/order/{urllib.parse.quote(str(seller_order_id))}")

    def packet(self, packet_id: str) -> dict:
        """`GET /partner/v4/packet/:packetId` — the order behind a packet id."""
        return self._call("GET", f"/partner/v4/packet/{urllib.parse.quote(str(packet_id))}")

    def invoice_details(self, packet_id: str) -> dict:
        """`GET /partner/v4/packet/:packetId/getInvoiceDetails/` — tax / invoice info."""
        return self._call(
            "GET", f"/partner/v4/packet/{urllib.parse.quote(str(packet_id))}/getInvoiceDetails/")

    # ---- returns / inventory / payments (present, scope not granted yet) -
    # These endpoints answer on this host but return 403 "This request is not valid" with the
    # token we borrow from OMSGuru (its grant covers orders + inventory sync, not these). Request
    # shapes are documented in docs/knowledge/myntra-seller-api.md; wire them up once a token with
    # the right scope is available (separate Ultron credentials from Myntra).
    def return_recon(self, start: date, end: date, return_type: str = "CUSTOMER_RETURN",
                     warehouse_ids: list[str] | None = None, page: int = 0) -> dict:
        """`POST /partner/v4/returns/returnRecon`. Dates DD-MM-YYYY, window <= 7 days and within
        120 days of today. Needs a token scoped for returns (currently 403)."""
        body = {"startDate": start.strftime("%d-%m-%Y"), "endDate": end.strftime("%d-%m-%Y"),
                "destinationWarehouseIds": warehouse_ids or [self.store],
                "page": page, "returnType": return_type}
        return self._call("POST", "/partner/v4/returns/returnRecon", partner="MYNTRA", body=body)

    # ---- open order lines, live (the main source for live orders since 23 Nov 2026) ----------
    def open_lines(self, start: date, end: date, statuses: tuple[str, ...] = OPEN_STATUSES,
                   workers: int = 6) -> list[dict]:
        """Every order line now open (to pick, packed, ready, shipped) with activity between start and end
        (getOrderList's range is the latest activity, not the order date: its end is exclusive), each with
        the times and amounts of its order detail (`LINE_FIELDS`, customer data left out). An order is
        read once even when it shows under two statuses. A range longer than the API's 7 days ("EndDate cannot be
        greater than 7 days from startDate") is asked for in 7-day windows."""
        from concurrent.futures import ThreadPoolExecutor
        from datetime import timedelta
        windows, a = [], start
        while a < end:
            windows.append((a, min(end, a + timedelta(days=MAX_WINDOW_DAYS))))
            a = windows[-1][1]
        ids: list[str] = []
        seen: set[str] = set()
        for status in statuses:
            for w_start, w_end in windows:
                for row in self.order_list(status, w_start, w_end):
                    for line in row.get("orderLines") or []:
                        so = str(line.get("sellerOrderId") or "")
                        if so and so not in seen:
                            seen.add(so)
                            ids.append(so)
        with ThreadPoolExecutor(max(1, workers)) as pool:
            details = list(pool.map(self._detail_with_retry, ids))
        out: list[dict] = []
        for so, detail in zip(ids, details):
            data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
            for entry in data.get("orderLineEntries") or []:
                out.append(order_line(so, entry))
        return out

    def _detail_with_retry(self, seller_order_id: str) -> dict:
        from ultron.core.retry import backoff, retry_call
        return retry_call(lambda: self.order(seller_order_id), tries=3, wait=backoff(2, 10),
                          on=(MyntraApiError,), log=log, what=f"Myntra API order {seller_order_id[:8]}...")

    @classmethod
    def for_account(cls, account: str, oms=None) -> "MyntraApi":
        """The account's API with the token OMSGuru holds right now (never minted by us, never stored)."""
        return cls(borrowed_token(account, oms), env("MYNTRA_API_STORE") or DEFAULT_STORE,
                   env("MYNTRA_API_DOMAIN", DEFAULT_DOMAIN))


def channels() -> dict[str, str]:
    out = dict(CHANNELS)
    for part in (env("MYNTRA_OMSGURU_CHANNELS") or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().upper()] = v.strip()
    return out


def api_time(value) -> "datetime | None":
    """The API's "22-11-2026 09:18:39" as a datetime (None when empty or another shape)."""
    try:
        return datetime.strptime(str(value).strip(), "%d-%m-%Y %H:%M:%S") if value else None
    except ValueError:
        return None


def order_line(seller_order_id: str, entry: dict) -> dict:
    """One order line of an order detail, only its order fields (no customer data), times as datetimes."""
    line = {"sellerOrderId": seller_order_id}
    for key in LINE_FIELDS:
        value = entry.get(key)
        line[key] = api_time(value) if key in TIME_FIELDS else value
    return line


def borrowed_token(account: str, oms=None) -> str:
    """The access token OMSGuru holds for the account's Myntra channel, read from its channel settings now (it
    renews the token itself about monthly, so a copy goes stale: the 7 Nov copy died on 8 Nov). Never logged."""
    import base64
    cid = channels().get(account.upper())
    if not cid:
        raise MyntraApiError(f"no OMSGuru Myntra channel for {account} (MYNTRA_OMSGURU_CHANNELS)")
    if oms is None:
        from ..core import clients
        oms = clients.omsguru()
    from ultron.core.html import parse
    page = parse(oms.get(f"{OMSGURU}/channel_companies/edit/{cid}/1/1").text)
    field = page.select_one('[name="data[ChannelCompany][api_token]"]')
    raw = (field.attr("value") or field.text()) if field else ""
    try:
        token = json.loads(raw)["access_token"] if raw.strip().startswith("{") else raw.strip()
    except (ValueError, KeyError, TypeError):
        token = ""
    if not token:
        raise MyntraApiError(f"OMSGuru channel {cid} ({account}) holds no Myntra API token")
    try:
        exp = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))["exp"]
        if datetime.fromtimestamp(exp) <= datetime.now():
            raise MyntraApiError(f"OMSGuru's Myntra API token for {account} expired {datetime.fromtimestamp(exp):%d %b %Y}")
    except (IndexError, ValueError, KeyError):
        pass   # not a JWT we can read: the API itself says when it is refused
    return token
