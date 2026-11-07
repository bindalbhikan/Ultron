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
and OMSGuru refreshes it about monthly. Copy the current `access_token` into the secret
`MYNTRA_API_ACCESS_TOKEN` when it nears expiry. The token and the merchant credentials are secrets:
GitHub secrets / local `.env` only, never committed or logged.

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
from datetime import date
from typing import Iterator

from ..core.config import env

log = logging.getLogger(__name__)

DEFAULT_DOMAIN = "https://api-integration.myntra.com"
TIMEOUT = 60


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
