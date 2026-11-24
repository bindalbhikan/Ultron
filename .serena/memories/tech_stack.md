# Stack
- Python >=3.12, setuptools src layout, uv.lock. Windows uses uv-managed Python 3.12 and project .venv, all extras. Execute .venv\Scripts\python; plain uv run drops extras; no pip.
- Tables Polars only; Excel reads calamine via fastexcel/python-calamine; writes xlsxwriter. Do not add pandas or openpyxl in new code even though legacy openpyxl remains declared.
- Shared HTTP httpx, retries tenacity, optional orjson/selectolax, settings/shape validation pydantic and pydantic-settings. Portal-specific dependencies live in workings extras.
- Browser Patchright only through ultron.core.browser, only where no API provides data. Myntra buyer requests use existing Scrapy spiders or existing phone Agent mode exception.
- Cloudflare JS worker + dashboard; TypeScript app API uses Workers, D1, Better Auth and Drizzle; SMS sheet is Google Apps Script. App API npm lockfile controls packages; scripts in services/app_api/package.json.
- Flutter/Dart pins in apps/ultron_app/.flutter-version, README and pubspec.lock; frontend Riverpod and Kotlin Android bridges. Use repository pins, not globally installed defaults.
- Ruff bug rules F/E9/B; line length 130, target py312. Pyright basic checks seller-neutral src/ultron, excludes workings. CI pins are in .github/workflows/lint.yml.
