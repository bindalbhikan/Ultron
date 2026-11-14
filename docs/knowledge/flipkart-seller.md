# Flipkart Seller Hub (`seller.flipkart.com`) — what the calls are for

Learned from the owner's capture of 1 Nov 2026 (report centre, payments pages, dashboard).
Field-level detail of every call: `api/seller.flipkart.com.md`. Login and the calls the bots already
use: `docs/PORTALS.md` and `portals/flipkart.py` (`FlipkartClient`).

All calls go through the logged-in session with the `fk-csrf-token` header (from
`/getFeaturesForSeller`, `csrfToken`). **Read** = only reads; **Changes** = saves something.

## Report centre (`/napi/metrics/bizReport/...`)

The same flow for every report: `POST submitReport?reportName=<name>` with
`{from_date, to_date, file_format: "EXCEL", type: "ONETIME", filters: [{name: "date", operator:
"RANGE", values: [from, to]}]}` → `{request_id: {request_id, eta}}`; poll `POST report/getReportsV2`
(`report_requests[]`: `request_id`, `report_name`, `status` → `FILE_STORED`) → `GET
downloadReport/<file>?sellerId&token`. `FlipkartClient.request_report` / `report` already do this
(a request for the same dates is reused). Every report's filters: `GET report/2/detail?reportName=`
(all of these: `date` RANGE + `seller_id`, EXCEL).

| Group (`reportCategories`) | Report (`reportsNew?reportGroupName=`) | What it holds | Used by |
|---|---|---|---|
| Fulfilment Reports | **Orders** (id 5) | every order line, status, dates, SLA, cancellation / return ids — **no price** | `portal-reports` (ORDER REPORT) |
| Fulfilment Reports | **Returns** (id 11) | every return line, reason, status, dates (`return_approval_date`) | return analysis (RETURN REPORT), `flipkart-tat` |
| Fulfilment Reports | Pickup Report (31), DBD Breached Shipments (134), Seller Cancelled Shipments (135) | handovers, delivery-by-date breaches, seller cancellations | not used |
| Tax Reports | **Sales Report** (14) | every sale / return event with invoice values ("Start here") | return analysis, sale (Flipkart value) |
| Tax Reports | TDS (17), GSTR return report (19) | TDS break-up; GSTR-1 / GSTR-8 summary | not used |
| Payment Reports | **Settled Transactions** (16) | every transaction settled in the range: orders, PLA, TDS, SPF, storage, recall | `portal-reports` (PAYMENT REPORT) |
| Payment Reports | **Profit and Loss Report** (89) | profit / loss of the orders received in the range; best asked for after the 15-day return window | not used yet: a candidate for the business reporting's Flipkart margin |
| Payment Reports | Financial Year Report (74) | settled transactions before the previous quarter | not used (history) |
| Payment Reports | Older SPF Claims Report (75) | SPF claims older than 9 months, approved amounts and reasons | not used |
| Invoices | Commission Invoice | the monthly summary of marketplace charges | not used |

Other report calls: `getReportsCount` (counts), `getScheduledReports` (repeat schedules; the bots use
one-time requests only).

## Payments pages (`/napi/payments/...`, all Read)

| Call | What it gives |
|---|---|
| `GET fetchLastPaymentDetails` | the last payout per event, split prepaid / postpaid, with `bifurcation_details` (order, protection fund, rewards, service, taxation) and UTR / settlement status |
| `GET fetchOutstandingPaymentDetails` | money still to be paid, the same split, and the coming `payments[]` (start date, payment date) |
| `GET fetchSellerStatement?settlement_type` | account statement: opening / closing balance, total payment, settlement dates, advice id, UTR |
| `GET fetchBlockStatus?tier` | whether a payment is expected, delayed or failed, payout cycle changes |

## Seller standing (Read; plan item W8)

