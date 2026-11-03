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
  each run), `GROUPING REASONS.xlsx`, `HISTORY/GROUPING_ACCOUNT_WISE_<date>.xlsx`, and `TEMPLATES/<date>/ACC-<seller id>/` one
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
* The master's account sheets are in the owner's layout (2 Nov 2026): Unique ID, Group Type, Article Type, Brand, Style ID, SKU, FINAL SKU, GROUPING REMARK, STATUS, INV, SALE, ACTION, PORTAL COLOR, JOB ID, JOB STATUS, JOB SUBMITED DATE, PORTAL REMARK. The job columns are filled only on a style **not grouped yet** (GROUPING REMARK NOT DONE, owner's rule): **that style's own newest job** and that style's line of its report; blank there = never uploaded. Every other row's job columns are blank; all jobs stay in the SUBMISSIONS sheet and `GROUPING REASONS.xlsx`. `HISTORY/` keeps every column of the check (MISSING IN PORTAL, PORTAL GROUP, REMARK with `IN ANOTHER GROUP: UNGROUP FIRST` ...).
* `GROUPING REASONS.xlsx`: every row of every finished job's result report, by hand uploads too (job, date, account, status, unique id, style, REMARK = `SUCCESS` or the reason, group id), newest first. A finished job's report is read once. When the portal could not read the upload's file at all (Aug and Oct 2026: wrong header or cell type), the report holds only its error, kept as one row with no style.
* Telegram counts the pending groups by state, from the group's newest job: FRESH (never uploaded), WAITING ON MYNTRA, APPROVED, SITE NOT UPDATED (completed within 7 days), APPROVED, NOT ON SITE: CHECK (over 7 days ago), PARTIAL, FAILED, REJECTED.
