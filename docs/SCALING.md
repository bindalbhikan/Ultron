# Ultron: scaling plan

*Draft, 25 Oct 2026. Limits marked "check" should be confirmed against the provider's current
pricing page before a decision is taken on them.*

"Scaling" here means four different things, in this order of need:

1. **Faster and steadier for Bindal**: answers in seconds, fewer failed runs, no manual fixes.
2. **More volume for Bindal**: more orders, channels, accounts and reports without runs slowing
   down or hitting portal limits.
3. **More sellers**: the same Ultron set up for other sellers, each with their own logins.
4. **A hosted product**: sellers sign up and pay; nobody needs GitHub or Cloudflare skills.

Each phase below can stop the next one from being needed too early. Do them in order.

## 1. Where Ultron stands today

| Part | Today | What limits it |
|---|---|---|
| Telegram bot | one bot, one worker, owner's chats only | Telegram: about 30 messages/s per bot, 1 message/s per chat (check) |
| Worker (Cloudflare, free) | menu, cron schedule, Ultron's routes, KV "DASH" | 5 cron triggers per account; KV free tier about 1,000 writes/day (check); 100k requests/day |
| Reports (GitHub Actions) | one workflow per report, public repo | each run starts cold (~30-60 s: checkout, Python, install); free plan runs about 20 jobs at once (check); GitHub's own `schedule:` can start late |
| Chat answers | worker starts the `agent-chat` workflow | 1-2 minutes per answer, mostly the cold start |
| Model | Workers AI `gpt-oss-120b`, free daily allocation | about 10,000 neurons/day: roughly 15 watcher checks plus some chat (check); too weak for code changes |
| Memory, approvals | one JSON document / keys in KV | every chat turn, note and incident is a KV write; one document grows with every seller |
| Portals | OMSGuru, Myntra (3 accounts), AJIO, Flipkart, ERP, SRM, VMS | OMSGuru list stops near 3,000 rows a window; Myntra refuses the same report twice in 15 minutes and logins last about 30 days |
| Drive | service account + Apps Script relay for new files | Sheets API about 60 requests/min per user (check); the relay is one script |
| Code | `src/ultron` (seller-neutral) + `src/ultron/workings` (Bindal's) | the workings name Bindal's sheets, accounts and channels |

At Bindal's current volume nothing is near a hard limit. The slow chat answer and the free model
are the two things the owner feels.

## 2. Phase 1: faster and steadier for Bindal (weeks 1-3)

| # | Change | Why | Effort |
|---|---|---|---|
| 1.1 | **Chat inside the worker.** Run the agent loop in the worker (JavaScript) for questions that need no Python portal code; keep GitHub Actions for reports and heavy tools | answers in about 10-20 s instead of 1-2 min | medium |
| 1.2 | **Auto-retry known failures.** The watcher re-runs a report once when the cause is a known, harmless one (login drop, portal timeout, cooldown), from `known_issue` notes in memory | fewer alerts, no manual rerun | small |
| 1.3 | **Model fallback chain.** Workers AI first; when the free allocation is used up, a second free / cheap endpoint (`AGENT_LLM_URL`, e.g. Gemini with the existing `GEMINI_API_KEY`); a paid model (Claude) only for hard cases | Ultron never goes silent at the end of the day | small |
| 1.4 | **One scheduler.** Move the GitHub `schedule:` reports into the worker's `SCHEDULE` (one cron trigger lists many hours) | GitHub schedules start late or skip; one place to see every time | small |
| 1.5 | **Health message.** One short morning line: runs yesterday, failed, Myntra logins expiring within 7 days, model budget left | problems seen before the owner asks | small |
| 1.6 | **Pin releases.** Reports run a tagged Ultron release; `main` is for work in progress | a bad push does not break the next morning's reports | small |

**Done when:** chat answers come in under 30 s; a week of reports passes with no manual rerun.

## 3. Phase 2: more volume for Bindal (months 1-2)

| # | Change | Why |
|---|---|---|
| 2.1 | **Local order cache.** Keep OMSGuru order lines in a small database (Cloudflare D1, or SQLite on Drive / a VPS), updated every few hours; reports read the cache instead of paging OMSGuru every time | runs become seconds, OMSGuru's 3,000-row list limit stops mattering, fewer logins |
| 2.2 | **Parallel portal reads** with a per-portal limit (OMSGuru pages, Myntra accounts, couriers) | reports stay fast as orders grow |
| 2.3 | **Batch Drive writes**: one update per sheet per run, not per row | stays inside Sheets API limits |
| 2.4 | **Memory out of a single KV document**: notes and chat turns in D1 rows (or KV keys per chat); KV keeps only small, rarely written values | KV write limit and document size stop being a risk |
| 2.5 | **Persistent runner for heavy reports** (a small VPS or always-on PC with `ultron serve` and a job runner), GitHub Actions as fallback | no cold start; files and logins stay warm |
| 2.6 | **Dashboard from the cache** instead of numbers pushed by each run | always current, fewer KV writes |

**Done when:** orders can double with run times staying the same, and no report pages OMSGuru
more than once a day.

## 4. Phase 3: more sellers (months 2-4)

### 4.1 Make the workings seller-neutral

Everything seller-specific moves into `agent.toml` (or a `seller.toml` next to it):

* Drive file and folder ids, sheet names and layouts
* marketplace accounts (Myntra partner ids, AJIO / Flipkart logins), warehouses, channel names
* which reports are on, their times and thresholds (the repository variables of today)

`src/ultron/workings` then names no seller, the same rule `src/ultron` follows today. Bindal
becomes the first seller set up this way. This is the biggest single piece of work in the plan.

### 4.2 How each new seller runs: start with one repo per seller

| Model | How | For | Against |
|---|---|---|---|
| **A. Repo per seller (start here)** | `ultron init` creates the seller's repo from a template: workflows, `agent.toml`, worker config; the seller's secrets in that repo; Ultron installed from a pinned release | logins and data fully apart; free to run; nothing hosted to look after | each seller needs a GitHub and Cloudflare account; updates go out repo by repo |
| B. One hosted service | one worker + database for all sellers, a job runner for the Python reports, secrets per seller in a vault | one place to update; sign-up without GitHub | someone must run, secure and pay for it all the time |

Model A fits the first 5-10 sellers; Model B (Phase 4) once onboarding by hand becomes the bottleneck.

### 4.3 What a new seller needs (target: set up in under an hour)

1. `ultron init` (asks the seller's name, marketplaces, accounts; writes `agent.toml`).
2. Logins: a guided `ultron login <portal>` for each portal, stored as secrets.
3. `ultron deploy`: workflows pushed, worker deployed, Telegram bot connected.
4. `ultron check`: every login, sheet and tool tested, with a clear list of what is missing.

The SOP's set-up section becomes this tool.

## 5. Phase 4: hosted product (months 4-8)

| Layer | Choice to evaluate |
|---|---|
| Front door | one Telegram bot per seller (seller's own token), or one shared Ultron bot that knows each seller by chat |
| API + scheduling | Cloudflare Workers + Cron + Queues (Queues and higher limits need Workers Paid, about $5/month, check) |
| Data | Cloudflare D1 (per-seller rows: orders cache, memory, approvals, runs); R2 for files |
| Python reports | containers on a job runner (Fly.io / Cloud Run / a VPS pool) pulling jobs from the queue |
| Secrets | per-seller encrypted store (Workers secrets cannot hold thousands; use a vault or D1 with envelope encryption) |
| Model | per-seller budget; free model first, paid model for hard cases, billed in the plan |
| Billing | monthly plan per seller, by orders / marketplaces; usage shown in the dashboard |
| Sign-up | web page: marketplaces, logins (guided), Telegram link; then a first report within the hour |

## 6. Costs (rough, to be re-done with real usage)

| Stage | Monthly cost |
|---|---|
| Today (Bindal) | about Rs 0: free GitHub Actions (public repo), Cloudflare free, Workers AI free allocation |
| Phase 1-2 (Bindal) | Rs 0 to about Rs 1,000: a fallback model and / or a small VPS |
| Phase 3 (repo per seller) | per seller about the same as Bindal; a private repo per seller has a limited free Actions allowance (check), so a persistent runner may be needed |
| Phase 4 (hosted) | Workers Paid + database + job runner + paid model use: from roughly Rs 2,000-5,000 for the first sellers, growing with orders |

## 7. Measures to watch

* chat answer time (median, slowest of the day)
* report runs a day, failed %, runs that needed a manual rerun
* minutes per report (sale, VMS, AJIO TAT, Myntra SPF)
* model budget used per day, and how often the fallback was used
* KV writes per day, database size
* per seller: time from sign-up to first report, reports a day, alerts a week

## 8. Risks

| Risk | What to do |
|---|---|
| Portal changes (OMSGuru / Myntra / AJIO page or API changes) break reports | the watcher already alerts; keep each portal client small and tested by hand after a change; for many sellers, a change hits all of them at once |
| Marketplace terms on automated access | read each marketplace's seller terms before selling to others; prefer official APIs where they exist |
| Public repository | business data must never enter git (already enforced); make the product repo private before selling, with a token for installs |
| Secrets of many sellers in one place | Model A keeps them apart; Model B needs a real vault and access logs |
| The name "Ultron" (Marvel / Disney) | trademark check before selling |
| One person knows how it works | the SOP, `docs/bots/`, and `ultron check` / `ultron init` so another person can set it up |

## 9. Decisions needed from the owner

1. Phase 1 now? (chat in the worker, auto-retry, model fallback, one scheduler)
2. A small VPS / always-on PC for Phase 2, or stay on GitHub Actions for now?
3. When to start Phase 3 (seller-neutral workings): before or after the first outside seller?
4. Model A (repo per seller) for the first sellers?
5. Budget ceiling per month for the model and hosting.
