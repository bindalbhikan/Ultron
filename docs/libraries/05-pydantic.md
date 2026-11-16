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

**Next, one by one (each checked on real answers first)**: Myntra SPF claims and payments, AJIO orders / RTV,
Flipkart report centre, OMSGuru order list lines (the SLA column case), SRM ledger lines.
