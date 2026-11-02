# Myntra colour grouping — `python run.py myntra-grouping`

**When**: every 3 days (the 1st, 4th, 7th ... 28th), 12 PM IST (`myntra-grouping.yml`, started by the
worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: `/grouping` or run the workflow.
Runs on the office PC (myntra.com refuses GitHub's runners); when its runner is offline the worker
starts it with `runner=cloud` and the styles are looked up by Ultron Phone (the same website API
`www.myntra.com/gateway/v2/product/<style>` from a mobile line; the app sends the colour group since
2 Nov 2026 - an older app makes the run stop with "update the app").

* The owner's grouping checker (LISTING/MYNTRA/Grouping2/main.py) taken over unchanged as
  `myntra_grouping/engine.py`, with two changes (2 Nov 2026): a style in no colour group is NOT DONE (no
  separate NOT GROUPED), and the one-existing-group rule of the upload files below.
* Inputs: Drive `AGENT WORK/MYNTRA/LISTING GROUPING/GROUPING SHEET.xlsx` (kept by the owner: one tab
  per category, column A = MY SKUs, a blank row between groups) and `portal template.xlsx`; the
  newest listings report of each account (`MYNTRA DAILY REPORTS`, myntra-reports); MasterSheet
  (`BUSINESS REPORTING`); sales = order lines delivered (C) or on the way (SH) in the last 3 months'
  order reports (`PORTAL REPORTS`, `GROUPING_SALE_MONTHS`; HIGH SALES = 20+); INV = OMSGuru's
  inventory of every warehouse per FINAL SKU (left blank, and said so, when OMSGuru cannot be read).
* For every group x brand x article type of every account: each style's live colour group on
  myntra.com, then DONE / NOT DONE / DONE - EXTRA IN PORTAL (remove) / NOT LIVE / NOT LISTED /
  DUPLICATE - NOT IN GROUP / ONLY 1 LISTED / DONE IN OTHER ACCOUNT, with PORTAL GROUP and MISSING IN PORTAL.
* Output in `LISTING GROUPING`: `MYNTRA GROUPING MASTER.xlsx` (one sheet per account + Summary, replaced
  each run), `HISTORY/GROUPING_ACCOUNT_WISE_<date>.xlsx`, and `TEMPLATES/<date>/ACC-<seller id>/` one
  upload file per pending group (Unique ID, Group Type, Style ID; one style per SKU: the one already
  grouped, else Active, else the best seller).
* When myntra.com (and the phone) answer for less than 80% of the styles the report is not written
  (a blocked run would show live groups as not live).
* **Submitting** (`--submit`, by hand; the scheduled run only checks): each pending group's file goes up on its
  account as the portal's Catalog > Style Grouping does (`getUploadToken/cms`, the file to the CMS blob
  store, `diy-cataloguing/style-grouping/bulk-upload/submit`); Myntra then approves it (APPROVAL_PENDING).
  Myntra fails a whole upload holding more than one style that already has a colour group, so a file
  carries the style of the biggest existing group plus the ungrouped ones; a style in another group is
  marked `IN ANOTHER GROUP: UNGROUP FIRST` in REMARK. A style in a job still waiting, and an upload that failed before with the same styles, are not sent again; the failure reason of the job's report is in PORTAL REMARK. Some styles fail although myntra.com shows them in no group (a group the buyer site does not show, seen since Aug 2026): an upload cannot fix those.
* `GROUPING SUBMISSIONS.xlsx` (and the SUBMISSIONS sheet of the master): every job of the portal, by hand
  too, date-wise: date, time, account, unique id, styles, JOB ID, status, counts; each run reads the
  statuses again. The account sheets show SUBMITTED ON, JOB ID, JOB STATUS per style.
