# Ticket follow-up — `python run.py ticket-followup`

**When**: 8 PM daily (`ticket-followup.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: Menu > Reports & MIS > Ticket follow-up, `/ticketfollowup`, or run the workflow (inputs `dry_run`, `no_upload`).

**Result**, in Drive `AGENT WORK`:
* `TICKET MASTER.xlsx`: every ticket, one row each. Sheets `SUMMARY`, `OPEN`, `ALL`. Columns PORTAL, ACCOUNT, TYPE, TICKET ID, PARTICULAR, ORDER ID, RAISED ON, LAST UPDATE, AGE DAYS, STATUS, OPEN, FOLLOWED UP BY, LAST FOLLOW-UP, CHECKED ON.
* `TICKET FOLLOWUP SHEET.xlsx`: the owner's five columns (DATE, PORTAL, PARTICULAR, TICKET ID, STATUS). Every open ticket, open ones first, oldest first. A ticket on it that closes stays with its new status. **A row added by hand** with a ticket id the portals here do not list (a Seller Support ticket) is kept as written, and counted as open until its STATUS says closed, done or solved.

**Sources**: Myntra SPF tickets of MAIN, DBCC, FMCC (model PPMP); every AJIO Help Center ticket of the last 2 years. Open = Myntra not REJECT / PAYMENT_COMPLETED / CLOSED; AJIO not RESOLVED or closed. A source that fails keeps its last known rows (CHECKED ON shows the day) and is named on Telegram; a ticket a portal stops listing keeps its last row too.

**Who follows up** (one bot per ticket, so nothing gets two replies):

| Tickets | By | How often |
|---|---|---|
| AJIO SPF | `ajio-spf` | only Wed + Sat (hard rule) |
| AJIO pickup not done | `ajio-tat` | every 24 h |
| AJIO other GENERAL | this run | one fixed comment when our last word is `TICKET_FOLLOWUP_HOURS` (22, as the run's time moves a little) old, open tickets only, read open today and again just before the comment (a comment re-opens a resolved ticket), raised in the last `TICKET_OTHER_MAX_DAYS` (90) days (an older one is only listed), at most `TICKET_OTHER_CAP` (10) a run |
| Myntra | nobody yet | listed for a reply by hand: no call to reply on a Myntra ticket is known, and raising a general Seller Support ticket is not known either (needs a browser capture of one done by hand) |
