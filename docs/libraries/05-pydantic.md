# 5. pydantic v2 — portal answers checked

**Status**: 🔧 16 Nov 2026 — Myntra report jobs checked; the other answers one by one.

**Why**: "data must never be wrong". A portal that renames a field or a column today gives empty or 0
values far down the line (OMSGuru's new SLA column, 5 Nov 2026). A pydantic model per portal answer fails
at once, with the field named. Rust core: fast enough for every row of a big seller. In the `workings` extra
(not the Termux core).

**Done**
* `pyproject.toml`: `pydantic>=2.9` (2.14.3 in `uv.lock`; only pydantic and its own 3 packages added, no other
  version changed).
* Myntra partner portal: every job of `/report/jobs/search` (`MyntraPortal.jobs()`, so `all_jobs`, `ensure`,
  `reports`, the 9:30 AM run, SPF, sale, portal sale, grouping ...) is checked by `checked_jobs()` against
  `ReportJob` — `id`, `reportId`, `status`, `createdOn` (int), `queryParams` (object) required, `successFile` /
  `statusMessage` may be empty, other fields allowed. Checked first on real data: all 4,914 jobs of MAIN, DBCC and
  FMCC fit. A job in another shape raises `PortalChanged` naming the field ("status (missing)"); the jobs are
  returned unchanged, so no working reads anything differently — `tests/test_portal_shapes.py`.

* The models and `check_rows()` live in one place: `workings/core/shapes.py` (`PortalChanged` too).
* Myntra payouts (`payment_history`, the SPF master's and the portal reports' payments): `MyntraPayout` —
  `utrNumber`, `paymentDate` (a date), `amount` (a number), `yearMonth`, `paymentMethod`; all 1,320 payouts of
  the last 400 days of the three accounts fitted.
* Myntra SPF tickets (`spf_tickets`, claims and disputes): `MyntraSpfTicket` — `ticketId`, `orderLineId`,
  `orderId`, `issueCategory`, `status`, `createdOn`, `lastModifiedOn` (`returnId` may be empty); all 18,458
  tickets of the whole history fitted (MAIN 17,215, DBCC 728, FMCC 515). Its page retry moved onto
  `ultron/core/retry.py` too (3 tries, waits 15, 30 s; tested).

* SRM ledger (`Srm.statement`, AJIO SPF and AJIO ads / TOT and the portal reports' AJIO payments):
  `SrmLedgerLine` — every field text, `DOC_DATE` DD.MM.YYYY, `amount` a plain number ("1,234.00" or another
  date shape would stop the run, named); all 17,640 lines of the last 400 days fitted.

* Flipkart report centre (`report_requests`, every monthly / return / sales report): `FlipkartReportRequest` —
  `request_id`, `report_name`, `created_at` (the download name is made of these two), `status`, `filters`;
  all 172 requests listed fitted.

* Myntra SPF claim detail (`spf_claim`, disputes and replies): `MyntraSpfClaim` — `status`, `orderId`,
  `eligibleForTagLoop` required (read with [] by the SPF master), the rest may be empty; 233 claims of every
  status across the three accounts' whole history fitted. No claim from the portal stays `{}`, as before.

**Next (each checked on real answers first)**: AJIO JSON answers. Not pydantic: the OMSGuru order list is HTML the code turns into rows
itself; there the risk is a layout change that leaves fields at their defaults (order "", value 0.0) — a
row-quality check, planned with the Polars move.
