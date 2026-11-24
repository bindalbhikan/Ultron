# Return analysis (monthly + yearly) — `python run.py returns`

**When**: on the 10th: 7:00 AM `--request` (Myntra orders + first returns report per account,
Flipkart Sales Report + Returns), 2:00 PM the report. Second try on the 15th with fresh reports:
7:00 AM `--request --fresh` (new reports even where the 10th's exist for the same dates; the 2 PM
run takes the newest), 2:00 PM the report again (owner's rule, 1 Nov 2026). On demand:
`/returns [YYYY-MM]`.

**Windows**: order month = 1st to last day; returns = that month's 1st through the next month's 14th.
The 10th's fresh exports only reach the 9th; the 15th's exports reach the final cutoff. Reusing a
saved month never counts returns after its next 14th, even when run later.
**PORTAL REPORTS**: the month's return report (1st to last day) and, since 16 Nov 2026 (owner: returns of a month's
orders = that month + the next 1st to 14th), the window's tail as the **next month's PARTIAL return report**
(`pr.save_partial`: never over a whole report of that month; the month's own run replaces it later).

**Rules** (19 Nov 2026): the active bot uses `reconciled.py` and Business Reporting's existing
builders on the same saved PORTAL REPORTS snapshots. Order month, return-sheet status, deduplication,
cancellations, RTO and partial-return quantities have one implementation. Myntra's order-report return
flag is no longer used; Flipkart uses order month rather than invoice month. Customer Return Qty must
equal Business Reporting for the same month and source snapshot. The legacy `engine.py` is retained
for rendering the existing workbook layout; its standalone hand-run builders are not used by the bot.
Portals: Myntra MAIN / DBCC / FMCC, AJIO, Flipkart.

Analysis Sales Units = canonical Delivered + Customer Return units, excluding Cancelled, RTO and
In Transit; it is not Business Reporting's Gross Qty. Values use the canonical business sale value
(per unit in the template). Myntra template ORDER ID is now order-line id, Flipkart order-item id,
AJIO customer-order number plus SELLER SKU CODE; a partially returned line can appear twice.

| Input | Source |
|---|---|
| Myntra orders / returns | saved calendar-month order and return reports per account; scheduled refresh still collects reports 4 / 12 |
| AJIO orders / RTV | saved order + RTV reports, with the same monthly/OMSGuru supplements as Business Reporting |
| Flipkart orders / returns | saved Fulfilment Orders + Returns, Sales Reports and the same supplements as Business Reporting; no invoice-month grouping |
| MasterSheet | Drive `AGENT WORK/MASTER SHEET` (MasterData + REMOVED LISTINGS, since 24 Nov 2026; `core/master_sheet.py`) |
| Cost Sheet (optional) | Drive `RETURN ANALYSIS/Supporting` |

**PORTAL REPORTS** (1 Nov 2026): the downloaded reports are also kept in Drive `AGENT WORK/PORTAL
REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/` as `<PORTAL> [<ACCOUNT>] ORDER REPORT <MON-YY>` and `... RETURN
REPORT <MON-YY>`, one calendar month each (`archive_reports`, `core/portal_reports.py`): the order
report only when the 2nd's `portal-reports` run did not save it; the return report = Myntra's first
returns report (the month itself), AJIO RTV and Flipkart Returns cut to the month's rows (`Return
Created Date` / `return_approval_date`, one row per return line). The 15th's return reports replace
the 10th's. Not with `--drive-input` or `--no-upload`. See `docs/bots/portal-reports.md`.

**Output** (Drive `RETURN ANALYSIS`, `RETURN_DRIVE_FOLDER_ID`): `Output/<MON-YY>/`, one report per
portal + MYNTRA COMBINED + ALL PORTAL; `Template/<PORTAL> <MON-YY> TEMPLATE.csv`; Telegram table +
ALL PORTAL workbook. A portal that cannot be fetched, or whose Flipkart returns are incomplete, is
left out and named. An unknown return source is excluded, never shown as zero. `--saved-reports`
(legacy alias `--drive-input`) skips portal refresh and reads PORTAL REPORTS; it no longer reads
hand-dropped Input files. `--no-upload` also reads existing saved reports, generates local outputs
only and does not request fresh portal jobs. A normal scheduled run first archives its fresh returns;
an archive failure excludes that portal rather than silently using older return data.

**Yearly** (`yearly.py`): each monthly run saves every portal's rows (template columns + STATE) to
`Yearly/<YYYY>/<PORTAL> <MON-YY>.csv` and rebuilds `Output/<YYYY>/` (the same 7 workbooks, January
to December; Monthly Summary shows the months). Yearly rendering revalidates the saved months against
the canonical business lines, so old CSV return flags cannot reintroduce mismatches. Missing sources
are named in the yearly notes. `--backfill-year 2026` now reuses archived PORTAL REPORTS, builds its
canonical lines once, and renders closed months without requesting new portal jobs. A portal without
both return reports is excluded; the old live-download backfill's fixed Jan-Jun Flipkart exclusion
does not apply when complete archived sources exist. Each rebuilt month's reports and templates replace
the ones in `Output/<MON-YY>/` and `Template/` (22 Nov 2026), so every month on Drive is the rebuilt one.
Every figure is checked unit for unit against the business report's RAW DATA of the same order month and
account (`reconciled.check_against_business`); one that differs is left out and named, never published.
The analysis bridge keeps only its required columns and reuses each portal's frame across accounts
and yearly months, avoiding repeated copies of payment/history columns.
