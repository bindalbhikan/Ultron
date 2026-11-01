# Portal reports — `python run.py portal-reports`

**When**: the 2nd of every month, 11 AM IST (`portal-reports.yml`, started by the worker's cron,
`SCHEDULE` in `worker/src/worker.js`). By hand: `/portalreports [YYYY-MM]` or run the workflow
(inputs `month`, `portals` e.g. `MYNTRA,AJIO`, `kinds` e.g. `payment`, `no_upload`).
**Back-fill**: inputs `from` / `to` (YYYY-MM): every month in between, one after the other, Myntra's and AJIO's
return report (Dropship RTV of the month) too; a report with no rows (the portal no longer keeps
that month) is not saved and is listed as "no data".

* Last month's reports, 1st to last day, into Drive `AGENT WORK/PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/`
  (`core/portal_reports.py`). No sub folders: the file name says what it is (owner's rule, 1 Nov 2026):
  `<PORTAL> [<ACCOUNT>] ORDER REPORT <MON-YY>`, `... RETURN REPORT ...`, `... PAYMENT REPORT ...`;
  `PARTIAL` at the end = days are missing (its source had gaps).

| Portal | ORDER REPORT (this run) | PAYMENT REPORT (this run) | RETURN REPORT |
|---|---|---|---|
| Myntra MAIN / DBCC / FMCC | Seller_Orders_Report (4) for exactly the month; a job already on the portal for those dates is reused, else one is asked for | every payout of the month with its line rows (`myntra_spf/payments.py`, the QUIRY export's columns) | the return analysis, 10th / 15th |
| AJIO | Dropship order report | SRM statement of accounts (the AJIO ledger: G4 payments, reversals) | the return analysis (RTV cut to the month) |
| Flipkart | report centre `Orders` (Fulfilment Reports; the owner's monthly order file), and the SALES REPORT: the tax `Sales Report` (every sale / return / cancel event with its invoice value; `Sales Report Archived` for the months moved out of it, 2025) | report centre `Settled Transactions` (Payment Reports: every transaction settled in the month: orders, SPF, TDS, storage, recall) | the return analysis (Returns cut to the month) |

* The parts run side by side; one that fails is named on Telegram (❌) and the others are saved.
  A run again replaces the files. A month that is not over is refused.
* The return analysis keeps this run's order reports (it saves its own only when one is missing; never
  Flipkart's, whose sale file there is the Tax `Sales Report`).
* Back-filled once (1 Nov 2026): Myntra orders + returns Apr-25 to Sep-26 (`myntra-history`
  files), Myntra payments Apr-25 to Sep-26 (the SPF payment files + live downloads, de-duplicated),
  Flipkart orders Feb-26 to Oct-26 and returns Jul-25 to Sep-26 (the owner's files, re-split by
  calendar month).
* The business reporting reads these files (one download serves every working).

* Flipkart's report centre list of every report together answers HTTP 500 since 1 Nov 2026: reports are
  looked up group by group and by name (`FlipkartClient.report_requests`). Old Orders / Returns / Settled
  Transactions months come back empty or refused; 2025 lives only in `Sales Report Archived`.
