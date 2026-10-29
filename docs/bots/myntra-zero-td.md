# Myntra zero TD — `python run.py myntra-zero-td`

**When**: 10 AM, 2 PM and 5 PM IST, Monday to Saturday (`myntra-zero-td.yml`, started by the
worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: `/myntrazerotd`, the 🏷 Zero TD
button on the Myntra menu, or run the workflow. About 1-2 minutes for ~5,900 styles.

* Source: Drive `BINDAL EXPORTS/AGENT WORK/MYNTRA/MYNTRA ZERO TD UPDATE SHEET.xlsx`, one tab per account
  and month (`MAIN-SEP-26`, `DBCC-SEP-26`, `FMCC-SEP-26`; ARTICLE TYPE, BRAND, STYLE ID, MY SKU,
  FINAL SKU, COST, LIQ STYLES). The last tab of each account is read; a new month = a new tab at
  the end. Accounts: `MYNTRA_ZERO_TD_ACCOUNTS` (default MAIN, DBCC, FMCC).
* Each style is looked up on the buyer side, the product API behind `https://www.myntra.com/<style id>`
  (`/gateway/v2/product/<style id>`, a Scrapy spider: `myntra_zero_td/spider.py`). No login: the
  home page first gives the session cookie the API needs (without it: 401).
* Per style, from each size that can be bought now (available, stock > 0): ZERO TD (every size in
  stock sells at MRP), PART ZERO TD (some sizes), DISCOUNTED, OUT OF STOCK, NOT FOUND (404), NOT
  CHECKED (no answer after 3 retries).
* Telegram: one message, per account the styles at MRP and their stock, the 5 with most stock,
  then the workbook: SUMMARY, ALL ACCOUNTS (every account's styles at MRP together, each style
  once: STYLE ID, SKU (FINAL SKU, else MY SKU), SELLING PRICE), a tab per account (its ZERO TD / PART ZERO TD styles: the sheet's
  columns + STATUS, MRP, SELLING PRICE, SIZES AT MRP, STOCK AT MRP, TOTAL STOCK, SELLER, LINK),
  NOT CHECKED when some had no answer.
* Drive: the same workbook in `AGENT WORK/MYNTRA/MYNTRA ZERO TD SHEETS/<OCT-26>/<26-10-26>/ZERO TD 26-10-26 10.00 AM.xlsx`.
* The buyer side shows a style, not an account: a style id on two account tabs shows the same
  result on both.
* Runs on the office PC (self-hosted runner BHIKAN-PC, label `bindal-office`, in
  `C:\Users\Bhikan\actions-runner` with its own venv): www.myntra.com answers GitHub's runners with
  403 (26 Oct 2026). The PC must be on at the run times; a run waits in the queue while the runner
  is off. The runner starts at login only once `start-hidden.vbs` is in the Startup folder.
* Fails (Telegram alert) when myntra.com answered no style at all (blocked, site down); exit 1
  when more than 5% had no answer (the message and sheet still go out).
