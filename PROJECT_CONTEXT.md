# Project context

Updated: 25 Nov 2026.

- Active checkout: D:\ULTRON; the Google Drive checkout is retired. Read AGENTS.md first.
- Ultron: seller-neutral agent core, seller workings, Cloudflare operations worker, app API and Flutter app.
- Current task: centralize app and Telegram controls. The owner authorized permission-checked app chat controls; app identity must come from its claimed D1 job, never Telegram owner privileges.
- In progress: shared generated action registry (agent.toml + workflow declarations), worker/control.js, shared Preview/run/cancel/rerun, model/account controls, approvals, runtime schedules and historical reporting.
- Preview must validate without dispatching or changing anything. Mutating chat requests wait for approval; roles are checked again at execution.
- R2 updates are live. Preserve free-only guards: 2 GB total reservations, 10,000 Class A and 100,000 Class B operations per UTC month; private Standard bucket only.
- Preserve other agents' recent MasterSheet changes. No credentials, customer data or private identifiers in this file.
- Verified: 247 Python tests, 28 app API tests, 38 Flutter tests, Flutter analysis and release web build. Migration 0011 and both services are deployed. Live catalog (34 actions, 18 controls, 68 schedule entries), model service binding, Preview and reporting history reads passed.
- Remaining: push the reviewed change and verify the updated native packages and publication.
- Durable implementation notes: .serena/memories/app/shared_controls.md; product docs: docs/apps/.
