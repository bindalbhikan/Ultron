# Libraries — best-in-class, one by one

Owner's rule (16 Nov 2026, `AGENTS.md` hard rules): Ultron is sold to sellers far bigger than Bindal, so every
library is the top choice for its job and built for their scale, not the familiar one. Each change has its own
page here and goes in on its own, in this order (most effect first). **A switch never changes a number**: the
old and the new code give the same output on the same input before the old one goes.

Also weighed for every library: the licence (Ultron is sold: no AGPL / GPL, e.g. no PyMuPDF) and whether the
seller-neutral core (`src/ultron/`, not `workings/`) still installs on Android (Termux).

| # | Page | Change | Status |
|---|---|---|---|
| 1 | [01-ruff.md](01-ruff.md) | lint gate for bugs: **ruff** | ✅ 16 Nov 2026 |
| 2 | [02-uv.md](02-uv.md) | installs and a lock file: **uv** | ✅ 16 Nov 2026 cloud runners; 22 Nov 2026 everywhere (PC `.venv`, Lint, installers) |
| 3 | [03-pyright.md](03-pyright.md) | type check: **pyright** | 🔧 16 Nov 2026 core; `workings/` folder by folder next |
| 4 | [04-tenacity.md](04-tenacity.md) | one retry helper: **tenacity** (hand-written loops out) | ✅ 16 Nov 2026 |
| 5 | [05-pydantic.md](05-pydantic.md) | portal answers checked: **pydantic v2** | ✅ 17 Nov 2026 |
| 6 | [06-polars.md](06-polars.md) | tables: **Polars** instead of pandas, working by working | ✅ 22 Nov 2026: every working, pandas and numpy out (**fastexcel** in for `pl.read_excel`) |
| 7 | [07-duckdb-parquet.md](07-duckdb-parquet.md) | months / years of data: **DuckDB + Parquet** | ⏳ |
| 8 | [08-httpx.md](08-httpx.md) | HTTP: **httpx** (curl_cffi kept where a bot check needs it) | ✅ 17 Nov 2026 |
| 9 | [09-selectolax.md](09-selectolax.md) | HTML: **selectolax** instead of BeautifulSoup | ✅ 17 Nov 2026 |
| 10 | [10-small.md](10-small.md) | **orjson**, **pypdfium2** text instead of pypdf, **pydantic-settings** | ✅ 17 Nov 2026 |
| 11 | [11-flutter-frontend.md](11-flutter-frontend.md) | New Flutter frontend: Material UI, Riverpod, GoRouter, Lucide and bundled DM Sans | ✅ frontend dependencies added; live API/native migration pending |
| 12 | [12-url-launcher.md](12-url-launcher.md) | Flutter team url_launcher for desktop update downloads | Added 24 Nov 2026 |
| 13 | [13-pyyaml.md](13-pyyaml.md) | Safe workflow YAML parsing for the shared action registry | Added 25 Nov 2026 |
| 14 | (page with the first move) | xlsx without **openpyxl**: read by python-calamine / `pl.read_excel`, written by **xlsxwriter**, a workbook written anew instead of edited (owner, 22 Nov 2026: only the top libraries, built for big data) | 🔧 done in business report, return analysis, grouping; ~25 files left (SPF engines, AJIO ads, sale / VMS / Myntra reports workbooks, core helpers) |

Kept as they are (already the top choice, or a hard rule): Patchright (browser, rule), Scrapy (Myntra buyer
site, rule), python-calamine and fastexcel (xlsx read), xlsxwriter (xlsx write), zxing-cpp, Pillow, pypdfium2,
cryptography, PyNaCl, google-auth, gspread, curl_cffi. openpyxl is on its way out (row 14).
