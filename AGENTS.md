# AGENTS.md — read first, every agent, every session

This repo (`bindalbhikan/Ultron`, **public**) is **Ultron · Ecom Manager**: report bots ("workings")
for BINDAL EXPORTS on GitHub Actions, a Cloudflare Telegram worker + dashboard, and the Ultron agent
(`src/ultron/`, seller-neutral, sellable). Any coding agent (Claude Code, Gemini CLI, the "AI fix on failure"
workflow, Codex, Cursor, …) follows this file. `CLAUDE.md` imports it.

<!-- AUTO:synced -->Last synced with the code: 2026-11-16.<!-- /AUTO:synced -->

## Read next

1. `docs/CONTEXT.md` — the workings (generated table), Drive folders, rules, secrets.
2. `docs/ARCHITECTURE.md` — how it fits together + the checklist for a new working.
3. `docs/PORTALS.md` — every outside system, its API and limits.
4. `docs/bots/<bot>.md` — one page per working (the watcher feeds it to the model on a failure).
5. `docs/plan.md` — what is built and what is still open; `docs/SCALING.md` — the roadmap.
6. `docs/knowledge/` — **Ultron's brain**: every portal API call seen (what it is for, read-only or
   changes something). Look here before saying a portal cannot give some data; the agent reads it
   with its `knowledge_search` / `knowledge_read` tools.

## Hard rules

- **English only** in everything written: code, comments, logs, docs, commits, PRs, Telegram texts.
- **Public repo**: never commit or print logins, cookies, tokens, customer data, Drive/chat ids.
  Bots run through `scripts/github/ci_run.sh` (encrypted output). `.env`, `service_account.json`,
  `myntra_session*.json` stay local (ignored). A run's files never go inside the source code: the output folder is
  the user's data folder (`%LOCALAPPDATA%\Ultron\output` on Windows; `ULTRON_OUTPUT` overrides it, GitHub's runner
  uses the checkout's `output/` that `ci_run.sh` encrypts), `ultron/core/paths.py`.
- **Data must never be wrong**: a failed or incomplete source is left out and named, never shown as 0.
- **Numbers that connect agree** (owner, 22 Nov 2026): when a report shows a figure another report also shows (the
  return analysis' sold / returned units and the business report's Delivered + Customer Return / Customer Return of
  the same order month and account, the dashboards, the yearly files), both come from the same order lines and are
  checked unit for unit before anything is published; a figure that differs is left out and named, never sent
  (`return_analysis/reconciled.check_against_business`). Rebuild reports from the saved PORTAL REPORTS, never from
  newly requested ones, so every report reads the same files.
- Daily Myntra return delivery workbook rows require that account's validated Orders report; a missing or
  stale Orders report leaves its existing rows unchanged, since cancellation/RTO classification needs it.
- Seller specifics live in `agent.toml` and `src/ultron/workings/`; `src/ultron/` core never names Bindal.
- Free Cloudflare plan: at most **5 cron triggers** (`worker/wrangler.toml`); each `SCHEDULE` entry in
  `worker/src/worker.js` must use a time the triggers fire at.
- Myntra: never bypass reCAPTCHA, never log out of the portal. AJIO SPF tickets / replies only Wed + Sat.
- **Browser**: Patchright only, opened through `ultron.core.browser`; add no other browser or
  fallback. Use it only where no API gives the data. A CAPTCHA or bot check is reported, never solved.
