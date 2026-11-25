# Myntra SPF master — `python run.py myntra-spf`

**When**: 10:00 AM the master, on the report jobs the 9:30 AM `myntra-reports` run asks for (the 30-day orders,
returns 12 and delivery 84 jobs are the same; since 16 Nov 2026 the 7 AM `--request` run is dropped, by hand only).
The older order window (31-60 days) is still asked for by the master itself.
On demand: `/myntraspf`.

**Result**: `AGENT WORK/SPF CLAIMS/MYNTRA SPF MASTER.xlsx` (PPMP) and, its own file, `MYNTRA SJIT SPF MASTER.xlsx`
(SJIT / FBM, below); the PPMP master found by name (`core/drive.py` `spf_master`; owner,
24 Nov 2026: the final master is kept only there; the hand inputs stay in `SPF/MYNTRA/input`,
`MYNTRA_SPF_FOLDER_ID`), sheets MAIN / DBCC / FMCC
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
* **RETURN IN TRANSIT sheet** (owner, 24 Nov 2026: **the portal decides the sheet**): every return
  the portal has not delivered back to us (no `deliver_to_seller_date`, no "Delivered" in the status;
  received in ERP / OMSGuru, SPF paid or with no portal status all the same), whatever its age, is
  on its own sheet of the master: all three accounts, ACCOUNT as the last column, same columns and
  formulas as the account sheets. MAIN / DBCC / FMCC hold only what the portal marks delivered. A
  row moves to its account sheet on the first run after the portal marks it delivered (until 24 Nov
  2026 a received or settled return went to the account sheet too). **RETURN MONTH**: the delivery
  month on the account sheets, the return / RTO created month on the in-transit sheet (until 24 Nov
  2026 always the created month); the SUMMARY months follow it, DATE SUMMARY stays by created day.
  SUMMARY / DATE SUMMARY stay one: every figure counts both sheets, plus an IN TRANSIT column. Claims, OMSGuru checks and the stats read both (`engine.master_rows`). Until
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
* **Disputes on rejected claims** (owner's rule, 4 Nov 2026: a claim stays alive until the return is
  received or the SPF is paid): a REJECT ticket is disputed when its master row has no FINAL RETURN
  STATUS or only Payment Received (OMSGuru results of this run included), no courier RETURN POD, is a worked order, was not
  replaced by a newer ticket and is untouched for `MYNTRA_SPF_DISPUTE_DAYS` (7). As the portal's Open
  Dispute box: `api/spf/createFwTicket`, reason Others; the claim turns AWAITING_AGENT_RESPONSE. Every
  one due is opened (owner's rule, no cap), none when a source was not read. Live only with the
  repo variable `MYNTRA_SPF_DISPUTE=1`; otherwise the notes count them. The bot never closes a ticket.
  A REJECT claim that already has a dispute (`fwTicketId`, rejected again after it) is not disputed again: the
  portal takes no second one (createFwTicket failed on the same 3 FMCC claims daily until 17 Nov 2026); it is
  named on Telegram for Partner Support and stays alive. Payment history pages are asked again on Myntra's
  own 5xx / timeout (3 tries, waits 15, 30 s; DBCC's page 1 got a 504 on 17 Nov 2026).
  Delayed Returns claims are disputed at any age with `MYNTRA_SPF_DISPUTE_DELAYED=1` (owner's rule, 4 Nov 2026),
  also those rejected as under 120 days, which Myntra may reject again.
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
    policy allows one claim per order and treats repeats as fraud), a FINAL RETURN STATUS that is
    blank or **Payment Received** (`pipeline.resolved`; owner, 24 Nov 2026: an order paid out with no
    return debit yet is still claimed, disputed and checked in OMSGuru, also CLAIM STATUS on the
    sheet; Return Received / SPF Paid / SPF Accepted are never claimed; OMSGuru received results of
    this run included), PPMP (not SJIT / FBM) and no courier RETURN
    POD. An account whose portal tickets could not be read gets no claims.
  * Raised like the portal's bulk upload: an xlsx with one `OrderId` column (order line ids, max
    500) put on the claims blob store (`file-manager/getUploadToken/spfJob`), then
    `api/spf/createRnrBulkTickets`. The rows show TICKET ID `BOT JOB <job id>` / STATUS
    `RAISED BY BOT` until the real ticket comes in on the next run.
  * Live only with the repo variable `MYNTRA_SPF_TICKETS=1`; otherwise the report only counts
    the claims due. At most `MYNTRA_SPF_TICKET_MAX` (500) per account and category per run.
* **SJIT / FBM in-transit claims** (owner, 25 Nov 2026; `tickets.py` `raise_sjit_claims`). Myntra's new SJIT SPF
  tool (Support > Seller Protection Fund > Create New Claim > SJIT; tickets raised through the old ticketing portal
  are not considered after 30 Nov 2026) takes claims per item, by **Fact Core Item ID** = the `core_item_id` of the
  `SJIT_Customer_Returns_Report` (70, `partnerType SJIT`). That report holds the SJIT lines that the Seller Returns
  Report calls `FBM` (MAIN, 1-23 Nov 2026: 429 of them, matched on order line; its PPMP lines carry no core id).
  * Each run asks for report 70 over the in-transit window (returns / RTOs created `MYNTRA_SPF_SJIT_AFTER_DAYS` 61 to
    `MYNTRA_SPF_SJIT_MAX_DAYS` 120 days ago; an RTO's day is `order_rto_date`, its `return_created_date` is
    1970-01-01). The file goes to `<work>/sjit/<account>`, never into the engine's input. A refused request is
    named and skipped, never retried into the run.
  * Not claimed: an item with an SJIT claim (`getTickets?modelType=SJIT`, its `factCoreId` / order line), or whose
    order line has a ticket, is received / settled or has a courier POD on the master. An account whose SJIT claims
    could not be read gets none, and none at all while ERP or OMSGuru was not read.
  * Each candidate is looked up live (`fetchNewClaimSJIT?factCoreId`): claimed only while `itemStatus` is
    `SHIPPED` (out of Myntra's warehouse: the return never came back; `STORED` = back in stock) and no claim is on
    it. A lookup that fails is not claimed. At most `MYNTRA_SPF_SJIT_CHECK_MAX` (1000) lookups per account a run.
  * Raised as the tool's bulk upload: an xlsx with one `FactCoreId` column (max 500) on the claims blob store, then
    `createRnrBulkTickets` with `modelType SJIT`, category `STN_GRN_AT_WAREHOUSE_NOT_SETTLED_NOR_RETURNED` (not
    settled nor returned; `MYNTRA_SPF_SJIT_CATEGORY` may name `INWARD_REJECTIONS_DELAY_IN_RETURNS` or
    `SHORTAGE_IN_RSTN`, the tool's other two), description "Return Pending: ...".
  * Live only with the repo variable `MYNTRA_SPF_SJIT_TICKETS=1` (its own switch: the category is new and a
    rejected claim cannot be raised again; set on 25 Nov 2026, also in the three `.env` copies); otherwise the
    report counts the items due. `MYNTRA_SPF_SJIT_CATEGORY` (repo variable, unset) changes the category. Dry run on MAIN, 25 Nov 2026
    (younger window, only a 1-23 Nov report on hand): 47 of 60 checked still out of stock.
  * The SJIT / FBM rows stay NON ELIGIBLE on the sheets and out of the summaries (below): only the claims are new.
  * **Their own file, laid out like the PPMP master** (owner, 25 Nov 2026: "alag master sheet ... same me mat karo",
    "MYNTRA SPF MASTER iske jaise same chahiye"): `AGENT WORK/SPF CLAIMS/MYNTRA SJIT SPF MASTER.xlsx`
    (`sjit_master.py`), rebuilt after the PPMP master's last engine run, on the previous SJIT master from Drive (made
    by the bot with the owner's OAuth; the bot owns it, an edit on Drive is not kept). Its rows are the PPMP
    master's SJIT / FBM rows, every engine column as there (order amount, settlement, return debit, SPF paid, UTR,
    PODs), with CLAIM STATUS (CLAIM DONE / ELIGIBLE / UPCOMING CLAIM / NON ELIGIBLE), CLAIM TYPE ("SJIT: ..."),
    TICKET ID, CLAIM TAT, STATUS, REJECTION REASON from the SJIT claims, and FACT CORE ITEM ID, MYNTRA STOCK, LAST
    CHECKED, BOT RESULT, BOT JOB at the end; an item of the SJIT returns report the master does not have yet gets a
    short row (kept on later runs). Sheets as in the PPMP master: SUMMARY (account x return month, its columns),
    DATE SUMMARY, CLAIM TAT (the SJIT claims by month), MAIN / DBCC / FMCC (+ an account with SJIT data not in the
    engine's SHEETS), RETURN IN TRANSIT, TICKETS (the SJIT claims, the PPMP TICKETS columns + FACT CORE ITEM ID),
    INPUT LOG (the SJIT returns reports read); yellow headers, SUBTOTAL row, frozen panes and filters as there.
    Figures are values (the PPMP master's are COUNTIFS formulas). An item's core id is learnt from the SJIT returns
    report (only the 61-120 day window each run) and kept from the previous file; older rows have none (BOT
    RESULT "NO FACT CORE ID"). Rebuilt 25 Nov 2026: MAIN 5,667 + DBCC 122 + in transit 226 rows, the same as the
    PPMP master's SJIT / FBM rows; 7 CLAIM DONE (tickets of the old route).
* A formula linking another workbook (e.g. `=VLOOKUP(G5,[1]Orders!$E:$F,2,)` pasted into a
  yellow column) reads as empty: written back it made Excel repair the file on every open.
* **Return received**: ERP GRN, then **OMSGuru** (only rows whose FINAL RETURN STATUS is blank or Payment Received,
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
* **SJIT and FBM orders are not worked on the sheets** (`NOT_WORKED_MODELS`; their in-transit claims: above): their rows stay on the sheets,
  but CLAIM STATUS is always NON ELIGIBLE, OMSGuru does not check them, and the summaries and the
  dashboard leave them out. A row with a blank `model` from a warehouse that is not one of ours
  (ours = the warehouses with PPMP orders: 46148, 24504, 50829, 56765) is marked `FBM` (Myntra
  warehouses 28 / 36 / 81 serve both SJIT and FBM, so the warehouse alone cannot tell).
* 18 Oct: 47,502 to 52,772 rows; GRN 2,011 received; OMSGuru 5,969 checked, 447 received.
  Without SJIT / FBM: MAIN 915 open (was 5,340), 69 eligible (was 435); OMSGuru checks 1,553.

**Later**: SJIT claims on the TICKETS sheet (their claim page call is not captured yet); the SJIT Shortage in
RSTN and Inward Rejections claims (need the RSTN / inward reports matched to what we received).

**No claim on a guess**: when the ERP or OMSGuru could not be read, no SPF claim is raised that run and the report names the source (a received return could look lost). An account whose portal reports failed gets no claim that run, and neither does a return whose OMSGuru lookup failed.
