# 6. Polars — tables instead of pandas

**Status**: ✅ 22 Nov 2026 — every working on Polars (`polars>=1.30`, `fastexcel` for `pl.read_excel`); pandas and numpy
are out of `pyproject.toml` and the lock; the bridge of `core/tables.py` (`to_pandas`, `to_polars`, `col`, `clean_id` of
a column) is gone; the old hand-run `scripts/legacy/myntra_build_workbook.py` removed.

**Why**: faster than pandas, multi-core, lazy queries, strict types (ids stay text: no more `46148.0`). For
Bindal's files the gain is seconds; for a seller with 100x the orders it decides whether a run finishes.

**Benchmark** (16 Nov 2026, the office PC): a real 30-day Myntra orders report (3.6 MB, 6,500 lines), the
sale report's work — read with ids as text, keep a date range, lines and amount per day and status:

| rows | pandas | Polars | |
|---|---|---|---|
| 6,500 (x1) | 0.45 s | 0.07 s | 6x |
| 65,000 (x10) | 2.50 s | 0.14 s | 17x |
| 650,000 (x100) | 21.9 s | 6.6 s | 3x |

The totals were the same both ways at every size. (Python's memory tracer does not see Polars' Rust
allocations, so no memory figure is claimed.)

**Where pandas is now**: nowhere (22 Nov 2026). All 178 modules import without it; tests no longer compare against it
(they hold the expected values the parity runs fixed).

**Shared helpers** (`workings/core/tables.py`): `read_text_csv(bytes)` (every column text), `to_polars(df)` (the
pandas bridge while both live side by side), `pcol(df, name)` (a column by name whatever its case),
`pclean_id(expr)` (no ".0"; nulls stay null).

**Moved**
* Myntra daily reports' return delivery counts (`ppmp_only`, `order_status`, `delivery_split`, `delivery_day`,
  `window_rows`; the 30-day jobs read straight into Polars; the orders' statuses worked out once, not per day).
  Parity on real data before the switch: the 30-day jobs of MAIN, DBCC and FMCC gave the same split for every
  day, old pandas vs new Polars, and with pandas frames given to the new code too (1,705 / 1,308 / 74 deliveries).

* Portal sale counting (`portal_sale/numbers.py`: Myntra, Flipkart and AJIO gross / return / cancel units per
  order day and block). Parity on the real Oct-26 PORTAL REPORTS files before the switch, every (day, block)
  count the same: Myntra MAIN 10,015 / 2,322 / 1,552, DBCC 5,100 / 1,149 / 813, FMCC 254 / 55 / 47, Flipkart
  13,146 / 4,084 / 1,424, AJIO 3,544 gross / 180 cancel / 852 return. The reports are still read by pandas
  (`read_report`): moving the xlsx reading is its own step (number cells must come out as the same text).

* Business report, Myntra (`business_report/myntra.py`: `payments_pl`, `raw_data_pl`, `pay_months_pl`,
  `report_pl`; `build_myntra` uses them, the RAW DATA goes on to the workbook as a pandas table through
  `tables.to_pandas` until the workbook moves too — no pyarrow). Checked with a golden run of the whole business
  report on real Sep–Oct 2026 PORTAL REPORTS files (Myntra 28,611 rows, 38,149 payment lines; Flipkart 19,104;
  AJIO 4,317), every table and cell compared: all the same **except 39 COMMISSION cells, now 1 paisa right**.
  Myntra writes commissions like `13.145000000000001`; pandas' fast text-to-number reader took it as 13.145 and
  rounded to 13.14; Polars reads the text exactly, 13.15. In all 39 cells the new value is the exact reading
  (checked one by one), the old one in none. Rounding is numpy's (`round2`: x × 100, half to even, / 100), as
  before. Dates: the three ISO shapes of these reports, before 2000 (the 1970 of RTO lines) empty, as before.

* Business report, every input file now read by Polars (no `pd.read_excel` / `pd.read_csv` left there):
  `tables.read_excel_text` (python-calamine, Rust; `engine="openpyxl"` for AJIO, whose texts keep outer spaces
  without `xml:space="preserve"` — calamine trims them, pandas kept them) and `tables.read_text_csv(pandas_na=True)`
  (Myntra CSVs). Read the way pandas did: whole numbers without ".0", dates "YYYY-MM-DD HH:MM:SS", pandas'
  missing texts ("NA", "N/A", "NULL", "nan" ...) as missing, empty rows inside kept (row positions matter to
  `bank_paid`), repeated headers ".1". Checked on all 100 sheets of the real Sep–Oct 2026 Flipkart / AJIO files
  (with and without a header row): every cell the same; then the golden business report run: ALL OUTPUTS THE SAME.

