# Flipkart listing file — `python run.py flipkart-listing-file`

**When**: 11:00 AM IST daily (`flipkart-listing-file.yml`, started by the worker's cron, `SCHEDULE`
in `worker/src/worker.js`), after the 8 AM Final TP update. By hand: `/fklisting` on Telegram, the
Flipkart menu button (📄 Listing file), or the workflow. Reads only. Asked by the owner on 14 Nov 2026.

**Result**: `FLIPKART LISTING FILE <DD-MON-YY>.xlsx` in Drive AGENT WORK > FLIPKART > LISTING FILE >
`<Mon-YY>` (a new file each day; the same day again replaces it), and a Telegram message: active /
inactive listings, own stock units, active listings out of stock, the link.

**Columns** (one row per listing, ACTIVE then INACTIVE): Seller SKU Id, Flipkart Serial Number,
Listing ID, Title, Brand, Category, Vertical, Listing Status, MRP, Selling Price, Bank Settlement,
Discount %, Service Profile, Your Stock, Reserved, FBF Stock, Procurement Type, Shipping Days,
Shipping Provider, HSN, Weight / Length / Breadth / Height, Discoverable, Visibility, Live Since,
Deactivation Reason, Product URL.

**Source**: Seller Hub's listing table (`FlipkartClient.listings`, ACTIVE and INACTIVE) and stock call
(`FlipkartClient.stock`), see `docs/PORTALS.md`. Seller Hub's own generated listing file (Listings >
Download) gives a `file_link` whose download path is not known: a netcap capture of one click on
that Download button would let the working save Flipkart's own .xls too. While prices change the
table can return a few listings short: the file is still saved and the message names the shortfall.

**Test of 14 Nov 2026** (local, no upload): 6,388 active + 123 inactive, 104,159 units of own stock,
4,125 active listings out of stock.

The monthly **payment** report is already saved by `portal-reports` (the 2nd: Flipkart
"Settled Transactions" as `FLIPKART PAYMENT REPORT <MON-YY>` in PORTAL REPORTS).
