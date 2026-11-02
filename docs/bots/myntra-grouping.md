# Myntra colour grouping — `python run.py myntra-grouping`

**When**: every 3 days (the 1st, 4th, 7th ... 28th), 12 PM IST (`myntra-grouping.yml`, started by the
worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: Menu > Myntra > Colour grouping, `/grouping`, or run the workflow.
**Status only**: 8 PM daily (quiet unless a job changed), or Menu > Myntra > Grouping status, `/grouping status`, input `status_only`: reads the portal's jobs again into `GROUPING SUBMISSIONS.xlsx` and the master's job columns, without asking myntra.com, so GROUPING REMARK stays as of the last full run. Not a separate row in the work schedule sheet (same workflow as the check).
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
  store, `diy-cataloguing/style-grouping/bulk-upload/submit`); Myntra then approves it, usually within hours (status IN_PROGRESS, then COMPLETED, or REJECTED by the approver).
  Myntra fails a whole upload holding more than one style that already has a colour group, so a file
  carries the style of the biggest existing group plus the ungrouped ones; a style in another group is
  marked `IN ANOTHER GROUP: UNGROUP FIRST` in REMARK. Some styles fail although myntra.com shows them in no group (a group the buyer site does not show, seen since Aug 2026): an upload cannot fix those.
* **What is not sent again** (`submit.skip_reason`; only the newest attempt counts, so a failed upload that later went through blocks nothing): a style in a job still waiting; styles all approved in the last 7 days (myntra.com can lag behind the approval: on 2 Nov 2026 only 35 of 143 approved jobs showed fully on the site hours later); the same styles whose newest upload was REJECTED (change the styles first); the same styles whose newest upload failed or partly failed in the last 7 days. Telegram counts each reason.
* `GROUPING SUBMISSIONS.xlsx` (and the SUBMISSIONS sheet of the master): every job of the portal, by hand
  too, date-wise: date, time, account, unique id, styles, JOB ID, status, counts; each run reads the
  statuses again.
* The account sheets show, per group, its **newest** job (any style of the group): SUBMITTED ON, JOB ID, JOB STATUS, PORTAL REMARK (`Remarks` of the job's report, `rejectReason` of a rejected one, by hand uploads too), TRIES (every upload, newest first) and **SUBMIT STATE**:

  | SUBMIT STATE | Means |
  |---|---|
  | DONE | nothing pending on myntra.com, whatever older jobs say |
  | FRESH | pending, never uploaded |
  | WAITING ON MYNTRA | newest job not finished |
  | APPROVED, SITE NOT UPDATED | newest job COMPLETED within 7 days, the site does not show it yet |
  | APPROVED, NOT ON SITE: CHECK | COMPLETED over 7 days ago, the site still does not show it: look at it by hand |
  | PARTIAL / FAILED / REJECTED | the newest job's result; the reason is in PORTAL REMARK |