* Business report, Flipkart and AJIO logic (`business_report/flipkart.py`: `sales_items`, `monthly_items`,
  `settlement`, `windowed_returns`, `raw_data`, `returned_units`; `business_report/ajio.py`: `windowed_rtv`,
  `credit_notes`, `ledger`, `raw_data` with the G4 / IC shares by invoice, `returned_units`). The old pandas code
  kept beside the new one on the same real files, every column compared: Flipkart Sep–Oct 2026 19,461 rows, AJIO
  4,314 rows, returned units 6,866 / 1,487 — all the same **except one Flipkart item** whose two return lines carry
  the same second: pandas' unstable sort took either line, Polars always takes the later one in the file (its
  RETURN ID and SUB REASON; its status and every number the same). Then the golden business report run: every
  table and number the same. Then the whole range, Apr-25..Oct-26 (Myntra 295,281 rows, Flipkart 182,590 with
  the Sales Reports and monthly files, AJIO 31,126 with its monthly files): Myntra and AJIO every cell the same;
  Flipkart the same but for **6 units now right**: the Returns report holds 26 lines with no return type (return id
  "RI:" only) at the same second as an item's real RTO line, and pandas' unstable sort sometimes took the empty one
  (the item showed Delivered); such a line is now no return (5 RTO, 1 customer return more). Kept as the old code had them (each a pandas habit, checked): an empty invoice number
  is the text "nan" when invoices are shared out (`_text`), Description's title case is Python's own `str.title`,
  a tie in the RAW DATA order keeps the file order.

* Business report, Flipkart's readers and payment months: `read_orders`, `read_returns`, `read_settled`,
  `read_sales` give Polars tables straight to `raw_data` (no pandas bridge on the way), the PAYMENT MONTHS of
  `report()` are summed in Polars, the input log takes Polars tables. Whole-range golden (Apr-25..Oct-26): every
  table and cell the same; one payment-match total differs in the 10th decimal (sum order), the same to the paisa.

* Business report, AJIO's readers: `ajio.read` gives one Polars table (order, RTV and SRM ledger files), and
  `ledger_lines`, `forward_values`, `cancelled_units` work in Polars (handed on as pandas while RAW DATA is pandas).
  Whole-range golden: every AJIO table and cell the same.

* Business report, Myntra's readers: `read_any` gives Polars tables straight to `payments_pl` / `raw_data_pl` (before,
  every file went Polars -> pandas -> Polars, a Python loop over every cell of ~300,000 rows). `_order` (a file's place:
  the later file's return line is the newer) stays a number: through pandas it had become text, so file 10 sorted
  before file 9. Whole-range golden: every Myntra table and cell the same (no line of this data had hit it).

* Business report, the owner's monthly files: Flipkart `read_monthly` / `monthly_settled`, AJIO `read_monthly` /
  `monthly_expenses` in Polars; their hand-typed dates read by `tables.pany_date` (Excel day number, AJIO's text, ISO)
  and sheet names by `tables.sheet_names` (python-calamine), so no `pd.ExcelFile` is left there. A date that cannot be
  read is logged with its count (`tables.unread_dates`): 2 lines in all (Oct-25, Nov-25 Flipkart, typed "00:00:00"),
  without a date before and after. Whole-range golden: every table and cell the same.

* Smaller workings, 17 Nov 2026, each checked old vs new on real data: stock totals (a line with no SKU left out:
  pandas kept it under NaN, read by no SKU); the SPF master's ERP files (xlsxwriter through `core/xlsx.py`, every cell
  of 30,349 GRN and 77,951 dispatch rows the same); Myntra `cut_orders` (the same table, MAIN / DBCC, three windows);
  the return delivery back-fill (read as text like the daily run: the same day splits, 3 accounts); the Flipkart
  listing file (no table library: sorted in Python, written by `write_sheets`, which gained autofilter / freeze /
  column widths / links; every cell, link, filter, freeze and width the same on 3,000 edge-case rows); VMS (233 list
  rows, the SLA-day orders, day counts, NO VMS list and ERP channel map the same on saved real pages); Myntra history
  (row counts of 108 files, merged RETURNS 103,076 / ORDERS 279,912 every cell the same); portal sale's report reading
  (every count the same, real May / Sep / Oct-26 files); the agent's `sheet_summary` tool in plain Python (the core
  stays installable on Termux; the same counts).

