# Completion requirements
- Run .venv\Scripts\python -m ruff check src tests run.py before a commit. Run relevant pytest tests; CI baseline is .venv\Scripts\python -m pytest -q tests. Core changes also need .venv\Scripts\pyright.exe.
- services/app_api changes: npm run check and npm test there; node --check worker/agent.js from root for shared worker routes. Flutter changes: format check, flutter analyze, flutter test, flutter build web --release under apps/ultron_app.
- Update affected docs/bots page for behavior/inputs/outputs/columns; APIs -> docs/PORTALS.md or docs/knowledge; new rules/settings -> docs/CONTEXT.md; built/dropped items -> docs/plan.md; cross-agent facts -> AGENTS.md.
- Schedule changes update worker SCHEDULE, wrangler cron triggers, work_schedule TASKS/WORK, bot When line and run.py docstring. New workings follow docs/ARCHITECTURE.md checklist.
- Run .venv\Scripts\python scripts\docs\sync_docs.py; inspect diff/gaps; update agent memory immediately. No edits inside generated AUTO blocks.
- Review git diff for private data and unintended changes. No work left only in local commits/stashes/branches; push authorized code history before leaving a PC. CI fixes propose a PR and never self-merge main.
- Secrets remain local and backed up with setup_pc.ps1 -Backup. Repo variables changed on GitHub also change local .env and its Drive backup.
- Docs/memory-only onboarding does not require production bot runs or portal requests. Serena memories can be validated with serena memories check.
