# Myntra Seller API V4 (official) — tested reference

A second way into Myntra's seller data, separate from the partner-portal report jobs in
`portals/myntra.py`. This page is both a **manual guide** (curl + Python you can run by hand) and the
**agent reference** (Ultron reads it with `knowledge_search` / `knowledge_read`; the client is
`portals/myntra_api.py`).

- **Status**: not wired into any working yet. Order reads are fully tested; returns / inventory /
  payments reach the server but are not authorised for our borrowed token (see below).
- **Last tested**: 7 Nov 2026, from the owner's PC, with OMSGuru's live token.

## 1. When to use this vs the portal

| | Portal `portals/myntra.py` | This API `portals/myntra_api.py` |
|---|---|---|
| Host | `partnersapi.myntrainfo.com` | `api-integration.myntra.com` |
| Auth | hand-made login session + reCAPTCHA | bearer `access_token` (no session) |
| Data | CSV report jobs, 15-min cooldown, stale before ~9 AM | live, immediate |
| Runs from GitHub runner | often 403 → Ultron Phone | yes (no session, no reCAPTCHA) |

So for live order status (SJIT, TAT, portal sale, morning) this API avoids the report-job cooldown
and the once-a-day stale copy. The portal stays for anything the API will not give us.

## 2. Base and authentication

- **Base**: `https://api-integration.myntra.com` (Akamai-fronted). A bare
  `POST /authorization/generate_token` answers `400 body.merchant_id is required`, confirming the host.
- **Token model**: every call carries a header `access_token` (a 30-day JWT). The token is minted by
  `POST /authorization/generate_token` (header `secret_key`, body `merchant_id`) and renewed by
  `POST /authorization/refresh_token`.

### Token — borrowed from OMSGuru, never minted by us

OMSGuru runs Myntra inventory and order sync on the **same merchant id**. Minting a new
token can end OMSGuru's and stop its sync. So Ultron **does not call `generate_token` / `refresh_token`**.
Instead we reuse the token OMSGuru already holds:

- It is in OMSGuru's Myntra channel settings, field `data[ChannelCompany][api_token]`, a JSON
  `{access_token, refresh_token}` — page `client.omsguru.com/channel_companies/edit/45111/1/1` (MAIN).
- The access token is a 30-day JWT (`origin: OMSGURU-V4`); OMSGuru refreshes it about monthly.
- When it nears expiry, re-read that field and update the secret `MYNTRA_API_ACCESS_TOKEN`.
- The token and the merchant credentials are **secrets**: GitHub secrets / local `.env` only, never
  committed or logged.

### Settings

| Secret / `.env` | Value |
|---|---|
| `MYNTRA_API_DOMAIN` | `https://api-integration.myntra.com` |
| `MYNTRA_API_STORE` | store code, e.g. `C45111W17453` (the `x-partner-store` header) |
| `MYNTRA_API_ACCESS_TOKEN` | the access token copied from OMSGuru |

## 3. Common request rules

- **Headers on every call**: `access_token: <token>`, `x-partner-store: <value>`,
  `Content-Type: application/json`.
- **`x-partner-store` is per-endpoint**: the **store code** (`C45111W17453`) for the order endpoints;
  the literal **`MYNTRA`** for `returnRecon` and `payments/*`. When unsure, the error names what it wants
  (e.g. `headers.x-partner-store must be [MYNTRA]`).
- **Date formats differ by endpoint** (checked against the server):
  - order endpoints: **ISO** `YYYY-MM-DD`
  - `payments/history`: **ISO** `YYYY-MM-DD` (regex-enforced)
  - `returns/returnRecon`: **DD-MM-YYYY**
- **Answer shape**: JSON with `statusType` (`SUCCESS` / `ERROR`), a numeric `statusCode` (see §7),
  `statusMessage`, and usually `data`. List answers add `totalCount` / `pages` or `hasNextPage`.
- **Never log customer data**: order and packet answers include receiver name, address, mobile, email.

## 4. Endpoints — tested and working (read-only)

### 4.1 Order list — `GET /partner/v4/order/getOrderList`
Query `page` (0-based), `statusCode`, `startDate`, `endDate` (ISO). Header store = store code.
```
GET /partner/v4/order/getOrderList?page=0&statusCode=PK&startDate=2026-11-01&endDate=2026-11-06
```
Answer: `{statusCode:1007, totalCount, pages, data:[ {orderId, orderLines:[{orderLineId, sellerOrderId, status}]} ]}`.
Paginate with `page=0,1,…` up to `pages`. Tested 7 Nov: `PK` (packed) 174, `SH` (shipped) 310 over 3 days,
`RFR` 0. `statusCode` values seen: `RFR` ready-for-release, `PK` packed, `SH` shipped.

### 4.2 Order detail — `GET /partner/v4/order/:sellerOrderId`
`sellerOrderId` comes from an order line above. Answer (`statusCode:1005`) top-level keys:
`receiverName, address, city, locality, state, zipcode, country, mobile, email, paymentMethod,
sellerOrderId, uidx, orderLineEntries[], charges[], sellerId, warehouse, orderEntry, trackingNumber,
status, store, expectedDeliveryTime`.
`orderLineEntries[]` item keys (what SJIT / portal-sale / VMS need):
`orderLineId, sku, mrp, quantity, lineFinalAmount, lineSellerFinalAmount, status_code, packedOn,
cancelledOn, invoiceNumber, invoiceDate, packetId, taxEntries, unitSalePriceWithoutTax,
shipByTime, packByTime, acceptByTime, customerPromiseTime, processingStartTime, shippingMethod,
tagloopRequired, invoiceQRCodeUrl, warehouse, ...`.
`charges[]` item keys: `activeAmount, chargeCode, chargeType, paidAmount, claimedByEntityId`.
**Holds customer PII — do not print or log the body.**