* More workings, 17 Nov 2026, old vs new on real data: PORTAL REPORTS month slices (AJIO / Flipkart, Sep and Oct 26:
  every cell the same) and the Flipkart returns coverage check (68 cases the same); Flipkart Orders in parts
  (`portal_monthly`: merged lines and the rewritten workbook, Help sheet too, every cell the same); listing health
  (138,734 listings, the four lists and the message the same; equal-stock lines keep the export's order where pandas'
  quicksort left them in none); Myntra TAT (9,150 lines, 1,031 scored, the message the same); ticket follow-up without a
  table library (each value keeps its kind; two full test runs: all 19,952 tickets, every sheet and the message the same;
  column widths 0.7 of a character wider, as xlsxwriter stores widths the way Excel shows them).

* 22 Nov 2026, no pandas left in these three, each old vs new code side by side (`git worktree` of the commit before):
  * **Myntra zero TD** (`myntra_zero_td/pipeline.py`): the sheet read by `pl.read_excel` (calamine, through
    **fastexcel**, now a dependency), the checks joined on STYLE ID, the workbook by xlsxwriter. A test sheet of 4
    tabs (ids as numbers and as text, a repeated id, a word in the id column) and fixed buyer-side answers: every
    row and the Telegram message the same; the order of styles with equal stock at MRP is now the sheet's (pandas'
    quicksort left it in none), and STYLE ID in the link column is a text cell (an id is text; xlsxwriter's link).
  * **Flipkart price** (`flipkart_price/pipeline.py`): targets, the run workbook, the merge of the matrix parts
    and the message: all the same on a test file and two parts.
  * **ERP to OMSGuru returns** (`erp_oms_return/pipeline.py`): the ERP's answer typed once at the edge
    (`report_table`), the sheet's memory, the jobs, the answers and the SUMMARY formulas in Polars. On the real
    sheet (32,313 GRN lines, OMSGuru's answers fixed by the AWB, nothing sent): the workbook every cell, formula
    and format the same, the message the same.

* 22 Nov 2026, the last pandas of these three out (old vs new code on the same saved files, `git worktree`):
  * **Business report, whole** (`business_report/`: pipeline, the three portals, OMSGuru matching, the workbook): RAW
    DATA stays a Polars table from the reports to the last cell; months are `datetime`; the INPUT LOG plain rows.
    Golden on the real Apr-25..Oct-26 PORTAL REPORTS (Myntra 295,281 qty, Flipkart 65,206, AJIO 31,281): every sheet,
    cell, formula and format the same but (a) REASONS: reasons with equal qty now A to Z (pandas' quicksort left them
    in no order), (b) one AJIO PAYMENT cell 0 where pandas' float sum left 1.2e-11. 15.9 min with the downloads before,
    3.5 min now from the same saved files.
  * **Return analysis, whole** (`return_analysis/`: engine, reconciled, yearly, dash): the report rendered from Polars
    by xlsxwriter (no openpyxl), the dead input builders of the hand-run tool removed. Oct-26 from the same saved
    files: the 7 reports every formula, format, merge, freeze and width the same, the 5 template CSVs the same,
    every total the same; the Grand Total row now carries its values (openpyxl wrote formulas without, so a preview
    showed nothing).
  * **Myntra grouping** (`myntra_grouping/`: engine, submit, pipeline): listings, sales, inventory and the
    submissions record in Polars, every workbook written by xlsxwriter and read by calamine (no openpyxl: the master is
    written again, not edited). Offline from the saved 4 Nov 2026 run (portal cache, record of 302 jobs, reasons;
    listings and the grouping sheet made from its report): the rows, the group states, the report, record, reasons,
    master and brand master and all 344 upload files the same.

* 22 Nov 2026, the last ones: **AJIO TAT** and **Flipkart TAT** (one engine, `ajio_tat/`), OMSGuru's `fetch_orders`. The live
  sources read once and kept (OMSGuru order pages, courier tracking, AJIO order report, ERP label prints, the Drive
  masters), then the old and the new code on them at one frozen time (time-machine), nothing sent: AJIO 10,219 orders and
  Flipkart 5,376, every master row, status, the Telegram reports, the scorecard and the dashboard the same; orders with
  the same Order Time now keep a fixed order (pandas' quicksort left them in none); an empty text is an empty cell.

**Was next** (kept for the record): the owner's monthly files and
the business report workbook (the last pandas there), return analysis,
Myntra history, then the daily ones. The owners' engines (SPF `engine.py`, grouping engine) only with the
owner's OK. With it: a row-quality check of the OMSGuru order list (fields left at their defaults).
