# Myntra daily reports — `python run.py myntra-reports`

**When**: 9:30 AM IST daily (`myntra-reports.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`).
Since 16 Nov 2026 (owner) **the one time of day any bot asks Myntra for its daily reports**: the other
workings use these jobs and never ask for the same report again. (Not before ~9 AM: a report asked for at 7 AM
had only 23 of the day's 239 MAIN orders.) By hand: run the workflow (`date` = another day, YYYY-MM-DD).

* **No report file saved** (owner, 16 Nov 2026): the reports are only made on the portal; only the monthly
  reports are saved (`portal-reports`). `AGENT WORK/MYNTRA/MYNTRA DAILY REPORTS/` keeps the days up to 15 Nov 2026.
* **`AGENT WORK/MYNTRA/MYNTRA DAILY RETURN DELIVERY REPORT.xlsx` is kept** (owner): from the 30-day return delivery
  and orders jobs, read in memory, every run writes **every day of the 30 days again** per account (DATE, PORTAL
  MYNTRA MAIN / DBCC / FMCC, CUSTOMER RETURN, RTO, CANCELLED, TOTAL), so a day missed or wrong before is put right.
  Only deliveries to our own PPMP warehouses count (MAIN 46148 / 24504, DBCC 50829, FMCC 56765;
  `MYNTRA_PPMP_WAREHOUSES`; FBM / SJIT returns to Myntra's warehouses 15774, 28, 36, 81, 309 ... are left out); each
  delivery on its `deliver_to_seller_date`; RTO_or_Cancel told apart by the order's status in the orders job
  (F = cancelled, else RTO).
* **Days Myntra's data does not hold yet stay blank, never 0**: the days after the account's last PPMP delivery in
  the report are removed from DATA, named on Telegram (⏳) and filled by a later run once Myntra has them (a day
  before that last one with no delivery, e.g. a Sunday, is a real 0). 16 Nov 2026: Myntra's report held no PPMP
  delivery after 7 Nov (return_created_date up to 2 Nov), so 8-15 Nov, written as 0 before, were made blank.
  Myntra being late is not a run failure; a report not made or the workbook not written is (exit 1).
* **Data gaps stay blank too** (owner, 17 Nov 2026): days of an account that usually has deliveries (10+ a day on
  average: MAIN, DBCC) in a run of 2+ days without one, not closed days, are blank (Myntra's data has not come:
  the warehouse worked 11-15 Nov 2026 while the report held none). Closed days are a real 0:
  `MYNTRA_WAREHOUSE_CLOSED` (YYYY-MM-DD, comma separated; default Diwali 8-10 Nov 2026). FMCC (a few a day) is
  left as it is: it has real empty days.
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
* Telegram: one message: yesterday's return delivery (customer return / RTO / cancelled), per account each report
  made (job id and dates), the workbook link, then the days left blank and any report not made, and why.
* The workbook (`workbook.py`): **DASHBOARD** (formulas over DATA, current when opened) and **DATA**; only DATA's
  rows are rewritten inside the .xlsx, the dashboard's own formatting and charts stay.
* `--backfill-from YYYY-MM-DD` (`--backfill-to`), by hand: DATA rows for older days from report jobs already on
  the portal (a range none covers is asked for), with the same blank rule. Run for 17 Oct - 15 Nov on 16 Nov 2026.
