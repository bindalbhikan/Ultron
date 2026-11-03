# ERP to OMSGuru returns - `python run.py erp-oms-return`

**When**: 8 PM daily (`erp-oms-return.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: Menu > Reports & MIS > ERP to OMS returns, `/erpomsreturn`, or the workflow (input `dry_run`).

**What it does**: every return booked in the ERP's GRN (report 58) that OMSGuru has not accepted is accepted there, as **Good**, through Quick Returns (`accept.py`), with the note `Return accepted in ERP <GRN date>` on the order. An order with no return yet asks the return type: `GRN Customer` = customer, `GRN RTO` and `GRN Cancel` = courier. **Never a Putaway** (owner's rule, 3 Nov 2026): the unit moves from Return Transit to Putaway and OMSGuru's In Stock does not change. Undo one by hand: Revert Return Received on the order.

**Result**: Drive `AGENT WORK/ERP TO OMSGURU RETURN.xlsx`. Sheet `2026`: one row per GRN line: GRN DATE, GRN VOUCHER, PORTAL, OMS CHANNEL, ORDER DATE, SHIPPING LABEL PRINT DATE, ORDER ID, ITEM ID, SUB ORDER ID (not on OMSGuru's order page: empty), FWD AWB, RT AWB, SKU, BARCODE, QTY, ERP STATUS, OMS STATUS, ACTION, NOTE IN OMS, ERP REMARK. Sheet `SUMMARY`: ERP Return, OMS Accepted, Pending by month, then by portal and month, in formulas on sheet `2026`. Telegram: the day's count.

**Not accepted, ACTION says why**: `No ERP ID` (no tracking id or item id in the ERP: it cannot be tied to an order), `Not found in OMS`, `ERP and OMS SKU differ: check` (maybe the wrong item came back), `OMS shows cancelled: check`, `Not accepted: <OMSGuru's answer>`. Every AWB not accepted is tried again the next run.

**Failures**: one order never stops the rest; 40 failures in a row stop the run, it is named on Telegram and the sheet still saved, the next run goes on.

First bulk: 3 Nov 2026, from the owner's PC: 12,110 of 12,122 AWBs.
