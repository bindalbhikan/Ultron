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
| 2 | [02-uv.md](02-uv.md) | installs and a lock file: **uv** | ✅ 16 Nov 2026 (cloud runners) |
| 3 | [03-pyright.md](03-pyright.md) | type check: **pyright** | ✅ 16 Nov 2026 core (workings next) |
| 4 | [04-tenacity.md](04-tenacity.md) | one retry helper: **tenacity** (hand-written loops out) | ✅ 16 Nov 2026 |
| 5 | [05-pydantic.md](05-pydantic.md) | portal answers checked: **pydantic v2** | 🔧 Myntra jobs, payouts, SPF tickets + claims, SRM ledger, Flipkart report centre in |
| 6 | [06-polars.md](06-polars.md) | tables: **Polars** instead of pandas, working by working | 🔧 in; benchmark; first working moved |
| 7 | [07-duckdb-parquet.md](07-duckdb-parquet.md) | months / years of data: **DuckDB + Parquet** | ⏳ |
| 8 | [08-httpx.md](08-httpx.md) | HTTP: **httpx** (curl_cffi kept where a bot check needs it) | ⏳ |
| 9 | [09-selectolax.md](09-selectolax.md) | HTML: **selectolax** instead of BeautifulSoup | ⏳ |
| 10 | [10-small.md](10-small.md) | **orjson**, **pypdfium2** text instead of pypdf, **pydantic-settings** | ⏳ |

Kept as they are (already the top choice, or a hard rule): Patchright (browser, rule), Scrapy (Myntra buyer
site, rule), python-calamine (xlsx read), xlsxwriter (new xlsx), openpyxl (only to edit an existing workbook in
place: dashboards and charts stay), zxing-cpp, Pillow, pypdfium2, cryptography, PyNaCl, google-auth, gspread,
curl_cffi.
