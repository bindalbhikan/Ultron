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
  minutes after the last and downloads what is ready meanwhile. A month refused 3 times is skipped
  and listed on Telegram (Apr-25 was refused on 28 Oct 2026: older than the portal keeps?).
* Months already in the Drive folder are skipped: a run stopped by GitHub's 6 h limit is run again.
