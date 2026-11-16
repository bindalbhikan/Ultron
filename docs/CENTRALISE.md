# Centralise Ultron — one place for what every working repeats

Owner (16 Nov 2026): "Ultron ko centralise karo, bohot sari chize reuse ho sakti hain". Each step moves one kind
of repeated code into one shared place, keeps every working's behaviour exactly, and lands with its tests.
Goes hand in hand with `docs/libraries/` (the shared places are built on the best-in-class libraries).

Rule for every step: the working gives the same output after the move (tests; a working without tests gets one
on a saved input first). The seller-neutral core (`src/ultron/`, not `workings/`) never imports from `workings/`.

| # | What is repeated today | One place | Status |
|---|---|---|---|
| 1 | Portal login boilerplate: OMSGuru `from_env()` + `login()` (~17 workings), AJIO (6), SRM, Flipkart, two Myntra helpers (`return_analysis.sources.myntra_portal`, `sale.myntra_portal`) | `workings/core/clients.py`: `omsguru(warehouse=)`, `ajio()`, `srm()`, `flipkart()`, `myntra(account)`, `myntra_done(portal, account)`; a missing login raises `MissingLogin` naming the secrets | ✅ 16 Nov 2026: 19 OMSGuru users, 11 AJIO / SRM / Flipkart users, `return_analysis.sources` and `portal_monthly` moved (`tests/test_clients.py`). Left on purpose: AJIO TAT and Flipkart TAT build OMSGuru with `workers=`; `sale.myntra_portal` keeps its session-expiry warning (to fold in with step 8) |
| 2 | Retry loops written by hand (30+ files) | `ultron/core/retry.py` on tenacity (`docs/libraries/04-tenacity.md`) | 🔧 OMSGuru `get()` moved |
| 3 | Two Telegram modules (`integrations/telegram.py` for the agent, `workings/core/telegram.py` for the bots: `esc`, `md`, message split, send with retries) | one sender in `integrations/telegram.py`; the bots' module keeps only report rendering (`render`, `send_report`, `write_xlsx`) | ⏳ |
| 4 | Two config modules (`core/config.py`: agent.toml; `workings/core/config.py`: env, num, flag, csv_list, output_dir) | one typed settings object (pydantic-settings, `docs/libraries/10-small.md`) behind the same names | ⏳ |
| 5 | Table helpers copied per working: a column by name whatever its case (`_col`), ids without `.0`, numbers from text (`_num`), the days between two dates (`span`, `_days`), `norm` of SKUs / text, `read_any` | `workings/core/tables.py`, written for Polars with a pandas bridge (`docs/libraries/06-polars.md`) | ⏳ |
| 6 | xlsx writing: header style, widths, freeze, filter, hyperlinks redone in each working (`write_xlsx` x2, zero TD, grouping, AJIO TAT, VMS ...) | `workings/core/xlsx.py` on xlsxwriter: `write_sheets({name: table}, links=, widths=)`; openpyxl only to edit an existing workbook | ⏳ |
| 7 | Drive paths: `DriveFolder(agent_work_id()).subfolder(AREA, create=True).subfolder(...)` in every working | `workings/core/drive.py` `agent_folder("MYNTRA", "LISTING GROUPING")` | ⏳ |
| 8 | Myntra report jobs: ensure / wait / reuse a covering job / cut to days / stale check, spread over daily reports, SPF, sale, portal sale, TAT, grouping | `portals/myntra.py` `ReportJobs` (one API: `get(report, first, last, ask=)`), the 9:30 rule inside it | ⏳ |
| 9 | Run summary on Telegram: "✅ / ⚠️ / ❌ lines, notes, exit 1 when a part failed" built by hand in each `run()` | `workings/core/app.py` `Summary` collected by `run_bot` | ⏳ |

Order: 1 → 2 → 5 → 6 → 7 → 3 → 9 → 8 → 4 (most repeated and lowest risk first; Myntra jobs and settings touch
the most and come when the shared pieces under them are in place).
