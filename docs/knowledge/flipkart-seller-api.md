# Flipkart official Seller APIs

Researched 7 Nov 2026 from the owner's [Developer API v3.0 index](https://seller.flipkart.com/api-docs/fmsapi_index.html)
and the official [API Platform Hub](https://flipkart.github.io/fk-api-platform-docs/docs/intro).
Status: documentation verified; authenticated calls and account entitlements not tested.
Seller Hub reverse-engineered APIs are in [flipkart-seller.md](flipkart-seller.md).

## Hosts and authentication

Orders, shipments, listings and returns use `https://api.flipkart.net/sellers`.
The report reference instead specifies `https://api.flipkart.net/reports` (no `/sellers`).
Sandbox uses `sandbox-api.flipkart.net`; never send sandbox lifecycle operations to production.

Seller Hub login cookies and `fk-csrf-token` do not replace an official API bearer token.
For the seller's own application, Developer Access provides an app ID and secret. The documented
client-credentials exchange is `GET https://api.flipkart.net/oauth-service/oauth/token`, with
`grant_type=client_credentials`, scope `Seller_Api` (the guide also lists `Seller_Api,Default`),
and HTTP Basic authentication using the app ID/secret. Business calls use
`Authorization: Bearer <access_token>`. Use the returned `expires_in`, not a hard-coded lifetime.
Third-party integrations use seller authorization through an authorization-code flow.
Source: [authentication guide](https://flipkart.github.io/fk-api-platform-docs/docs/intro).

## Orders and returns: read candidates

Paths below are relative to `/sellers`. POST search is a read; HTTP method alone does not classify side effects.

| Method and path | Inputs and purpose |
|---|---|
| `POST /v3/shipments/filter/` | `filter`, `pagination`, `sort`; search by order/dispatch dates, state, SKU and location |
| `GET /v3/shipments` | One of `shipmentIds`, `orderItemIds`, `orderIds`; retrieve shipment detail |
| `GET /v3/shipments/handover/counts` | `locationId`; pending handover counts |
| `GET /v2/returns` | `source`, created/modified date boundaries, optional location/return/tracking IDs |

Shipment search documents page sizes 1–20 and maximum retrieval of 5,000. Follow `nextPageUrl`
while `hasMore`; use smaller date windows if a query reaches the cap. Detail lookup accepts up
to 100 identifiers. Shipment fields include dispatch deadlines, `updatedAt`, order-item status,
quantity, SKU and price components. `updatedAt` is not a pickup timestamp. Search defaults to
`NON_FBF`; the reference excludes Flipkart Advantage orders. Do not use it as proof of all FBF sales.

Returns distinguishes `customer_return` and `courier_return`; the first response has at most
25 records and continuation uses `nextUrl`. Use HTTPS even where an old example says HTTP.
Source: [order API reference](https://seller.flipkart.com/api-docs/order-api-docs/OMAPIRef.html).

## Listings

Read candidates: `GET /listings/v3/{sku-ids}`, `POST /listings/v3/details`,
`POST /listings/v3/product/search`, `POST /listings/v3/search`, all under `/sellers`.
Creating listings and `/update`, `/update/price`, `/update/inventory` change business data and
were not invoked. Source: [listing reference](https://seller.flipkart.com/api-docs/listing-api-docs/LMAPIRef.html).

## Official reports: separate entitlement and workflow

**The documentation describes Settlement and FBF reports as a paid service, available only through
third-party tokens/partners.** A self-access token must not be assumed sufficient.

| Identifier | Purpose / documented constraint |
|---|---|
| `sales_ledger`, `settled_transaction_ledger` | Invoice sales and settled transaction reconciliation |
| `orders_report`, `returns_report` | Orders and reverse shipments; returns documentation claims one year of availability |
| `fbf_orders_report` | FBF orders: last 15 days, maximum 3 days per request |
| `financial_year_ledger`, `gst_returns_report` | Financial-year transactions and GST reporting |
| `profit_loss_report` | Order profitability; less than 31 days per request; allow return maturity |
| `commission_invoice_report`, `commission_invoice_transaction_report` | Commission invoices and their transactions |
| `current_inventory_report`, `stranded_inventory_report`, `unsellable_inventory_report` | Warehouse inventory categories |
| `mir_ledger`, `stock_ledger` | Monthly warehouse reconciliation and inventory movements |

The one-year return claim belongs to this official paid API. It does not invalidate the roughly
four-month completeness limit observed in this repository's Seller Hub reports. Verify actual
coverage before using either source for historical analysis.
Source: [report overview and types](https://seller.flipkart.com/api-docs/reports-api-docs/RMAPIOverview.html).

Trigger `POST https://api.flipkart.net/reports/{reportTypeIdentifier}` with `parameters` and an
optional unique `correlation_id`. This creates a report job. Read the resulting `report_id` using
`GET /reports/{reportId}/detail`. States are `TRIGGERED`, `PROCESSING`, `COMPLETED`, `EXPIRED`,
`FAILED`. Only `COMPLETED` supplies the download `location` and expiry metadata. Treat download
URLs as secrets, and never attach the API bearer token to an unrelated download host.
This is distinct from Seller Hub's `FILE_STORED` workflow and its observed 20-request daily quota;
no official API quota was verified. Source: [report reference](https://seller.flipkart.com/api-docs/reports-api-docs/RMAPIRef.html).

## Pickup time candidate: notifications

The official `shipment_pickup_complete` event includes `shipmentId`, `timestamp`, and status.
This is a candidate for collecting future pickup events, not proof of a historical lookup or the
exact physical handover time. Validate timing and location coverage before calculating on-time pickup.
Source: [event reference](https://seller.flipkart.com/api-docs/order-api-docs/NotifRef.html#pickup-complete).

Notifications require registration, signature verification and duplicate handling (delivery is
at least once). `POST /sellers/v3/notification/subscription` changes existing subscription settings;
it is not a read or proof that registration exists. No subscription was created or changed.
Source: [notification service](https://seller.flipkart.com/api-docs/order-api-docs/NotifIntro.html).

## Integration decisions still open

- Validate a seller-authorized token with small shipment, return and listing reads.
- Check report entitlement separately; retain the working Seller Hub report integration meanwhile.
- Compare row counts, date coverage and price semantics before replacing any working's source.
- Collect successful GraphQL responses for payment and inventory capabilities absent from verified reads.
- Treat dispatch, cancellation, label generation, return approval/rejection/completion, inventory/price
  changes and notification configuration as actions; API discovery does not authorize executing them.
