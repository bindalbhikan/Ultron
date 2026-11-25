# Myntra zero TD — `python run.py myntra-zero-td`

**When**: every 2 hours from 7 AM to 7 PM IST (7, 9, 11 AM, 1, 3, 5, 7 PM), Monday to Saturday, plus one fixed run every day (Sunday too) at 10 AM (`myntra-zero-td.yml`, started by the
worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: `/myntrazerotd`, the 🏷 Zero TD
button on the Myntra menu, or run the workflow. About 1 minute for ~3,500 styles.

* Styles: the owner's sheet, Drive `AGENT WORK/MYNTRA/MYNTRA ZERO TD SHEETS/MYNTRA ZERO TD UPDATE SHEET.xlsx` (moved
  there 25 Nov 2026; `AGENT WORK/MYNTRA` still read when it is not there), one tab per account (`MAIN`, `DBCC`, `FMCC`,
  or `MAIN-SEP-26` ...; ARTICLE TYPE, BRAND, STYLE ID, MY SKU, FINAL SKU, COST, LIQ STYLES), the last tab of each
  account read. Accounts: `MYNTRA_ZERO_TD_ACCOUNTS` (default every account of `portals/myntra.py`).
* **Brand / SKU from the MasterSheet** (owner, 25 Nov 2026: the one SKU master, `AGENT WORK/MASTER SHEET/MasterSheet.xlsx`,
  MASTER DATA only): BRAND, MY SKU and FINAL SKU (= MASTER STYLE CODE) by MYNTRA STYLE ID, the sheet's own value only
  where the master has none. An account with no tab (EXIM) is checked for every Myntra style the master has for it.
  The MasterSheet not readable: the sheet's values, named on Telegram.
* **Each style checked once** (owner, 25 Nov 2026): the accounts' styles are merged and a style id on two or three tabs
  is checked once, under the first account (MAIN, DBCC, FMCC, EXIM) that has it; ACCOUNTS names every account that has
  it. 25 Nov 2026: 4,665 rows, 3,480 styles (1,185 duplicates no longer checked again).
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
* **MYNTRA ZERO TD MASTER** (owner, 25 Nov 2026; `myntra_zero_td/history.py`), `MYNTRA ZERO TD SHEETS/MYNTRA ZERO TD
  MASTER.xlsx`, every check added, written anew (Drive keeps the old versions): STYLE SUMMARY (one row per style: ACCOUNTS,
  BRAND, SKU, TIMES AT MRP, ZERO TD / PART ZERO TD TIMES, DAYS, FIRST / LAST AT MRP, LAST STATUS, MAX STOCK AT MRP, DATES,
  times per month), DAY WISE (style + day: TIMES, CHECK TIMES), MONTH WISE (month + account: styles, times, checks run),
  RUNS (every check), LOG (every style at MRP of every check). With no master on Drive it is built from every saved
  check first (25 Nov 2026: 193 checks since 26 Oct, about 6 minutes, once); `--rebuild-master` builds it again. The
  Telegram list names a style's times this month ("15x in Nov"). Not updated: named on Telegram, the check still goes out.
* The buyer side shows a style, not an account: a style id on two account tabs shows the same
  result on both.
* Runs on the office PC (self-hosted runner BHIKAN-PC, label `bindal-office`, in
  `C:\Users\Bhikan\actions-runner` with its own venv): www.myntra.com answers GitHub's runners with
  403 (26 Oct 2026). The PC must be on at the run times; a run waits in the queue while the runner
  is off. The runner starts at login only once `start-hidden.vbs` is in the Startup folder.
* **Office PC off -> the ULTRON app's Agent mode**: before each run the worker asks GitHub whether the office runner
  is online; if not it starts the run with `runner=cloud` (GitHub's runner) and the style lookups go to
  the ULTRON app (`apps/ultron_app`, Agent mode on), which checks them on the phone's mobile line
  (`core/phone.py`, worker `/api/phone/*`). Any run that gets 403 for most styles hands them to the
  phone too; `MYNTRA_ZERO_TD_VIA=phone` always does. The phone has `MYNTRA_ZERO_TD_PHONE_MINUTES`
  (40) to reconnect and answer within one shared budget. A stale heartbeat no longer fails immediately:
  the bot polls until the phone returns, then queues the work with the time remaining. If the phone
  stays offline, no job is queued and the run names the missing phone; results are never fabricated.
  Styles the phone could not answer (its line dropped: `UnknownHostException`, or HTTP 403) are asked
  for again, up to `MYNTRA_ZERO_TD_PHONE_RETRIES` (2) times after a 1 / 2 minute pause (since 16 Nov 2026).
  These retries also share the original phone lookup deadline; they never restart another 40-minute
  wait beyond the workflow's 45-minute limit. Exhausted retries preserve any answers already received.
* Fails (Telegram alert) when myntra.com answered no style at all (blocked, site down); exit 1
  when more than 5% had no answer (the message and sheet still go out).
