# Ultron project map
- Public repo bindalbhikan/Ultron; active Windows checkout D:\ULTRON. Old Google Drive checkout is retired because Drive corrupted Git refs. Read AGENTS.md every session; pull before work.
- Seller-neutral agent: src/ultron/{agents,core,host,integrations,portals,tools}; seller-specific workings: src/ultron/workings plus agent.toml. Core must not import workings or name Bindal.
- Workflow path: Cloudflare Telegram worker schedules workflow_dispatch -> GitHub Actions -> scripts/github/ci_run.sh -> run.py <bot> -> portal reads, Drive workbooks, Telegram and dashboard. Public runner output must be encrypted by ci_run.sh.
- Navigation: docs/CONTEXT.md (workings/settings), docs/ARCHITECTURE.md (new working checklist), docs/PORTALS.md (used APIs), docs/knowledge/ (known API capabilities), docs/bots/<bot>.md, docs/plan.md and docs/SCALING.md. Older narrative can lag code; AGENTS.md governs current rules.
- Failed/incomplete sources are excluded and named, never zero. Connected report figures must agree unit for unit from identical saved PORTAL REPORTS; reconciliation failure suppresses publication.
- Outputs use ultron/core/paths.py: OS user data output, overridden by ULTRON_OUTPUT. No customer data, credentials, cookies, tokens, Drive/chat ids in repository or printed logs; netcap is private.
- Memory naming, reference and maintenance rules: `mem:memory_maintenance`.
- Runtime/build choices: `mem:tech_stack`; shared implementation rules: `mem:conventions`; local commands: `mem:suggested_commands`; finish checks/docs: `mem:task_completion`.
- Report orchestration and parity constraints: `mem:workings/core`; Cloudflare service boundaries: `mem:services/core`; Flutter/Android behavior: `mem:app/core`.
