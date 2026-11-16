# Myntra daily reports — `python run.py myntra-reports`

**When**: 9:30 AM IST daily (`myntra-reports.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`).
Since 16 Nov 2026 (owner) **the one time of day any bot asks Myntra for its daily reports**: the other
workings use these jobs and never ask for the same report again. (Not before ~9 AM: a report asked for at 7 AM
had only 23 of the day's 239 MAIN orders.) By hand: run the workflow (`date` = another day, YYYY-MM-DD).

* Each Myntra account (MAIN / DBCC / FMCC, `MYNTRA_REPORT_ACCOUNTS`), saved portal sessions:
  Seller_Orders_Report (4), Seller_Returns_Report (12) and Return_Delivery_Report (84) for the 30 days up to
  yesterday (the very jobs the SPF master reads; the day's rows are cut from them: orders by `created on`,
  deliveries by `deliver_to_seller_date`, returns by `return_created_date`, RTO lines by `order_rto_date`),
  Seller_Listings_Report (14) and Seller_Inventory_Report (16), snapshots of today. The inventory report is only
  made on the portal, never downloaded. Different reports are asked for together; a job already on
  the portal for the same dates is reused.
* Who uses these jobs (nobody asks for them again): the SPF master at 10 AM (orders, returns, deliveries
  of the 30 days), the morning report (waits for the orders job, `ask=False`), the daily sale and the
  courier scorecard (`MyntraPortal.reports`: a job covering the days), the portal sale (`covering_job`,
  cut to its days), the colour grouping (today's / yesterday's listings job).
* **Wrong or short data gets a new report** (owner, 16 Nov 2026): an orders job whose data does not reach
  yesterday (`data_stamp`) makes this run ask for orders, returns and deliveries anew in its second round;
  the workings that reuse a job ask for a new one when it holds their days only in part (`MyntraPortal.reports`,
  portal sale) or the listings job has no rows (grouping). A report not got
  (Myntra's "Internal server error while scheduling", a job INTERRUPTED with "cluster is out of
  memory") is asked for again in a second round once the others are in (`MYNTRA_REPORT_ROUNDS`, 2;
  since 16 Nov 2026); the workflow has 100 minutes for that.
* **No files on Drive** since 16 Nov 2026 (owner): the CSVs stay in the run's (encrypted) output only.
  `AGENT WORK/MYNTRA/MYNTRA DAILY REPORTS/` keeps the days up to 15 Nov 2026.
* Telegram: one message, first the total return delivery of all accounts (Return vs RTO), then per account each report's rows (orders: lines, value, cancelled;
  returns / delivery: Return vs RTO; listings: SKUs, active) and the inventory job made. A report not
  got is named at the end.
* `AGENT WORK/MYNTRA/MYNTRA DAILY RETURN DELIVERY REPORT.xlsx`: one row per account and day - DATE, PORTAL
  (MYNTRA MAIN / DBCC / FMCC), CUSTOMER RETURN, RTO, CANCELLED, TOTAL. Only deliveries to our own
  PPMP warehouses count (MAIN 46148 / 24504, DBCC 50829, FMCC 56765; `MYNTRA_PPMP_WAREHOUSES`):
  FBM / SJIT returns to Myntra's warehouses (28, 36, 81 ...) are left out (since 27 Oct 2026; the rows
  from 24 Sep were filled again that way). The delivery report has
  RTO and cancelled as one type (RTO_or_Cancel): the order's status in the 30-day orders report
  tells them apart (F = cancelled, else RTO). A day run again replaces its rows.
* The workbook (`src/ultron/workings/myntra_reports/workbook.py`): **DASHBOARD** (first tab) and **DATA**. The
  dashboard is formulas over DATA's whole columns, so it is current whenever the file is opened:
  C3 = the day shown (latest by default, type a date to see another), tiles (total / customer
  return / RTO / cancelled, share, vs the day before), by portal for the day and month to date,
  the last 14 days, the last 6 months, three charts. Built when the file has no DASHBOARD sheet
  (delete the tab to get it rebuilt by the next run). After that the bot rewrites only DATA's rows inside
  the .xlsx: fonts, sizes, alignment and charts changed by hand on the DASHBOARD stay (openpyxl
  would drop the charts).
* `--backfill-from YYYY-MM-DD` (`--backfill-to YYYY-MM-DD`): fills DATA from that day to the day before yesterday (or that day) from report
  jobs already on the portal (each delivery on its deliver_to_seller_date). Filled from 24 Sep
  2026 (the first day the 30-day delivery report held).