- **Myntra buyer site (`www.myntra.com`)**: bots read it with Scrapy spiders only (`myntra_zero_td/spider.py`,
  `myntra_grouping/engine.py`), never a browser or another HTTP client. The one exception is the
  existing phone route (the ULTRON app's Agent mode), for when GitHub's runner gets 403.
- **Myntra SPF tickets**: never close one; a claim stays alive until the return is received or the SPF
  is paid (`docs/bots/myntra-spf.md`, disputes).
- Never merge to main by yourself from CI; propose a PR (`ci-fix.yml`).
- **Best-in-class libraries, built for any seller's scale** (owner, 16 Nov 2026): Ultron is sold to sellers
  far bigger than Bindal, so every library added or kept is the top choice for the job, not the familiar one.
  Tables: **Polars** only (pandas is out of the project since 22 Nov 2026: never add it back); Excel read with
  calamine (`pl.read_excel` through fastexcel, or python-calamine), written with xlsxwriter; no openpyxl in new code
  (owner, 22 Nov 2026: only the top libraries, built for big data and speed): a workbook that changes is read and
  written anew, not edited in place. No workaround either: the proper library way, from the root, even for small data.
  A switch never changes a number: the old and new code give the same output on the same input first.
  One page per library change, in order, with its status: `docs/libraries/` (run `python -m ruff check src tests run.py` before a commit).
- **Centralise, do not copy**: a portal login comes from `workings/core/clients.py`, a retry from
  `ultron/core/retry.py`, an AGENT WORK folder from `agent_folder()`, a new xlsx from `workings/core/xlsx.py`,
  a portal answer is checked in `workings/core/shapes.py`, ids / columns via `workings/core/tables.py`, the Myntra accounts from `portals/myntra.py` `SELLERS` / `ACCOUNTS` (a new account is added there only); what two workings both need goes into one shared place (`docs/CENTRALISE.md`).
- `netcap/` (raw browser captures) is local only: it holds cookies and customer data. Only names
  (paths, field names, meanings) go into `docs/knowledge/`, never values.

## Keep the docs up to date — part of every change, not a follow-up

The owner must never have to check the docs by hand. Every change you make includes its doc update
**in the same commit**:

| You changed | Update |
|---|---|
| a working's behaviour, inputs, outputs, sheet columns | its `docs/bots/<bot>.md` |
| a run time (the Drive reporting sheet rebuilds itself on push) | `worker/src/worker.js` `SCHEDULE` (+ `worker/wrangler.toml` triggers), `TASKS` / `WORK` in `src/ultron/workings/work_schedule/pipeline.py`, the page's `**When**:` line, the `run.py` docstring |
| a new working | everything in the `docs/ARCHITECTURE.md` checklist (page, `run.py`, workflow, `agent-watch.yml` list, `TASKS`, `SCHEDULE`, dashboard tab) |
| a portal / API fact | `docs/PORTALS.md` (a working uses it) or `docs/knowledge/<portal>.md` (not used yet) |
| a new browser capture in `netcap/` | `python scripts/knowledge/learn_netcap.py`, then what the new calls are for in `docs/knowledge/<portal>.md` |
| a rule, Drive folder, secret name | the hand-written sections of `docs/CONTEXT.md` |
| built or dropped a planned item | the status tables of `docs/plan.md` |
| a fact every agent should know | this file |

Then run **`python scripts/docs/sync_docs.py`**: it rewrites the generated blocks
(`<!-- AUTO:… -->`) of `docs/CONTEXT.md` and this file from the code and lists the gaps below.
Do not edit inside those blocks by hand. Safety net: the **Docs sync** workflow
(`.github/workflows/docs-sync.yml`) runs it on every push to main and commits the result, so a
forgotten sync is caught within a minute; the hand-written parts are still yours to update.

## Gaps the sync found (fix them)

<!-- AUTO:gaps -->
- none: every bot has its page and its workflow is watched
<!-- /AUTO:gaps -->

## Working on this machine (owner's Windows PC)

- **Serena**: activate `D:\ULTRON` (project `ULTRON`), not the retired Drive checkout. Onboarding notes live in
  `.serena/memories/`; start with `core`. Commit shared config and reviewed memories; keep caches and
  `project.local.yml` ignored. Back up memories to Drive `AGENT-MEMORY/AGENT-ULTRON-BINDAL/serena/`
  after updating them. See `scripts/local/README.md` for the onboarding checks.

- The ULTRON app: `apps/ultron_app/` (`docs/apps/ultron-app.md`), live on the app API (`services/app_api`,
  username sign-in). The old Kotlin `android app/` was removed on 23 Nov 2026: SMS only and Agent mode live here.
  Owner rules (23 Nov 2026): a signed-in user stays signed in (session in the device key store, 30-day server
  sessions) and never sees the SMS only screen; SMS only is only for a phone with no one signed in, and opens by
  itself when it is on. SMS only and Agent mode keep running in the background (`KeepAlive.kt`).
- **One Worker calling another** (the app API -> the Telegram worker): a service binding (`OPS` in
  `services/app_api/wrangler.jsonc`), never its workers.dev URL: Cloudflare answers that fetch with its own 404
  (error 1042; the app showed "The operations service said 404", 23 Nov 2026).
- Daily OTP sheet (team sheet): the agent's rows show only the phone's user name in the name column, no
  `Agent ·` (owner, 23 Nov 2026); `services/sms_sheet/Code.gs` knows its rows by the note `ULTRON app` on that cell.
- App chat is private per user and read-only: `app_chat_job` in D1, `agent-chat.yml` dispatched with a request
  id only. Never give app chat Telegram's owner action or shared-note write tools; actions use the app's
  separately authorised Workflows and Approvals routes. App replies never go to Telegram.
- Phone jobs share one reconnect/processing deadline: a stale heartbeat is polled within the existing
  wait budget, and work is queued only after the phone reconnects. An offline phone never supplies zero data.

- The project lives at **`D:\ULTRON`**, a normal Git clone off Google Drive (since 22 Nov 2026; the old Drive
  folder `AGENT-ULTRON-BINDAL` is no longer worked in: Drive's `desktop.ini` broke Git refs there).
- **No PC is fixed** (owner, 22 Nov 2026): any PC may be the one in use, and any may be switched off for good,
  so nothing that matters lives only on a PC. Code history on GitHub (**push before leaving a PC**; never leave
  work only in local commits, stashes or branches); `.env`, `service_account.json`, `myntra_session*.json` copied
  to Drive `AGENT-PRIVATE/ULTRON` (`setup_pc.ps1 -Backup`); the coding agents' memory on Drive in
  `AGENT-MEMORY/`. On a new PC: clone to `D:\ULTRON`, run `scripts/local/setup_pc.ps1` (`scripts/local/README.md`).
- Python is **uv**: `.venv` in the project from `uv.lock` (`uv sync --all-extras --frozen --managed-python --python 3.12`,
  done by `setup_pc.ps1`: uv's own Python 3.12 as on GitHub, never the Microsoft Store one, which quietly moves
  `%LOCALAPPDATA%` writes into its package folder); run with `.venv\Scripts\python`. Not plain `uv run` (it drops the extras), no pip.
- Pull before you start (`git pull`): the Docs sync workflow may have committed on main.
- In bash heredocs `\\n` / `\\b` become real control characters; write regexes with the Edit/Write tools.
- Deploy the worker from `worker/`, the dashboard from `dashboard/` and the app API from `services/app_api/`
  (`npx wrangler deploy`); the repo root has no `wrangler.toml`. The SMS sheet's Apps Script (`services/sms_sheet/
  Code.gs`): clasp (`npx @google/clasp`), a new version of the same web app deployment so its URL stays (ids in the
  agent memory, not in this public repo); compare the live code with the repo before pushing.
- **`.env` = GitHub** (owner, 23 Nov 2026: "kabhi manual run karna hua to env hi kaam aayegi"): every repository
  variable has the same value in `.env`, live switches included (`SPF_DRY_RUN`, `MYNTRA_SPF_*`, `AJIO_PICKUP_FORM`), so a
  manual run on a PC acts like the GitHub run; after changing a GitHub variable, change `.env` and its Drive copy
  (`AGENT-PRIVATE/ULTRON`, `setup_pc.ps1 -Backup`). Secrets cannot be read back from GitHub: keep both in step by hand.
- Decrypt a run's log: `python scripts/github/run_output.py <run id>` (ARTIFACT_KEY from `.env`). When GitHub's
  artifact has expired, the same failure log is in Drive `AGENT WORK/AGENT LOGS/<MON-YY>/<dd-mm-yy>/`
  (`<BOT> <time> FAIL #<run id>.log`).
- **Every edit updates the docs and the memory** (owner, 23 Nov 2026): this file and the pages in the same commit,
  `python scripts/docs/sync_docs.py` before it, and the agent memory note right after (not only at the end).
