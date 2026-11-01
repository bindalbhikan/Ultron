# AGENTS.md — read first, every agent, every session

This repo (`bindalbhikan/Ultron`, **public**) is **Ultron · Ecom Manager**: report bots ("workings")
for BINDAL EXPORTS on GitHub Actions, a Cloudflare Telegram worker + dashboard, and the Ultron agent
(`src/ultron/`, seller-neutral, sellable). Any coding agent (Claude Code, Gemini CLI, the "AI fix on failure"
workflow, Codex, Cursor, …) follows this file. `CLAUDE.md` imports it.

<!-- AUTO:synced -->Last synced with the code: 2026-11-01.<!-- /AUTO:synced -->

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
  `myntra_session*.json`, `output/` stay local (ignored).
- **Data must never be wrong**: a failed or incomplete source is left out and named, never shown as 0.
- Seller specifics live in `agent.toml` and `src/ultron/workings/`; `src/ultron/` core never names Bindal.
- Free Cloudflare plan: at most **5 cron triggers** (`worker/wrangler.toml`); each `SCHEDULE` entry in
  `worker/src/worker.js` must use a time the triggers fire at.
- Myntra: never bypass reCAPTCHA, never log out of the portal. AJIO SPF tickets / replies only Wed + Sat.
- Never merge to main by yourself from CI; propose a PR (`ci-fix.yml`).
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

- The repo sits on Google Drive (`G:\My Drive\...`): Drive drops `desktop.ini` files; the local hook
  removes them from `.git` before push / pull / fetch.
- Pull before you start (`git pull`): the Docs sync workflow may have committed on main.
- In bash heredocs `\\n` / `\\b` become real control characters; write regexes with the Edit/Write tools.
- Deploy the worker from `worker/` and the dashboard from `dashboard/` (`npx wrangler deploy`); the
  repo root has no `wrangler.toml`.
- Decrypt a run's log: `python scripts/github/run_output.py <run id>`.
