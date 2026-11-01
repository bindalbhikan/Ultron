# Portal sale reports — `python run.py portal-sales`

**When**: the 2nd of every month, 11 AM IST (`portal-sales.yml`, started by the worker's cron,
`SCHEDULE` in `worker/src/worker.js`). By hand: `/portalsales [YYYY-MM]` or run the workflow
(inputs `month`, `portals` e.g. `MYNTRA,FLIPKART`, `no_upload`).

* Last month's sale reports, 1st to last day, into Drive
  `AGENT WORK/PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/Sale Report <Mon-YY>/` (`core/portal_reports.py`):
  * Myntra MAIN / DBCC / FMCC: Seller_Orders_Report (report 4) for exactly the month, saved as
    `<ACCOUNT> <portal file name>`; a job already on the portal for those dates is reused, else one
    is asked for (the owner allowed it, 1 Nov 2026).
  * AJIO: the Dropship order report (`DropShipOrderReports <from> to <to>.xlsx`).
  * Flipkart: the report centre's `Sales Report` of the month.
* The month's return reports follow on the 10th (and the fresh second try on the 15th) from the
  return analysis (`docs/bots/returns.md`); it keeps this run's sale reports.
* The portals are fetched side by side; one that fails is named on Telegram (❌) and the others are
  saved. A run again replaces the files. A month that is not over is refused.
* The business reporting reads these files (one download serves every working).
