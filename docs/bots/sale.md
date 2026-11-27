# Daily sale — `python run.py sale`

**When**: 3:30 PM daily (report days = **the 1st of the month to yesterday**, `SALE_REPORT_DAYS` = 0 since
14 Nov 2026, owner: a blank or wiped day is written again by the next run; a number = that many days);
the SJIT orders come from the 30-day order report the 9:30 AM `myntra-reports` run asks for (the 7 AM
`--sjit-request` run was dropped on 16 Nov 2026; by hand it only gives a head start, a refusal ends well). On demand: `/sale`, `/sale today`,
`/sale FROM TO`, `/salepic [YYYY-MM]` (sheet picture).

**Result**: `AGENT WORK/DAILY REPORTING/DAILY SALE REPORT BINDAL/SALE REPORT.xlsx` (`SALE_DRIVE_FILE_ID`), one sheet per month
(blocks per channel, rows GROSS / RETURN / Cancel / NET per day), Telegram day + month table.

**Sources**
* New marketplaces in the OMSGuru channel list get their own GROSS, RETURN, Cancel and NET columns before Total, even with no orders yet. Existing marketplace groupings and the Snapdeal exclusion still apply.
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
* `/sale today` (Telegram only): MYNTRA so far today from the **Myntra Seller API** (owner, 23 Nov 2026: the API is
  the main source, OMSGuru the backup): the open lines created today per account (MAIN, DBCC, FMCC, EXIM; token read
  live from OMSGuru, `portals/myntra_api.py`) plus OMSGuru's cancelled units (the API holds no cancelled order;
  GROSS keeps cancellations as always), so the line also shows Myntra's Cancel. An account whose API call fails, or a
  Myntra channel without an API account, counts OMSGuru's GROSS and is named; a difference between the two is named.
  Checked live on 23 Nov 2026: GROSS 118 both ways, Cancel 6. The API holds PPMP orders only, so SJIT is still not in
  today's report (no live source for it).

**Notes**: Since Oct 2026 a COCOBLU block follows AZ/FX/FBA and there is no SNAPDEAL block; older
sheets keep their layout. The run also keeps the DBCC / FMCC Myntra sessions alive and alerts on
Telegram when a Myntra session expired or expires within 3 days.

**Old copy saved over the file** (14 Nov 2026): a copy of the workbook from 7 Nov, open in Excel on
the PC, was saved over the Drive file at 11:16 AM and wiped 7-11 Nov (the bot's runs had written them;
Drive revisions show the ~705 KB Excel saves between the bot's ~673 KB ones). Since then every run
keeps the file as it saved it in `BACKUP/SALE REPORT (last bot save).xlsx` and, before writing, fills
GROSS / RETURN / CANCEL cells that are blank but held a number in that copy (named in the Telegram
notes). Close the workbook in Excel before the 3:30 PM run, or save only a freshly opened copy.

