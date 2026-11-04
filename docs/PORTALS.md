# Portals — the outside systems the bots use

One client per system in `src/ultron/workings/portals/`. Logins are GitHub secrets / the local `.env`; nothing
here is a secret. Each section ends with the lessons that cost a run to learn.

## Myntra partner portal — `portals/myntra.py`

* **Login**: has a reCAPTCHA, never bypassed. A login made by hand in Chrome is reused: the
  `cookie:` request header copied from DevTools (Network → a `partnersapi.myntrainfo.com`
  request), saved with `python scripts/myntra/myntra_session.py [MAIN|DBCC|FMCC]` (no argument = the
  files `scripts/myntra/main.txt`, `dbcc.txt`, `fmcc.txt`) to the worker KV (`myntra_session`,
  `myntra_session_dbcc`, `myntra_session_fmcc`; MAIN also the secret `MYNTRA_SESSION_JSON`).
  Login cookies `erp.at` (3 h), `erp.rt` (24 h), `session` (30 d) are httpOnly and host-only on
  `partnersapi`: page JavaScript, captures (netcap) and a Chrome extension cannot read them.
* **Keeping it alive**: every run that uses a session saves the cookies the portal renewed back
  to the worker (`save_to_worker`); the 7 AM and 3:30 PM runs touch all three accounts. A session
  used twice a day has lasted for days. **Do not log out of the portal** — that ends the bot's
  session too. Logged out = HTTP 401 → Telegram alert.
* **Accounts**: MAIN 19170 (also SJIT), DBCC 32207, FMCC 35426 — separate logins.
* **Reports** (`storeId 2297`, `partnerType PPMP`, one job ≤ 1 month):
  `Seller_Orders_Report` 4, `Seller_Returns_Report` 12, `Return_Delivery_Report` 84.
  `POST /api/partners/report/jobs/schedule` → poll `GET /api/partners/report/jobs/search` until
  `COMPLETED` → download via `/api/file-manager/getDownloadUrl?url=<successFile>` (redirect to a
  signed link; the blob URL itself is private). A job takes ~5–10 min.
* **Cooldown**: the same report again within 15 minutes is refused with *"Internal server error
  while scheduling…"* (HTTP 200). Different reports can be requested together. After any request
  or refusal, the next request of that report waits ~16 min (`schedule()` waits out one refusal).
* **Reuse**: a job for exactly the same dates (`exact_job`) or covering them (`plan`, SJIT) is
  reused. Statuses like `INTERRUPTED`, `FAILED`, `EXPIRED` are dead — never reused or waited for.
  A job that will not download is asked for again (`collect_or_regenerate`).
* Backfilled months: the order report carries the return status as of the day it is generated.

## AJIO Seller Central — `portals/ajio.py`

* Login: Reliance seller OAuth form, username + password, no OTP (`AJIO_USERNAME/PASSWORD`).
* Dropship **order report**: `POST /malekith/vision/v1/dropship/order/report/download?from=&to=`,
  **RTV report**: `.../dropship/rtv/report/download`; form `pobIds=DV00348890,DV00316239`,
  headers `X-Tenant: AJIO`, `x-pob-id`, `businessModel: B2C`. Max **31 days** per download.
  Direct downloads — nothing to reuse or wait for.
* SPF tickets (list, detail, comment, create) — used by the AJIO SPF bot.

## Flipkart Seller Hub — `portals/flipkart.py`

* Login: JSON POST `/login` (`FLIPKART_EMAIL/PASSWORD`); CSRF from `/getFeaturesForSeller`.
* FBF units: `/napi/metrics/search` filtered on Flipkart's own warehouses (sale bot).
* Report centre (`/napi/metrics/bizReport/`): at most 20 new report requests a day; over it `submitReport` answers HTTP 500 around a 429 ("daily quota of 20 reports"). Downloading finished requests does not count.
* **Report centre**: `POST /napi/metrics/bizReport/submitReport?reportName=<name>` with
  `{"from_date","to_date","file_format":"EXCEL","type":"ONETIME","filters":[{"values":[from,to],
  "operator":"RANGE","name":"date"}]}` → poll `report/getReportsV2` (paged, 50 per page) until
  `FILE_STORED` → `GET downloadReport/<request_id>_<created_at>.xlsx?token=<id>&sellerId=<sid>`.
  Return analysis uses Tax Reports → **`Sales Report`** and Fulfilment Reports → **`Returns`**
  (the Fulfilment "Orders" report is a different one).
* **Returns retention: about four months.** Returns reports for older months are empty (~10 KB)
  or start mid-month — also when requested by hand. Such a month is left out (never shown as
  0 % returns). The Sales Report carries Return events but cannot split RTO from customer returns
  and has no reasons, so it is not used for returns.
