# AJIO dispatch TAT — `python run.py ajio-tat`

**When**: 5:30 PM daily (OMSGuru window = yesterday + today, `TAT_LOOKBACK_DAYS`). On demand:
`/ajiotat [days]`.

**Result**: one master `AJIO_TAT_MASTER.xlsx` in Drive `AGENT WORK/AJIO/Ajio Daily Order Tat Check Working`
(`TAT_DRIVE_FOLDER_ID`, found by name; a missing one is seeded from the old file
`TAT_DRIVE_FILE_ID` and created with the owner's OAuth token). Orders from 2026-06-01 (rebuilt 20 Oct
2026 with `days=141`), plus 26 hand-added late-May orders (`--orders`).

* **10:10 rule**: orders from yesterday 10:00 to today 10:00 must be processed and picked up today
  (before 10:00: due the order date; from 10:00: the next day).
  Processing is on time when ready (RTS) by the END of the due date; the pickup is due by the
  courier's pickup time that day (Promise Ship Date). Until 29 Oct 2026 processing was held to the
  pickup time too, so an order after 10 AM processed the next afternoon read Late.
* OMSGuru order pages (only orders new or still open) + courier tracking for AWBs whose pickup is
  not confirmed: Process / Pickup status, TAT Result (CORRECT / NOT CORRECT / CHECK / PENDING /
  CANCELLED).
* **ERP label print**: `Label Printed` / `ERP Label Time` / `ERP Label By` from ERP report 62
  (portal AJIO; its "Order ID" is the AWB), read from the window start (a week at least); the first
  print counts. 18 Oct: 3,104 of 3,286 orders matched.
* **OMSGuru list limit**: the order list stops at ~3,000 orders (10 pages) whatever the filter, so
  windows are listed 7 days at a time (`LIST_DAYS`), a piece near the limit split in two.
* **AJIO order report** (Seller Central Dropship report, `AJIO_USERNAME`): for orders still missing
  them, `Cust Order No` (AJIO's FN... / EX... number, matched on Order ID = seller order) and
  `Pickup Time` from its "Pickup Timestamp" where courier tracking gave none. Couriers keep no
  history after a few months and OMSGuru logs no pickup; on 1,512 Sep-Oct orders the AJIO time
  equals the courier pickup scan. An order OMSGuru shows In Transit / Delivered / returned with no
  pickup time at all is Picked (Time N/A) -> CHECK.
* **`--orders`** (workflow input `orders`): add hand-picked orders whatever their date - FN / EX
  numbers (via the AJIO report, last 180 days), seller order numbers, invoices or AWBs.
* The saved master is tested as a zip before upload (a local run from G: once uploaded a damaged
  file).
* Telegram: TAT table, then the **courier scorecard**, then pickups pending. The scorecard: per
  courier, orders of the last 7 complete order days (every deadline passed, i.e. up to the day
  before yesterday at the 5:30 PM run), late pickups (after the deadline or still waiting past it),
  on-time % and the last day's %; that day's NOT CORRECT split into our side (processing late) and
  the courier's (pickup late); an alert for a courier under `COURIER_ALERT_PCT` (70) % on time
  `COURIER_ALERT_DAYS` (3) days in a row (days with 5+ orders); 2 lines from the agent's free
  model (left out when it is not available). Pickups pending: a ready-to-copy mail with the AWB
  table when it fits in one message; with more AWBs the mail comes alone and every AWB (courier,
  Over / Due, order time, RTS, deadline) is in the attached `AJIO_pickup_pending_*.xlsx`.
* **Pickup tickets** (on by default, `AJIO_PICKUP_TICKETS`): ONE AJIO "pickup not done" ticket per
  courier (since 27 Oct 2026; 23-26 Oct it was one per order, 317 tickets), every order of that
  courier's pickup pending list (Over and Due alike; `TICKET_ONLY_OVER=1` goes back to orders
  `TICKET_GRACE_HOURS` past the deadline) on its own "Order ID ... - AWB ..." line, when the AJIO
  report and the courier's site show no pickup; the same orders (only Order ID, AWB, Courier) are attached as
  `PICKUP PENDING <COURIER> <dd-mm-yy>.xlsx` (`POST /tickets/<id>/attachments`, multipart "files",
  after the ticket is created; a failed attachment is only logged). `TICKET_BATCH` (50) orders a ticket at most (more =
  "(1/2)", "(2/2)"), `TICKET_CAP` (200) orders a run. Never two tickets for one order: an order with
  any pickup ticket of the last 30 days (one-per-order, or a courier ticket: the next runs read its
  orders back from the description) or a ticket id in the master is not raised again. (27 Oct, the
  first courier run, put 58 orders that had a one-per-order ticket into a courier ticket too; fixed
  the same day.) While some orders of a ticket are still not picked up, the order's latest ticket
  gets one follow-up comment listing them every 24 h. `TICKET_DELAY_MS` (30) between two ticket calls. The master's Pickup Ticket holds every
  pickup ticket id of the order (old one-per-order and courier tickets, comma separated), filled
  from all pickup tickets of the last 30 days on every run.
* **Pickup form** (after the tickets, `pickup_form.py`): AJIO's Microsoft Form "Seller Pickup Issue",
  one response a day per courier whose parcels the courier's site shows not picked up past their
  pickup deadline: Bindal Exports Limited, POB 348890 (last six digits), contact (repo variable
  `AJIO_FORM_CONTACT`), "Pick-up not done", the courier, the date of its oldest such deadline.
  Sent only with `AJIO_PICKUP_FORM=1`, else listed on Telegram as "would send". The couriers sent
  each day are kept in `AJIO_PICKUP_FORMS.json` next to the master (no second form that day).
