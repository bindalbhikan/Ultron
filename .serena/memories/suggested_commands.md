# Windows commands
Run from D:\ULTRON unless stated.
- Setup: powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1
- Locked environment: uv sync --all-extras --frozen --managed-python --python 3.12
- Bot help: .venv\Scripts\python run.py <bot> --help; agent CLI: .venv\Scripts\ultron.exe --help.
- Lint: .venv\Scripts\python -m ruff check src tests run.py
- Tests: .venv\Scripts\python -m pytest -q tests (target relevant tests while iterating).
- Types: .venv\Scripts\pyright.exe
- Docs: .venv\Scripts\python scripts\docs\sync_docs.py
- Read encrypted run output: .venv\Scripts\python scripts\github\run_output.py <run-id>; keep decrypted customer data private.
- services/app_api: npm ci --no-audit --no-fund; npm run check; npm test; npm run build. Worker syntax: node --check worker/agent.js from root.
- apps/ultron_app: flutter pub get --enforce-lockfile; dart format --output=none --set-exit-if-changed lib test; flutter analyze; flutter test; flutter build web --release. tool/dev.ps1 supports preview/analyze/test.
- Deployment, only for requested changes: npx wrangler deploy in worker/, dashboard/ or services/app_api/; root has no wrangler configuration.
- PowerShell file ops use Get-Content/Get-ChildItem and literal paths; quote paths with spaces. Search with rg/rg --files.
- Private file backup after changes: powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1 -Backup; never print private file contents.
- Serena memory references: serena memories check (if Serena CLI is available).
