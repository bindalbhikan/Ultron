# AJIO SPF — `python run.py ajio-spf`

**When**: 9:00 AM daily. Wed + Sat the full run (tickets + replies); the other days
`--master-only` (master updated, nothing posted). On demand: `/ajiospf` (live) or `/ajiospf dry`.

**Result**: `AGENT WORK/SPF CLAIMS/AJIO MASTER.xlsx`, found by name (`core/drive.py` `spf_master`; owner,
24 Nov 2026: the final master is kept only there, `SPF_MASTER_DRIVE_FILE_ID` is no longer used). The hand inputs
stay in Drive `SPF/AJIO` (`SPF_MANUAL_DRIVE_FILE_ID`, `SPF_OMS_DRIVE_FILE_ID`).

1. **Fetch**: AJIO RTV report + SPF tickets, ERP GRN and dispatch, SRM ledger, the manual register
   (Drive).
2. **Build**: the hand-run master script (`master_engine.py`, unchanged). Return received:
   **ERP GRN first** ("Return Received ERP"), **then OMSGuru** for the returns still open (live
   order lookups give a return sheet the script reads), **then the manual register**.
3. **Raise** SPF tickets for returns past a claim threshold (`claims.py`: dispute 5 to 365 days,
   not delivered 60 to 90 days); **follow up** where AJIO answered (`followup.py`, Gemini drafts).
4. **Publish**: master to Drive, actions file + summary to Telegram.

**Sheets** (owner, 24 Nov 2026: **the portal decides the sheet**): RETURN DELIVERED holds only the
returns AJIO marks delivered to us (a Return Delivered Date, 3PL "Return Delivered", or Return Status
RETURN_DELIVERED / RETURN_PROCESSED / CREDIT_NOTE_CREATED; `master_engine.delivered_to_us`); every
other return (in transit, cancelled, no status, received in ERP / OMSGuru or paid all the same) is on
RETURN IN TRANSIT and moves over on the run after AJIO marks it delivered (until 24 Nov 2026 a
received return sat on RETURN DELIVERED). **RETURN MONTH** (a formula column): the delivery month
(Return Delivered Date, else the Delivery Challan Date AGE counts from) for a delivered return, the
Return Created Date month otherwise; SUMMARY's months match on it (until 24 Nov 2026 by created date).
A paid return (G4, Payment Done) is still claimed (`claims.py`); only a received one is not.

`SPF_DRY_RUN=1` (default) lists instead of posting; only an explicit 0 posts. Any failed source turns
the run into a dry run; per-run caps (`MAX_RAISE_PER_RUN`, `MAX_REPLIES_PER_RUN`); a failed "ticket
already exists?" check skips that ticket.

**No ticket on a guess**: nothing is posted to AJIO on a run where a source failed, and that includes the courier pickup check. A few failed OMSGuru lookups do not stop the run: those return orders get no ticket that run (result `skipped (OMSGuru lookup failed)` in the actions file).