* The local `.env` `FLIPKART_PASSWORD` was stale on 2026-10-18 (GitHub's secret works).

## Reliance SRM — `portals/srm.py`

* Statement of accounts (the AJIO vendor ledger: G4 payments, IC reversals, TOT charges):
  `POST https://srm-rrscm.ril.com/srm/rdl/api/v1/report/statement-off-acc/fetch`, company 9008.
  `payment_rows()` gives the columns of the hand-downloaded `StatementOfAccount*.xlsx`
  (DT, VENDORCODE, DOCDATE `dd.mm.yyyy`, AMOUNT, TEXT, …). Used by AJIO SPF and AJIO ads gap.

## OMSGuru returns - `workings/erp_oms_return/accept.py`

* Accept a return: Orders > Quick Returns (`/orders/quickReturns`, manual mode, searching by AWB accepts nothing) opens a form; `POST /orders/processOrderReturn` with `data[SkuQty][n][good]` and the return warehouse. It answers JSON (`"result":"OK"` or `"Fail"`).
* An order with no return yet (Ready to ship, Delivered ...) also needs `data[Invoice][confirm_return_type]` (`courier` / `customer`), else it answers "Invalid Invoice Status". One AWB can open several forms.
* Stock: accepting moves the unit from Return Transit to Putaway; In Stock does not change until someone does the Putaway (`/sku_transaction_logs/export_form` shows each move). Undo: `/orders/revertReturnReceived/<id>`.
* Order note: `POST /orders/addInvoiceNote/<id>` with `data[note]` and `oms_token` (the page's `csrf-token` meta).

## Flipkart NXT Insights

* `POST /napi/metrics/search` with `x-view-name: sell_more_aggregated_groupby_view`: gross, cancellation (it holds RTO too) and return units and amounts by order date, pivoted by state. Through this view no data before May-26; the Earn More screen shows rounded figures from Nov-25. Its rupees run above every price column of the tax Sales Report (not explained).

## DigiBizz ERP — `portals/erp.py`

* Report preview API (`ERP_USERNAME`, `ERP_PASSWORD`, `ERP_USER_TOKEN`; password AES-encrypted
  like the web app). Report **58** GR GRN (returns booked into the warehouse), report **62**
  Shipping Label Print / packing (`packed(portal, since)`).
* In report 62 the "Order ID" is the **AWB** for AJIO and the **Myntra tracking number** for Myntra.
* **Never page a report** (`skip` / `take`), measured 4 Nov 2026. Without a sort each page has its own order: a read of 28,071 rows
  repeated about 1,200 and lost about 700 with its count still right, not on every read. With a `filter`, `skip` is ignored: every
  page repeats the first 10,000 and the rest, the newest rows among them, never come. `report()` asks for everything in one request,
  sorted on every column, and raises when the rows are not `totalCount`, the status is not 200 or the answer has no data.

## OMSGuru — `portals/omsguru.py`, `portals/omsguru_returns.py`

* One session (`OMSGURU_EMAIL/PASSWORD/OTP`), warehouse by warehouse; list pages, order pages,
  search box (AWB / order id). `omsguru_returns.ReturnLookup`: an item counts as received only
  when its order page shows "Return Log RT… (date)". Myntra masters have no SKU, so Myntra
  lookups match the order on its AWBs / store order id.
* An order list line's status carries what became of it (Return Init, Return Received, Cancel Init,
  Cancelled ...), also for channels with no portal client: `portal-sale` reads it by order date
  (`order_lines_range`, some channels, one window per month). The channel filter on the orders page needs a
  warehouse chosen first (`set_warehouse`), or `channel_names` finds no list.
* Reports > **Returns Received** (`/reports/returns_received`): units booked in per channel, at once; its
  Channel Breakup is the range's total whatever "group by" says. Not used: from mid Sep 2026 far fewer units
  are booked in than the paper register shows. Courier / Customer Returns are **queued** (2-10 minutes,
  then a notification): a POST starts a job, not used.

## VMS — `src/ultron/workings/vms/vms.py`

* `fkvms.synlabs.io`: login and the AWBs that have a packing-video scan (VMS bot).

## Couriers — `src/ultron/workings/awb_tracker/`

* BlueDart, Delhivery, Ekart, Shadowfax, Valmo, XpressBees. A courier with no record of an AWB
  is "not found", not an error (Delhivery forgets after ~2–3 months).

## Google Drive — `core/drive.py`

* Service account `ajio-tat-bot@storied-port-441507-k7.iam.gserviceaccount.com` needs Editor on
  each folder / workbook. It can update and create folders but **not create files** ("Service
  Accounts do not have storage quota"): with the Drive owner's OAuth refresh token (`GOOGLE_OAUTH_*`,
  `scripts/google/oauth_token.py`) Drive is used as the owner, who can create files. Uploads are
  resumable.
* `DriveFile.upload()` refuses when the file changed on Drive since it was downloaded. Drive can
  answer a 502 on a master's upload (3 Nov 2026): a 5xx, a rate limit (429, 403 `rateLimitExceeded`),
  a timeout or a dropped connection, also on the token refresh, is tried three times (10 s, 30 s apart).
  Every read through `RetrySession` does this by itself, also for code using a folder's `.http`. A
  write is tried again only by the upload methods: the change check repeats before each try, and this
  run's own content found on Drive means the upload is done (a 502 can still have saved it). A new file
  that a failed try did create is reused, never made twice. Creating a folder is not tried again.
* The bot cannot delete files you own: to drop data it overwrites the file (e.g. header-only CSV).
