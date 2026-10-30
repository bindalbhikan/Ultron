# Myntra SPF master — `python run.py myntra-spf`

**When**: 7:00 AM `--request` (returns 12 + delivery 84 per account), 9:00 AM the master.
On demand: `/myntraspf`.

**Result**: `SPF/MYNTRA/MYNTRA SPF MASTER.xlsx` (`MYNTRA_SPF_FOLDER_ID`), sheets MAIN / DBCC / FMCC
+ SUMMARY / DATE SUMMARY / INPUT LOG; claim aging per SPF POLICY v5 (formulas).

* Rules: the hand-run tool `SPF/MYNTRA/main.py` as `engine.py` (only its folder `MYNTRA_SPF_DIR`
  and an `OMS_RESULTS` hook added). The previous master is the base: rows update, never duplicate.
* Inputs: Myntra returns / delivery (last 30 days) and orders (last 60 days, 30-day jobs) per
  account; **payments of the last `MYNTRA_SPF_PAY_DAYS` (150) per account, downloaded by the bot**
  (`payments.py`, the QUIRY payment export tool's method: every payout + its line CSV; Myntra's
  broken detail links are probed, repaired or replaced by the breakup API); ERP GRN + dispatch;
  from Drive `SPF/MYNTRA/input`: Ticket1 and older payment exports per account (by hand, optional), MANUAL RETURN, LEGACY MASTER, and the courier POD sheet at the input
  root (`MYNTRA RETURN PICKUP POD.xlsx` -> PICKUP POD / RETURN POD / RETURN POD DATE, the last
  columns; refreshed every run, kept as they were when the file is missing).
* **RETURN IN TRANSIT sheet**: every return still in transit (not delivered, not received or
  settled), whatever its age, is on its own sheet of the master: all three accounts, ACCOUNT as the
  last column, same columns and formulas as the account sheets. MAIN / DBCC / FMCC hold the
  delivered / received returns. A row moves to its account sheet on the first run after it is
  delivered or received. SUMMARY / DATE SUMMARY stay one: every figure counts both sheets, plus an
  IN TRANSIT column. Claims, OMSGuru checks and the stats read both (`engine.master_rows`). Until
  30 Oct 2026 only the young ones (< 60 days) were set aside, on the hidden `YOUNG IN TRANSIT`
  sheet (still read once, then gone).
* **SPF tickets from the portal**: every run reads each account's SPF tickets (all statuses,
  `api/spf/v2/getTickets`) as one more ticket report, so TICKET ID / STATUS follow the portal
  without a hand-dropped Ticket1 (a rejection reason from Ticket1 is kept).
* **Claims waiting on our reply** (`AWAITING_SELLER_RESPONSE`, closed by Myntra after 4 days):
  every run reads Myntra's last message and picks a reply as the QUIRY SPF bulk reply tool does
  (label / proof / delivered / working-on-it rules, else a status request); not when we replied
  last. Sent (portal `updateClaim`, as its Edit screen) only with the repo variable
  `MYNTRA_SPF_REPLY=1`; otherwise the Telegram notes list what would be sent.
* **Auto claims** (`tickets.py`), after the first engine run, on the SPF POLICY v5 timelines:
  * *Return Not Received* (`RTS_ORDER_WAS_NEVER_DELIVERED`): delivered to us per Myntra, not
    received; raised 4 to 7 days after the delivery date (`MYNTRA_SPF_RNR_AFTER_DAYS` /
    `_MAX_DAYS`; policy: within 7 days).
  * *In transit* (`RTS_ORDER_WAS_NEVER_DELIVERED`, description "Return Pending"): in transit or no
    return tracking; raised 61 to 120 days after the return / RTO creation date
    (`MYNTRA_SPF_DELAY_AFTER_DAYS` / `_MAX_DAYS`). Until 30 Oct 2026 these were *Delayed Returns*
    (`DELAYED_DELIVERED_RETURN`): Myntra rejected all 906 ("Not_eligible_tat_less_than_120_days"),
    while 83 in-transit returns claimed as Return Not Received were paid / accepted. One claim per
    order line, so the category matters. `MYNTRA_SPF_TRANSIT_CATEGORY=DELAYED` brings the old one back.
  * Only rows with no ticket (master TICKET ID or any portal ticket for the order line - the
    policy allows one claim per order and treats repeats as fraud), a blank FINAL RETURN STATUS
    (OMSGuru received results of this run included), PPMP (not SJIT / FBM) and no courier RETURN
    POD. An account whose portal tickets could not be read gets no claims.
  * Raised like the portal's bulk upload: an xlsx with one `OrderId` column (order line ids, max
    500) put on the claims blob store (`file-manager/getUploadToken/spfJob`), then
    `api/spf/createRnrBulkTickets`. The rows show TICKET ID `BOT JOB <job id>` / STATUS
    `RAISED BY BOT` until the real ticket comes in on the next run.
  * Live only with the repo variable `MYNTRA_SPF_TICKETS=1`; otherwise the report only counts
    the claims due. At most `MYNTRA_SPF_TICKET_MAX` (500) per account and category per run.
* A formula linking another workbook (e.g. `=VLOOKUP(G5,[1]Orders!$E:$F,2,)` pasted into a
  yellow column) reads as empty: written back it made Excel repair the file on every open.
* **Return received**: ERP GRN, then **OMSGuru** (only rows whose FINAL RETURN STATUS is blank,
  created in the last 180 days, matched on AWBs / store order id: "Return Received OMSGuru" or the
  current status), then the manual sheet. The engine runs twice (before and after OMSGuru).
* **Missing ORDER AMOUNT**: the daily order window is 60 days, so older returns had no order
  value (18 Oct: MAIN 4,306, DBCC 1,544, FMCC 177). Each run works out, from the master, the
  calendar months of order reports those returns need (45 days before each return up to it,
  `MYNTRA_SPF_ORDER_LOOKBACK`) and fetches them: a report already on the portal is only
  downloaded; at most `MYNTRA_SPF_OLD_ORDERS_NEW` (1) new one per account per run, asked for after
  the daily reports and waited for only `MYNTRA_SPF_OLD_WAIT_MINUTES` (10); the rest, refusals
  and reports not ready in time are left to the next runs (named in the notes), so they never
  hold up the run (19 Oct: 3 per run with retries and 45-minute waits ran past the 150-minute
  job limit). A value once filled stays in the master.
* **SJIT and FBM orders are not worked** (`NOT_WORKED_MODELS`): their rows stay on the sheets,
  but CLAIM STATUS is always NON ELIGIBLE, OMSGuru does not check them, and the summaries and the
  dashboard leave them out. A row with a blank `model` from a warehouse that is not one of ours
  (ours = the warehouses with PPMP orders: 46148, 24504, 50829, 56765) is marked `FBM` (Myntra
  warehouses 28 / 36 / 81 serve both SJIT and FBM, so the warehouse alone cannot tell).
* 18 Oct: 47,502 to 52,772 rows; GRN 2,011 received; OMSGuru 5,969 checked, 447 received.
  Without SJIT / FBM: MAIN 915 open (was 5,340), 69 eligible (was 435); OMSGuru checks 1,553.

**Later**: raising SPF claims on Myntra (needs captures of the claim form, the ticket export and the
payment download); only no-video claim types, existing-ticket check, caps, dry run first.
