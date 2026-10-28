# Myntra order + return history — `python run.py myntra-history`

**When**: by hand only (`myntra-history.yml`, inputs `from` / `to` YYYY-MM). The workflow runs
`--step prepare` (Drive folders), then one `--step fetch` job per account x report (matrix, each
its own 6 h), then `--step merge` (merged files + Telegram summary). Locally `--step all` does all three.

* Seller_Orders_Report (4) and Seller_Returns_Report (12) of MAIN, DBCC, FMCC, one report per
  calendar month, into Drive `AGENT WORK/MYNTRA ORDER RETURN REPORTS <FROM> TO <TO>/`:
  `ORDERS/<ACCOUNT>/<ACCOUNT> ORDERS APR-25.csv`, `RETURNS/<ACCOUNT>/...`, and per report one merged
  file of every month and account (`MYNTRA ORDERS ALL ACCOUNTS APR-25 TO SEP-26.csv`, ACCOUNT and
  MONTH columns first; zipped when over 30 MB, the Drive relay's limit).
* A report already on the portal for exactly that month is used; else one is asked for.
* The portal takes the same report of an account once in 16 minutes (refusals read "Internal
  server error"): six lines (account x report) run side by side, each asks for its next month 16
  minutes after the last and downloads what is ready meanwhile. Months are asked for newest first;
  a month refused twice (16 minutes apart, so not the cooldown) is older than the portal keeps, and
  so is every older one: the line stops there and lists them on Telegram (28 Oct 2026: Apr-25 and
  May-25 refused, Jul-25 given; asked oldest first, the first run spent 1.5 h on those refusals).
* Months already in the Drive folder are skipped: a run stopped by GitHub's 6 h limit is run again.
