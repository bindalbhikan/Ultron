# 6. Polars — tables instead of pandas

**Status**: 🔧 17 Nov 2026 — in (`polars>=1.30`, 2.1.0 in `uv.lock`); the business report's logic moved (all three portals).

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

**Where pandas is now**: ~38 files, ~900 calls (business report 6, return analysis 4, AJIO TAT 4, grouping 3,
VMS 2, portal sale 2, Flipkart price 2, one each in the other workings).

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

**Next, one by one, each with a parity test on real files**: the owner's monthly files and
the business report workbook (the last pandas there), return analysis,
Myntra history, then the daily ones. The owners' engines (SPF `engine.py`, grouping engine) only with the
owner's OK. With it: a row-quality check of the OMSGuru order list (fields left at their defaults).
