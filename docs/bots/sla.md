# SLA warning — `python run.py sla`

**When**: 12 PM and 3 PM IST (`sla.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: run the workflow.

**Result**: a Telegram message only when there is something to do; nothing is written.

* OMSGuru order list, every channel and warehouse, orders of the last `SLA_ORDER_DAYS` (8) order
  days (`order_lines`, shared with the sale and morning reports; each day its own window, a window
  near the list's ~3,000-line limit read in two halves).
* At risk = status New / Pending / Processing / Packed (not ready to ship yet) and the SLA Date
  column today or earlier. Over = SLA already passed; Today = due later today.
* **Myntra from the Seller API** (owner, 23 Nov 2026: the API is the main source, OMSGuru the backup): the lines of
  MAIN, DBCC, FMCC and EXIM come from the API, live, instead of OMSGuru: its WP lines (to pack = OMSGuru's New) with
  Myntra's own pack-by time as the SLA (`myntra_from_api`, `portals/myntra_api.py`, token read live from OMSGuru).
  Checked on 23 Nov 2026: OMSGuru's 285 open Myntra lines were the API's 285 WP lines, every SLA = packByTime, and
  "Ready to ship" = PK; the run that day gave the same warning both ways. An account whose API call fails keeps
  OMSGuru's lines and is named in the message.
* The message: counts per channel (Over / Today), then the orders by channel (order id, status,
  OVER or the SLA time), at most 40 listed.
* 20 Oct 2026, 4 PM: 7,402 order lines read, 1 at risk.
