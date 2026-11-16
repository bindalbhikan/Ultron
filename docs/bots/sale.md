# Daily sale — `python run.py sale`

**When**: 3:30 PM daily (report days = **the 1st of the month to yesterday**, `SALE_REPORT_DAYS` = 0 since
14 Nov 2026, owner: a blank or wiped day is written again by the next run; a number = that many days);
7:00 AM `--sjit-request` asks Myntra for the SJIT report (only a head start: when Myntra refuses it, the
run logs it and ends well, the 3:30 PM run asks for the report itself; since 16 Nov 2026). On demand: `/sale`, `/sale today`,
`/sale FROM TO`, `/salepic [YYYY-MM]` (sheet picture).

**Result**: `AGENT WORK/DAILY REPORTING/DAILY SALE REPORT BINDAL/SALE REPORT.xlsx` (`SALE_DRIVE_FILE_ID`), one sheet per month
(blocks per channel, rows GROSS / RETURN / Cancel / NET per day), Telegram day + month table.

**Sources**
* OMSGuru: GROSS per channel by order date (required: no orders at all = workbook untouched).
* Flipkart FBF: GROSS + cancel from Seller Hub metrics on Flipkart's own warehouses.
* Myntra SJIT: `Seller_Orders_Report` of MAIN from the partner portal (saved session); reports
  already on the portal are reused, only uncovered days get a new job. po_type SJIT / FBM only;
  GROSS by created on, Cancel = status F by cancelled on. A CSV dropped into the `sjit` Drive
  folder still counts. A report counts only for the days its data holds in full (the newest time in
  any of its date columns, minus one day; Myntra's data copy is renewed only after 7 AM, so the 7:00 AM
  report is usually old): a stale portal report gets a new job at 3:30 PM, and the newest data wins
  per order line. On 5 Nov 2026 a stale report gave 4 Nov 5 SJIT lines instead of 64. A day no report covers stays blank, shows `-` on Telegram, is left out of the totals and is named in the notes; never a 0.
* RETURN is typed by hand and never touched.

**Notes**: Since Oct 2026 a COCOBLU block follows AZ/FX/FBA and there is no SNAPDEAL block; older
sheets keep their layout. The run also keeps the DBCC / FMCC Myntra sessions alive and alerts on
Telegram when a Myntra session expired or expires within 3 days.

**Old copy saved over the file** (14 Nov 2026): a copy of the workbook from 7 Nov, open in Excel on
the PC, was saved over the Drive file at 11:16 AM and wiped 7-11 Nov (the bot's runs had written them;
Drive revisions show the ~705 KB Excel saves between the bot's ~673 KB ones). Since then every run
keeps the file as it saved it in `BACKUP/SALE REPORT (last bot save).xlsx` and, before writing, fills
GROSS / RETURN / CANCEL cells that are blank but held a number in that copy (named in the Telegram
notes). Close the workbook in Excel before the 3:30 PM run, or save only a freshly opened copy.