### 4.3 Packet — `GET /partner/v4/packet/:packetId`
`packetId` is on each order line. Answer `statusCode:1005`, same order shape as 4.2.

### 4.4 Invoice details — `GET /partner/v4/packet/:packetId/getInvoiceDetails/`
Answer `statusCode:1003` "Tax info fetched successfully" (tax / invoice breakup). Trailing slash matters.

## 5. Endpoints — reach the server but not authorised for our token

These answer on the host but return `403 "This request is not valid"` with the borrowed OMSGuru token
(its grant covers orders + inventory sync, not these). The request shapes below are pinned from the
server's own validation errors, so they are ready the day a scoped token exists (separate Ultron
credentials from Myntra, or OMSGuru enabling the scope).

- **Returns** — `POST /partner/v4/returns/returnRecon`, header store = `MYNTRA`.
  Body JSON: `{startDate, endDate (DD-MM-YYYY), destinationWarehouseIds:[store], page, returnType}`.
  `returnType` ∈ `CUSTOMER_RETURN` / `COURIER_RETURN`. Rules the server enforces: window
  **≤ 7 days**, `startDate` within **120 days** of today. Same path serves "Get Return Details"
  with body `{id:"<returnId>"}`.
- **Inventory** — `POST /partner/v4/inventory/search`. Body is a **JSON array of SKU strings**
  (`["SKU1","SKU2"]`, max 100). Returns `{inventoryDetails:[{sku, stores:[{stores_code, inventoryCount}]}], failedEntries}`.
- **Payments history** — `GET /partner/v4/payments/history/:paymentMethod`, header store = `MYNTRA`,
  `paymentMethod` ∈ `PREPAID` / `POSTPAID`. Query `fromDate`, `toDate` (**ISO** `YYYY-MM-DD`),
  `pageNo`, `pageSize`. Returns `{totalElements, totalPages, totalAmount, payments:[{paymentMethod,
  utrNumber, paymentDate, amount, ...}]}`.

## 6. Documented but not confirmed here

- `POST /partner/v4/payments/report/:reportType` (MONTHLY_REPORTS / ONE_TIME_REPORTS incl.
  `SPF_Accepted`, `PG_Forward_Settled`, …) and `GET /partner/v4/stores/fetch_wh_status` both answered
  **404** at these exact paths — the path or method differs from the Postman collection; confirm before use.
- Order/packet document downloads: `.../getDocument/?type=invoice`, `.../shippingLabel/`,
  `.../creditNoteDetails` — documented, not yet called.

### Write endpoints — never called by Ultron
Inventory/order/discount/expiry/store-status updates exist but OMSGuru is the only writer; a second
writer would clash (AGENTS.md). The client exposes **no** write method.

## 7. Status codes

| code | meaning |
|---|---|
| 1002 | inventory retrieved |
| 1003 | tax / invoice info fetched |
| 1005 | order / packet retrieved |
| 1007 | order list / returns retrieved |
| 401 | `access_token is invalid` — token missing/expired → re-copy from OMSGuru |
| 403 | `This request is not valid` — usually a scope the token lacks, or a failed deeper validation |
| 400 | body/params wrong — the message names the field (e.g. `must be [MYNTRA]`, date pattern, window rules) |
| 2006 | returns date-window rule broken (≤7 days, within 120 days) |

## 8. Manual quick start

```bash
# from the repo root, with MYNTRA_API_* in .env
TOKEN=$(grep ^MYNTRA_API_ACCESS_TOKEN= .env | cut -d= -f2-)
STORE=$(grep ^MYNTRA_API_STORE= .env | cut -d= -f2-)
curl -s "https://api-integration.myntra.com/partner/v4/order/getOrderList?page=0&statusCode=SH&startDate=2026-11-01&endDate=2026-11-06" \
  -H "access_token: $TOKEN" -H "x-partner-store: $STORE" -H "Content-Type: application/json" | head -c 400
```

## 9. Agent-ready client — `portals/myntra_api.py`

```python
from datetime import date, timedelta
from ultron.workings.portals.myntra_api import MyntraApi

api = MyntraApi.from_env()            # reads MYNTRA_API_* from the environment
today = date.today()

for order in api.order_list("SH", today - timedelta(days=3), today):
    detail = api.order(order["orderLines"][0]["sellerOrderId"])
    # detail["orderLineEntries"]: sku, packetId, invoiceNumber, packedOn, ...  (PII inside — do not log)

api.packet(packet_id)                 # order behind a packet id
api.invoice_details(packet_id)        # tax / invoice info
```
The client is **read-only by rule**: it has no write method, loads the borrowed token from env, raises
`MyntraApiError` on any `ERROR`/HTTP failure, and defaults `x-partner-store` to the store code (it sends
`MYNTRA` where an endpoint needs it). `return_recon(...)` is present but raises until a scoped token exists.

## 10. Sources

- Seller API V4 Postman: `https://documenter.getpostman.com/view/34879541/2sA3JNbLQG`
- Listing management Postman: `https://documenter.getpostman.com/view/34879541/2sA3kbhJoc`
- Developer Centre: `https://mmip.myntrainfo.com/` (`/documentation/myntra-ppmp-api-v4`)
