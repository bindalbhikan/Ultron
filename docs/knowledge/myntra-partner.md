# Myntra partner portal (`partnersapi.myntrainfo.com`) — what the calls are for

Learned from the owner's captures of 23–24 Oct 2026 (dashboard, OTC page, SPF tickets, pricing).
Field-level detail of every call: `api/partnersapi.myntrainfo.com.md`. Login, cooldowns and the
report jobs the bots already use: `docs/PORTALS.md` (Myntra section).

Every call needs the account's login session (worker KV `myntra_session`, `_dbcc`, `_fmcc`;
`portals/myntra.py` sends it). Answers are `{status: {statusCode, statusMessage, statusType}, data}`
unless noted. **Read** = only reads; **Changes** = saves something on Myntra: never called by the
agent without the owner's approval, and only through a working built for it.

## Already used by the bots

| Call | Kind | Used by |
|---|---|---|
| `GET /api/boot/partners` | Read | `portals/myntra.py`: which account the session belongs to (partner id), xsrf token |
| `GET /api/location/otc?trip&warehouse` | Read | `myntra-otp`: courier pickup / return OTPs (`otcDetails[]: courierCode, otc`) |
| `GET /api/partners/report/summary/payment-history` | Read | `myntra-spf`: payments (`payments[]: paymentMethod, utrNumber, paymentDate, amount, adviceId`) |
| `GET /api/spf/v2/fetchClaimByTicketId`, `GET /api/file-manager/getUploadToken/spfJob`, `POST /api/spf/createRnrBulkTickets` | Read / Changes | `myntra-spf`: claims read, bulk SPF tickets (file uploaded to the signed link, then the job) |

| `GET /api/file-manager/getUploadToken/cms`, `POST /api/diy-cataloguing/style-grouping/bulk-upload/submit`, `.../find/entries`, `.../export/report` | Read / Changes | `myntra-grouping`: colour group uploads, their jobs and result reports |

## Not used yet — what each could give us

### Notices and seller rating (plan item W8)

| Call | Kind | What it gives |
|---|---|---|
| `GET /api/partners/notifications/announcements?start&fetchSize` | Read | Myntra's announcements to the seller: `title`, `content`, `priority`, `activationDate`, `expiryDate`, `createdOn`. New ones since the last run = the W8 "new notice" alert. |
| `GET /api/partners/notifications/tasks?recipient&type&fetchSize` | Read | the seller's pending tasks / action items (`data` list). |
| `GET /api/partners/seller-performance/dashboard` | Read | quarterly seller scorecard: `evalQuarter`, `totalStars`, `finalSellerTier`, `metricScores[]`, and last quarter's `previous*` metrics (cancel, breach, return, rating, freshness). A drop in stars / tier = W8 "rating drop" alert. |
| `GET /api/partners/seller-performance/contract-tier`, `/tier-cutoff` | Read | the contract tier and the cut-offs for each tier. |
| `GET /api/seller-dashboard/home/summary` | Read | health per tab: overview, listing and inventory, pricing, customer impressions (`health`, `gmv_impact`). |
| `GET /api/seller-dashboard/summary` | Read | today / this week GMV and orders, fulfilled, cancellation and return requests, pending packing / handover — a quick cross-check for `morning` and `sla`. |
| `GET /api/seller-dashboard/actions-cards` | Read | Myntra's suggested action cards (`cardName`, `description`, `priorityWeight`, `redirectionUrl`). |

### Payments (plan item M2)

| Call | Kind | What it gives |
|---|---|---|
| `GET /api/partners/report/summary/next-payment` | Read | the next payout: `paymentDate`, `prepaidAmount`, `postpaidAmount`, `totalAmount`. |
| `GET /api/partners/report/summary/outstanding-payment` | Read | money still due: `prepaidAmount`, `postpaidAmount`, `totalAmount`, `updated_at`, `detailsLink`. |
| `GET /api/partners/report/summary/payment-history?fromDate&toDate&type&pageNo&pageSize` | Read | every payout with UTR and advice id (already read by `myntra-spf`). With the order report it is the start of payment reconciliation: delivered orders vs settled amounts. |
| `GET /api/partners/sellerreports/all-new?month&year` | Read | the list of monthly seller reports (`data.OTHERS[]: displayName, reportName, reportPath`) — settlement / commission statements to download. |

### Pricing and discounts (owner's action only)

| Call | Kind | What it does |
|---|---|---|
| `POST /api/pricing/fetchRecommendationsFilter` `{pageIndex, pageSize, tab}` | Read | Myntra's price recommendations per style: MRP, current selling price, settlement amount, commission %, GTA / pick-and-pack fees. Useful for the MIS net margin (instead of guessed `MIS_RATES`). |
| `POST /api/pricing/settlement-pricing/view` `{styleId}` | Read | one style's full price breakdown (commission, fees, settlement). |
| `GET /api/pricing/fetchSellerTerms` | Read | the seller's commercial terms. |
| `POST /api/pricing/filterDos/{partner}` | Read | discount overrides (`discountOverrideDTOs[]`: type, value, start / end, status) — which styles carry which discount (zero TD check). |
| `POST /api/pricing/jobtracker/job/filterjobs`, `GET /api/pricing/jobtracker/job/{id}` | Read | status of bulk pricing jobs (`status`, `successFileName`, `errorFileName`). |
| `POST /api/pricing/settlement-pricing/calculate/CALCULATE_SELLING_PRICE` | Read (calculator) | selling price for a wanted settlement amount. |
| `PUT /api/pricing/settlement-pricing/approve/CALCULATE_SELLING_PRICE` | **Changes** | sets a style's selling price. Never by the agent (plan §5: prices are changed by people). |
| `PUT /api/pricing/sellerDiscountAction/{partner}` `{discountOverrideIDStatuses[]}` | **Changes** | accepts / rejects discount overrides. Never by the agent. |

### Account and warehouse

| Call | Kind | What it gives |
|---|---|---|
| `GET /api/partners/vms/v3/partner?ids` | Read | the partner record (name, status, MSME, contact persons). |
| `GET /api/partners/vendorService/v3/partnerContactAddress/partner/addressType/SHIPPING` | Read | the shipping address(es) and warehouse codes. |
| `POST /api/warehouse/getWarehouseDetailsInBulk` | Read | warehouse details (zones, capacity, status). |
| `GET /api/partners/leftnav/fbm-status` | Read | `isFbm`: whether the account is fulfilled by Myntra. |
| `GET /api/spf/v2/getTickets?status&modelType&page&pageSize` | Read | the SPF ticket list (status, compensation amount, UTR). |
| `GET /api/spf/fetchNewClaim?id` | Read | the returns that can be claimed on a new SPF ticket. |
| `POST /api/spf/createFwTicket` | **Changes** | opens a dispute on a rejected claim (`ticketId, description, orderId, returnId, trackingId, skuId, styleId, issueCategory, returnReason, attachments`), used by `myntra-spf`. The box's terms speak of notice within 7 days of RTS delivery and at least 5 images for used products; a dispute with no images was accepted on 4 Nov 2026. |

Left out as noise: `seller-activation/seller-achievements`, `actions-cards/card-event` (click
tracking), `delighted/people` (survey, 403).
