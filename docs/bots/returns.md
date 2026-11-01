# Return analysis (monthly + yearly) — `python run.py returns`

**When**: on the 10th: 7:00 AM `--request` (Myntra orders + first returns report per account,
Flipkart Sales Report + Returns), 2:00 PM the report. Second try on the 15th with fresh reports:
7:00 AM `--request --fresh` (new reports even where the 10th's exist for the same dates; the 2 PM
run takes the newest), 2:00 PM the report again (owner's rule, 1 Nov 2026). On demand:
`/returns [YYYY-MM]`.

**Windows**: sale = last month 1st to last day; returns = last month 1st to the day before the run
(the 9th on the 10th, the 14th on the 15th).

**Rules**: the hand-run tool `RETURN ANALYSIS/main.py` as `engine.py` (unchanged; SEP-26 output
identical file by file). Portals: Myntra MAIN / DBCC / FMCC, Ajio, Flipkart.

| Input | Source |
|---|---|
| Myntra orders / returns | reports 4 / 12 per account (two returns jobs 15 min apart, or reused) |
| Ajio orders / RTV | dropship order + RTV downloads (31 days each at most) |
| Flipkart sales / returns | Tax `Sales Report` + Fulfilment `Returns` |
| MasterSheet (+ optional Cost Sheet) | Drive `RETURN ANALYSIS/Supporting` |

**PORTAL REPORTS** (1 Nov 2026): the downloaded reports are also kept in Drive `AGENT WORK/PORTAL
REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/Sale Report <Mon-YY>/` and `Return Report <Mon-YY>/`, one calendar
month each (`archive_reports`, `core/portal_reports.py`): the sale report only when the 2nd's
`portal-sales` run did not save it; Myntra's first
returns report (the month itself; the 1st-14th report of this month is next month's); AJIO RTV and
Flipkart Returns cut to the month's rows (`Return Created Date` / `return_approval_date`, one row
per return line); the 15th's return files replace the 10th's. Myntra files carry the account (`MAIN <file>`). Back-filled once: Myntra Apr-25 to
Sep-26 (`myntra-history` files), Flipkart from the owner's files (months with missing days named
`... PARTIAL`). Not with `--drive-input` or `--no-upload`.

**Output** (Drive `RETURN ANALYSIS`, `RETURN_DRIVE_FOLDER_ID`): `Output/<MON-YY>/`, one report per
portal + MYNTRA COMBINED + ALL PORTAL; `Template/<PORTAL> <MON-YY> TEMPLATE.csv`; Telegram table +
ALL PORTAL workbook. A portal that cannot be fetched, or whose Flipkart returns are incomplete, is
left out and named. `--drive-input` uses the Drive `Input/` folder, `--no-upload` is a test run.

**Yearly** (`yearly.py`): each monthly run saves every portal's rows (template columns + STATE) to
`Yearly/<YYYY>/<PORTAL> <MON-YY>.csv` and rebuilds `Output/<YYYY>/` (the same 7 workbooks, January
to December; Monthly Summary shows the months). `--backfill-year 2026` built the year once.
**Flipkart Jan to Jun 2026 are left out** of the yearly: Flipkart's Returns report only holds about
four months, so those months have no returns data (their saved CSVs are emptied).
