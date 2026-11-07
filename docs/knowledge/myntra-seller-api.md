# Myntra Seller API V4 (official) — what the calls are for

Not used by any bot yet. Read from Myntra's official docs (6–7 Nov 2026); **no call has been made with our
credentials**, so the paths are as documented, not tested. Request bodies and answer schemas: the Postman
collections below (this page is a map, not a spec).

- Developer Centre: `https://mmip.myntrainfo.com/` (PPMP workflow: `/documentation/myntra-ppmp-api-v4`)
- Seller API V4: `https://documenter.getpostman.com/view/34879541/2sA3JNbLQG`
- Listing management: `https://documenter.getpostman.com/view/34879541/2sA3kbhJoc`
- B2B / IJIT: `https://documenter.getpostman.com/view/34879541/2sA3kbhJob` (not mapped; our reports are PPMP)

**Base**: `https://api-integration.myntra.com` (a different host from the portal's `partnersapi.myntrainfo.com`;
no login session or reCAPTCHA, so it would work from GitHub's runners).

## Login — the open blocker

- `POST /authorization/generate_token`: header `secret_key`, body `merchant_id` → access + refresh token in the
  **answer headers**. Access token documented as valid 30 days; the docs say generate once, then only refresh.
- `POST /authorization/refresh_token`: header `refresh_token` + merchant id.
- The Merchant Id / Secret Key are the ones in OMSGuru's Myntra channel settings (MAIN). OMSGuru pushes
  inventory and order status with them. **Do not call `generate_token` until it is confirmed (Myntra or
  OMSGuru) that a new token does not end OMSGuru's** — better: separate API credentials for Ultron.
  Credentials go in GitHub secrets only, never in files or logs.

## Read calls — what each could give us

| Call | What it gives / which working could use it |
|---|---|
| `GET /partner/v4/order/getOrderList?page&statusCode&startDate&endDate` | orders by status and date, live: could replace the `Seller_Orders_Report` job (15-min cooldown, data stale before ~9 AM) for SJIT, TAT, portal sale, morning |
| `GET /partner/v4/order/:sellerOrderId`, `GET /partner/v4/packet/:packetId` | one order / packet |
| `POST /partner/v4/returns/returnRecon` | return search + return details (Return Search and Get Return Details use the same path): returns, SPF |
| `POST /partner/v4/inventory/search` | stock Myntra holds per SKU: cross-check of OMSGuru's inventory push |
| `GET /partner/v4/payments/history/:paymentMethod?fromDate&toDate&pageNo&pageSize` | payouts: M2 payment reconciliation, `myntra-spf` |
| `POST /partner/v4/payments/report/:reportType` | invoice / payment reports (incl. SPF accepted): M2 |
| `GET /partner/v4/packet/:packetId/getInvoiceDetails/`, `.../getDocument/?type=invoice`, `.../shippingLabel/` | invoice data, invoice PDF, label |
| `GET /partner/v4/packet/:packetId/creditNoteDetails`, `GET /partner/v4/returns/:returnId/creditNoteDetails`, `POST /partner/v4/returns/creditNote/download` | credit notes per packet / return |
| `GET /partner/v4/stores/fetch_wh_status`, `POST /partner/v4/stores/fetch_status` | whether the store / warehouse is live; status of an on/off job |
| `GET /partner/catalog/v2/product/search/nofilter` (`q`, `start`, `cursorMark`, `sellerApprovalStatus`) | listings and product details: listing status checks, grouping |
| `GET /partner/catalog/diy/task/{task_id}`, `POST /partner/catalog/diy/status/export/{task_id}` | status of a catalogue upload and its style-level errors |
| `GET /partner/v4/order/:id` | documented as "Get Seller OTP" (same shape as order lookup): confirm what it is before use |

## Changes calls — never by the agent

OMSGuru is the one system that writes orders and inventory; a second writer would clash. Prices and discounts
are changed by people (plan §5).

| Call | What it changes |
|---|---|
| `PUT /partner/v4/inventory/update`, `PUT /partner/v4/inventory/async/update` | stock (OMSGuru does this) |
| `PUT /partner/v4/order/:sellerorderId/:EventType`, `PUT /partner/v4/trackingNumber/:trackingNo/readyToShip`, `PUT /partner/v4/order/readyToDispatch/`, `PUT /partner/v4/order/:sellerOrderId/cancelItems`, `PUT /partner/v4/order/:sellerOrderId/assignmentUpdate` | order status, RTS / RTD, cancel lines, allocation (OMSGuru) |
| `PUT /partner/v4/discount/override`, `PUT /partner/v4/discount/update` (deprecated) | discounts. The docs disagree on the longest period (six months vs "greater than 180 days") |
| `PUT /partner/v4/expiry/update` | expiry dates |
| `POST /partner/v4/returns/creditNote/upload` | uploads a credit note |
| `POST /partner/v4/stores/update_status` | switches the store on / off |
| `POST /partner/catalog/diy/import/sheetValidator?source=seller&styleCreationSource=diy&studio=other_studios&partnerEmailId` | submits a catalogue sheet |
| `POST /partner/catalog/style/v2/bulkActionUpdate/SELLER_LISTING_STATUS_UPDATE` | activates / deactivates styles (marked Work in Progress in the docs) |

Myntra also calls the seller (callbacks: Create / Update Order, Download Invoice, Failure Inventory Update,
Create Return RTO, Create Customer Return, Update Return). That needs a receiving service: OMSGuru's job, not ours.

## Before the first call

1. Confirm the token question above (or get separate credentials).
2. Start with one read call (`order/getOrderList` for one day) and compare it with the order report.
3. Find the rate limits, page sizes and date-range limits per call (not in the map).
