# ERP to OMSGuru returns - `python run.py erp-oms-return`

**When**: 8 PM daily (`erp-oms-return.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: Menu > Reports & MIS > ERP to OMS returns, `/erpomsreturn`, or the workflow (input `dry_run`).

**What it does**: every return booked in the ERP's GRN (report 58) that OMSGuru has not accepted is accepted there, as **Good**, through Quick Returns (`accept.py`), with the note `Return accepted in ERP <GRN date>` on the order. An order with no return yet asks the return type: `GRN Customer` = customer, `GRN RTO` and `GRN Cancel` = courier. **Never a Putaway** (owner's rule, 3 Nov 2026): the unit moves from Return Transit to Putaway and OMSGuru's In Stock does not change. Undo one by hand: Revert Return Received on the order.

**Result**: Drive `AGENT WORK/ERP TO OMSGURU RETURN.xlsx`. Sheet `2026`: one row per GRN line: GRN DATE, GRN VOUCHER, PORTAL, OMS CHANNEL, ORDER DATE, SHIPPING LABEL PRINT DATE, ORDER ID, ITEM ID, SUB ORDER ID (not on OMSGuru's order page: empty), FWD AWB, RT AWB, SKU, BARCODE, QTY, ERP STATUS, OMS STATUS, ACTION, NOTE IN OMS, ERP REMARK. Sheet `SUMMARY`: ERP Return, OMS Accepted, Pending by month, then by portal and month, in formulas on sheet `2026`. Telegram: the day's count.

**Accepted means**: OMSGuru refused no form and, read back from the order page, an item's status moved to a received one. An AWB that belongs to several orders has all of them read, and each one that moved gets the note. When an AWB opens several forms and only some go through, the SKUs on those forms are marked Accepted and the rest stay pending. ACTION is kept per GRN line (AWB, SKU, voucher): a later GRN line of an AWB already accepted is still worked; lines accepted before are never rewritten.

**Not accepted, ACTION says why**: `No ERP ID` (no tracking id or item id in the ERP: it cannot be tied to an order), `No GRN date, qty or SKU: check` (not tried, QTY left blank, never guessed), `Not found in OMS`, `ERP and OMS SKU differ: check` (maybe the wrong item came back), `ERP qty above sent: check` (more than the form's rows take; nothing sent for that AWB), `OMS shows cancelled: check`, `Not accepted: <OMSGuru's answer>`. Every AWB not accepted is tried again the next run.

**Failures**: one order never stops the rest; 40 failures in a row stop the run, it is named on Telegram and the sheet still saved, the next run goes on.

First bulk: 3 Nov 2026, from the owner's PC: 12,110 of 12,122 AWBs.