| Call | What it gives |
|---|---|
| `GET /napi/darwin/finalTier` | the seller tier, when it changes next, and the breach / cancellation / revenue / units values against each tier's benchmark — a tier drop = W8 "rating drop" alert |
| `GET /napi/metrics/darwin/v3/tiering-metrics` | the metrics behind the tier (customer experience, sales, service quality), evaluation dates |
| `GET /napi/get-notifications-count?mode&notificationStatus&priority[]` | count of seller notifications by priority — new ones = W8 "notice" alert |

## Account

`GET /getFeaturesForSeller` (seller id, type, csrf token), `GET /napi/get-locations` (warehouses),
`GET /napi/seller-capability/fetch-capability`. Noise: `fed-ads/navbar`, `getExperimentVariant`,
`ui-config`, `fdp/batch-events` (tracking), `fkgrowthcapital/*` (loan offers), `partner-master/v0/ads`,
`riddler/*`, `sellerBuyerCommunications/*`, `srm/getQuestionnaireByFeature`.

## Investigation of 7 Nov 2026

Official OAuth APIs are documented separately in [flipkart-seller-api.md](flipkart-seller-api.md).
They use a different host and authentication from this Seller Hub session API. No authenticated
live API replay was performed in this investigation; the evidence below is the existing local
capture and checked-in client, not a fresh successful seller session.

### GraphQL is a business API, not just background traffic

The capture contains 148 requests to `POST /napi/graphql`, covering 47 named operations.
See [the operation inventory](flipkart-graphql.md) for variable names and query/mutation kind.
Important candidates include:

| Operation | Likely use, inferred from its name and variables |
|---|---|
| `TransactionPage_getTransactionsTableData` | Transaction rows filtered by dates, settlement status, tab and sub-tab; `token` and `size` suggest cursor paging |
| `TransactionPage_getTransactionsHeaderStrip` | Totals for the same transaction filters |
| `TransactionPage_getTransactionsSubTabs`, `TransactionPage_getTableFilters` | Discover supported tabs and filters before constructing transaction queries |
| `GetUpcomingPaymentsV3`, `GetEarningsSummary` | Upcoming payments and monthly earnings |
| `ReturnsCount` | Return counts by return/shipment status and out-for-delivery date range |
| `Selection_getStockWidget`, `Selection_getGmvLoss`, `GetInsightBuckets` | Stock and listing insight candidates |
| `GetBusinessSummarySalesUnits`, `GetBusinessSummaryImpressions` | Sales/visibility dashboard candidates |

The captured bodies expose `{type, error}` rather than usable business response schemas.
HTTP 200 therefore does **not** establish that an operation succeeded. Do not invent response
fields, replay inferred payloads, or treat missing data as zero. Inspect the complete query and
obtain a successful response from the relevant page before implementing any of these operations.
Do not assume an operation is read-only merely because its name starts with `Get`.

### Existing client details omitted from the capture catalogue

`src/ultron/workings/portals/flipkart.py` implements `POST /napi/metrics/search` as a read,
with `fk-csrf-token` and `x-view-name: sell_more_aggregated_groupby_view`. Body fields are
`filters`, `sort`, `metrics`, `derived_metrics`, `aggregate_by`, `interval`, `pivot`,
`page_number`, `page_size`; the response uses `data` and `total_pages`. Page numbering starts
at zero. The daily FBF query filters `location_id`; a whole date range is aggregated, so daily
reporting queries each day separately. The monthly view requests gross, cancellation and return
units and amounts. See `docs/PORTALS.md` for observed history and reconciliation limitations.

Report-list POSTs are reads; `submitReport` creates a job and consumes quota. List report requests
by group, starting at page 1 with `has_more`, rather than assuming a single page is complete.
The client's default three-page ceiling is a caller limit, not a proven server limit. Reports
must be checked for date coverage; HTTP 200 and `FILE_STORED` alone do not establish completeness.

### Remaining capture work

Capture successful responses on Orders, Returns, Listings/Inventory, payment transaction drill-down,
and SPF/support pages. Keep queries, cookies, identifiers and response values local in `netcap/`;
publish only reviewed paths, field names and meanings. Then run `scripts/knowledge/learn_netcap.py`.
No SPF claim submission endpoint or historical pickup timestamp endpoint was verified here.
