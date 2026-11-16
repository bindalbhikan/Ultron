# Myntra daily reports — `python run.py myntra-reports`

**When**: 9:30 AM IST daily (`myntra-reports.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`).
Since 16 Nov 2026 (owner) **the one time of day any bot asks Myntra for its daily reports**: the other
workings use these jobs and never ask for the same report again. (Not before ~9 AM: a report asked for at 7 AM
had only 23 of the day's 239 MAIN orders.) By hand: run the workflow (`date` = another day, YYYY-MM-DD).

* **Only made on the portal, nothing saved** (owner, 16 Nov 2026): no CSV on Drive, no workbook row; only the
  monthly reports are saved (`portal-reports`). `AGENT WORK/MYNTRA/MYNTRA DAILY REPORTS/` and
  `MYNTRA DAILY RETURN DELIVERY REPORT.xlsx` keep the days up to 15 Nov 2026.
* Each Myntra account (MAIN / DBCC / FMCC, `MYNTRA_REPORT_ACCOUNTS`), saved portal sessions:
  Seller_Orders_Report (4), Seller_Returns_Report (12) and Return_Delivery_Report (84) for the 30 days up to
  yesterday (the very jobs the SPF master reads), Seller_Listings_Report (14) and Seller_Inventory_Report (16),
  snapshots of today. Different reports are asked for together; a job already on the portal for the
  same dates (or a snapshot of today) is reused. Each job is waited for until it is done
  (`MYNTRA_REPORT_WAIT_MINUTES`, 40), without downloading it.
* Who uses these jobs (nobody asks for them again): the SPF master at 10 AM (orders, returns, deliveries
  of the 30 days), the morning report (waits for the orders job, `ask=False`), the daily sale and the
  courier scorecard (`MyntraPortal.reports`: a job covering the days), the portal sale (`covering_job`,
  cut to its days), the colour grouping (today's / yesterday's listings job).
* **Wrong or short data gets a new report**: the orders job's data time (`data_stamp`, read in memory, not
  kept) must reach yesterday, else orders, returns and deliveries are asked for anew in the second round;
  the workings that reuse a job ask for a new one when it holds their days only in part (`MyntraPortal.reports`,
  portal sale) or the listings job has no rows (grouping).
* A report refused ("Internal server error while scheduling") or killed (INTERRUPTED, "cluster is out of
  memory") is asked for again in a second round (`MYNTRA_REPORT_ROUNDS`, 2); the workflow has 100 minutes.
* Telegram: one message, per account each report made (job id and dates) and, at the end, any report not made
  and why. Exit 1 when one was not made.
* `--backfill-from YYYY-MM-DD` (`--backfill-to`), by hand only: the old return delivery workbook's DATA rows
  (DATE, PORTAL, CUSTOMER RETURN, RTO, CANCELLED, TOTAL; PPMP warehouses only, `workbook.py`) from report
  jobs already on the portal (each delivery on its deliver_to_seller_date).
