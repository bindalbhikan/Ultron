# Myntra VMS — `python run.py vms`

**When**: 5:30 PM daily. On demand: `/vms`, `/vms FROM TO`, `/vms erp`, `/vmspic [YYYY-MM]`.

**Result**: `AGENT WORK/DAILY REPORTING/VMS/MYNTRA ORDER ID WISE VMS.xlsx` (`VMS_DRIVE_FILE_ID`).

* Per SLA date and Myntra channel (`MYNTRA_CHANNELS`): ORDER COUNT = orders with an AWB, VMS COUNT =
  those whose Myntra AWB has a packing scan in VMS (`fkvms.synlabs.io`). For Shadowfax / Delhivery
  orders OMSGuru shows the courier AWB; the Myntra number is decoded from the shipping label barcode.
* **ERP vs VMS**: parcels packed in the ERP (report 62, portal MYNTRA: its Order ID is the Myntra
  tracking number) yesterday and today, with / without a VMS scan, per channel: sheets
  `ERP VS VMS MON-YY` and `ERP NO VMS` (who packed it). Only those two days are replaced. It uses no
  SLA date. The two parts do not stop each other: if the ERP part fails the VMS report still goes out
  with a note; if the SLA-date part fails, ERP vs VMS still goes out with a note, the month sheet stays
  as it was and the run counts as failed.
* The order list's SLA Date column is found by its header (OMSGuru added `Channel Push` before it on
  5 Nov 2026). No such header on a list with rows stops the read instead of showing every SLA as empty.
