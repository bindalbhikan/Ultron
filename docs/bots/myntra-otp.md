# Myntra courier OTP — `python run.py myntra-otp [--retry]`

**When**: 10 AM IST daily, and again at 11 AM with `--retry` (worker cron, `SCHEDULE` in
`worker/src/worker.js`; `myntra-otp.yml`). By hand: the menu (Myntra > Courier OTP) or `/myntraotp`.

* Reads today's PICKUP and RETURN one-time codes of the TLPL, MMRJ and BOAT warehouses from the
  Myntra partner portal's Orders > OTC page, with the saved portal sessions (worker KV):
  TLPL = MAIN 46148, MMRJ = DBCC 50829, BOAT = FMCC 56765 (`MYNTRA_OTP_SITES`, code:account:warehouse).
* Sends them to Telegram and adds them to the team's "Daily OTP 2026" Google Sheet
  (`MYNTRA_OTP_SHEET_ID`): DATE, PORTAL, COUNT (filled in by hand), OTP, STATUS (PICKUP / RETURN),
  Name (`MYNTRA_OTP_NAME`) and the courier as the team writes it. A code the sheet already has for
  that date, portal and status is not added again. Codes are never written to the log.
* A courier with no trip today has no code ("-"): normal, not an error.
* `--retry` (11 AM): a courier often has no trip yet at 10 AM, so the codes are read again;
  Telegram hears only when there is a code the sheet did not have (or no code of today at all).
* Failures: a logged-out account ("session expired") needs a new login
  (`python scripts/myntra/myntra_session.py`); one account failing does not stop the others.
