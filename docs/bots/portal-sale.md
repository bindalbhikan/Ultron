# Portal sale report (real sale) — `python run.py portal-sale`

**When**: 5:30 PM daily. On demand: Menu > Reports & MIS > Real sale (portal), `/portalsale`, `/portalsale FROM TO` (a back-fill from saved files).

**Result**: `AGENT WORK/DAILY REPORTING/DAILY SALE REPORT BINDAL/PORTAL SALE REPORT.xlsx`, next to
`SALE REPORT.xlsx` (found through `SALE_DRIVE_FILE_ID`'s folder, no id of its own). The same month sheets
from JUN-26 on, but **every row is an order date**: that day's orders and how many of those same orders
were returned or cancelled, whenever that happened. NET is what really stayed sold. The paper register
plays no part; `SALE REPORT.xlsx` is only read (its layout, its monthly target) and its paper entry goes on
as before.

Sheets after the months: `MONTHLY SUMMARY` (same layout, one row per month, links to each month's Total
row), `SOURCES`, `PAPER CHECK` (month totals beside SALE REPORT's).

**Sources**: one per channel, so RETURN + CANCEL can never exceed GROSS.

| Channel | GROSS | RETURN | CANCEL |
|---|---|---|---|
| MYNTRA (PPMP, MAIN + DBCC + FMCC), SJIT (FBM / SJIT lines) | `Seller_Orders_Report` by created on | an RTO or a return creation date | status F |
| AJIO B2C | Dropship order report by order date | RTV lines of those customer orders, without cancelled pickups | Cancelled Qty |
| FLIPKART, FBF | Flipkart Orders by order date (latest days: see below) | RETURNED, RETURN_REQUESTED | CANCELLED |
| AZ/FX/FBA, COCOBLU, MEESHO, NYKAA | OMSGuru order list by order date | Return Init, Return Received, Partial Return Received | Cancelled, Cancelled Before Shipping, Cancel Init, Cancelled Return Received, Partial Cancelled Return Received |

A line of any other status is still sold (Delivered, In Transit, Flipkart's REJECTED / UNDELIVERED ...).

**Nothing is fetched twice**
* Back-fill: only PORTAL REPORTS month files; a month without a complete Myntra or AJIO file is read
  from the job on the portal / AJIO's direct download; Flipkart uses PARTIAL files up to their last day.
* Daily: the last 60 days. Myntra: the order jobs `myntra-spf` asks for every morning (`_windows`), only
  downloaded. AJIO and OMSGuru answer at once. **Flipkart is the one new request**: no other working fetches
  its Orders report, so it is asked for once a day with a `PORTAL_SALE_FLIPKART_WAIT` (30) minute wait
  (15 minutes on 3 Nov 2026 for 60 days).
* Flipkart's latest days: the Orders report runs about two days behind (asked on the evening of 3 Nov 2026
  it stopped at 1 Nov; on the evening of 1 Nov, at 30 Oct). In the daily run the days after its last one come
  from OMSGuru's order list (FLIPKART: GROSS, RETURN, CANCEL) and Seller Hub metrics (FBF: GROSS and CANCEL,
  RETURN stays empty), each named on Telegram, and the next run overwrites them once the report reaches
  them. A day with no units there stays empty. A back-fill does not do this.

**Reading the numbers**
* Recent days are not final: returns keep coming for weeks. Older than 60 days a cell stays as last
  written; a month's file is as of the day it was saved (Jun-Sep 2026: 1 Nov 2026), so a back-fill with a
  newer file raises it a little.
* Differences from `SALE REPORT.xlsx`: the portal's order files hold more GROSS than it does for Jun and
  Jul 2026 (Myntra about 10 %) and for FBF in Sep 2026 (708 against 294). Its `JUN-26` sheet has July's dates
  in column A (found 2 Nov 2026), so anything reading that sheet by date finds nothing.

**Failures**: all three Myntra accounts or none. A source that fails or stops short (Flipkart's Orders
report, when the latest-days sources fail too) leaves its cells as they are and is named on Telegram. Never shown as 0.
