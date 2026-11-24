# App API (`services/app_api`) — users, roles and the agent's control panel

**Status:** 23 Nov 2026: deployed at `https://ultron-app-api.bhikan-serein.workers.dev` (D1 `ultron`, secret
`AUTH_SECRET`), tested on the real Workers runtime (wrangler's test harness, local D1).

**Sign-in is by username** (better-auth's username plugin, 3-30 letters, digits, dots or underscores; case does not
matter). Passwords are 8 to 128 characters. An account made without an email gets the internal address
`<username>@users.ultron.invalid`. A public registration starts **pending** until an administrator approves it.
**First-time setup** (no terminal): while no active administrator exists, the app's sign-in screen offers
"First-time setup"; the setup code (its SHA-256 is the worker secret `SETUP_CODE_HASH`; the code itself was given to the
owner once) plus a name, username and password the owner types make the first administrator (`GET/POST /api/setup`).
Once an administrator exists the route answers 409 for good. Or, from the owner's own terminal: `.venv\Scripts\python scriptspp\create_admin.py`.
It asks for the name, username and password (hidden), registers through the API, then promotes the account with
wrangler. The password never reaches a file or a log.

A Cloudflare Worker (TypeScript) that the Flutter app (`apps/ultron_app`) talks to. It runs on Cloudflare's
own runtime (workerd), never on Node; Node only runs the tools on a PC or in CI (wrangler, tsc, tests).

## One D1 database, two workers

The database is called `ultron`. Its tables come from `services/app_api/migrations` (applied in order by
`wrangler d1 migrations apply ultron`):

| Migration | Tables | Used by |
|---|---|---|
| `0009_app_release.sql` | Current completed R2 package per platform | app API; see app-updates.md |
| `0008_operations_state.sql` | Atomic approval decisions and independent phone jobs/results | Telegram worker |
| `0007_app_chat.sql` | `app_chat_job`: private per-user questions, answers and processing state; one pending request per user | app API and Telegram worker; Python agent processes a request id |
| `0001_identity.sql` | `user`, `session`, `account`, `verification`, `rate_limit` (better-auth), `app_role`, `app_access`, `app_audit` | app API |
| `0006_api_keys.sql` | `api_key` (AES-GCM, `KEYS_SECRET`), `agent_model` | the app API adds / lists, the worker decrypts for the agent |
| `0005_phone_agent.sql` | `phone_agent`: Agent mode phones (device, SHA-256 of the token, last seen, revoked) | the app API makes / revokes, the Telegram worker checks |
| `0004_username.sql` | `user.username` (unique) and `display_username` | app API (sign-in by username) |
| `0003_sms_phone.sql` | `sms_phone`: the phones in "SMS only" mode (name, last seen, SMS sent, blocked) | the Telegram worker writes, the app API lists and blocks |
| `0002_agent.sql` | `agent_note`, `agent_turn` (the agent's memory), `agent_setting` (model, tier, order); admin gets `agent.manage` and `memory.manage` | app API (binding `DB`) and the Telegram worker (`worker/`, binding `AGENT_DB`) |

The Python agent never reaches D1 directly. It calls the Telegram worker with its token
(`/api/memory/...`, `/api/settings`; see `docs/bots/worker-and-dashboard.md`). The app reaches D1 only
through this API, with a signed-in user's session and permissions.

## Routes

| Route | Permission | What |
|---|---|---|
| `POST /api/auth/sign-up/email` (name, username, password, optional email), `sign-in/username`, `sign-in/email`, `sign-out`, `get-session`, `change-password` | none | better-auth. A public sign-up starts **pending** and cannot choose its role. |
| `GET /api/me` | signed in | the user, role and permissions |
| `GET /api/admin/users`, `PATCH /api/admin/users/<id>` | `users.manage` | list (50 a page, search), approve / disable / change role (revision checked) |
| `POST /api/admin/users` | `users.manage` | an administrator creates an account: name, username, optional email, password (8-128), an approved role. It starts **active**. The password is never audited. |
| `GET /api/admin/roles`, `PUT /api/admin/roles/<id>` | `roles.manage` | roles and their permissions (admin / pending cannot change) |
| `GET /api/admin/audit` | `users.manage` | the last 100 changes |
| `GET /api/agent/settings` | `agent.tools.read` | model (`auto` or `provider:model`), tier (`smart` / `fast`), provider order, revision |
| `PUT /api/agent/settings` | `agent.manage` | save them; a stale revision is refused (409) |
| `GET /api/agent/keys`; `POST` (provider, key, label); `PATCH /<id>` (move up / down, reset); `DELETE /<id>` | `agent.tools.read` to list, `agent.manage` to change | the agent's model API keys, several per provider; listed by their last four characters only |
| `GET /api/agent/models` | `agent.tools.read` | each provider's models (the model picker). The app API reads them from the provider's own `GET /models` with one of its keys: at once when a key is added, again when the list is a day old. The list is replaced, so a new model appears and a retired one goes; only chat models are kept |
| `POST /api/agent/models/refresh` | `agent.manage` | read every provider's list again now (the **Refresh models** button) |
| `GET /api/workspace` | `app.access` | the live workspace from the Telegram worker (`worker/agent.js` `/api/app/workspace`, 2 minute cache): GitHub workflows with their last run, the last 40 runs, pending approvals, the reports' publish times, portal sessions and the Agent mode phone (time only, never cookies), and the cron schedule |
| `POST /api/workflows/run` (action) | `workflows.run` | start a working in the worker's `AGENT_ACTIONS`; the tap is the approval; Telegram is told who started it; audited |
| `POST /api/approvals/decide` (id, approve) | `approvals.decide` | approve or decline a pending agent proposal, as a tap on Telegram would; audited |
| `GET/POST /api/agent/chat` (text) | `agent.chat` | last 30 private questions / queue a question of 1-2000 characters; identity comes from the session, never the body; the existing Python agent answers asynchronously |
| `GET /api/agent/memory?kind=&search=` | `agent.tools.read` | the agent's notes, newest first (200), and the count of each kind |
| `DELETE /api/agent/memory/<id>` | `memory.manage` | drop one note (audited) |
| `GET /api/admin/phones` | `phone.manage` | the SMS-only phones, newest first: name, first / last seen, SMS sent, app version, blocked |
| `GET` / `POST /api/admin/phone-agents`, `DELETE /api/admin/phone-agents/<id>` | `phone.manage` | Agent mode phones: list; make a token for this phone (shown once, only its SHA-256 kept); revoke one. The worker's `/api/phone/next` and `/result` accept it until revoked |
| `PATCH /api/admin/phones/<id>` | `phone.manage` | block or unblock one (revision checked, audited); the worker then refuses its SMS (403) |

The app API reaches the worker through the `OPS` service binding (in `wrangler.jsonc`) with the secret
`WORKER_TOKEN` (the worker's `DASHBOARD_TOKEN`); the app never holds that token. Not through `WORKER_URL`:
one Worker fetching another Worker of the same account by its workers.dev URL gets Cloudflare's 404
(error 1042), which the app showed as "The operations service said 404". `WORKER_URL` is only the fallback. The other operational routes
(`/api/agent/tools`, `/api/agent/execute` ...) check the permission and then answer 503 until their services are connected.

App chat uses the existing `agent-chat.yml` workflow. Only the request id is dispatched to GitHub;
the message stays in D1. A worker-authenticated job claim rechecks the account's active status and
chat permission. The Python agent uses read-only tools (runs, orders, business facts and knowledge),
private `app:<user>` history, and no Telegram notifications or owner action/shared-note write tools.
Workflows and approvals stay in their separately authorised screens. Requests expire after 30 minutes;
dispatch failures and expired requests are shown as failures, and a result can be saved only once.

What the panel saves reaches the agent within 5 minutes. The order is: the `AGENT_MODEL*` env vars first,
then the panel, then `[model]` in `agent.toml` (`ultron.core.llm.settings`, `src/ultron/core/models.py`).

## Operations fixes (24 Nov 2026)

Workspace fields are filtered on the server: workflows/GitHub require workflows.read; runs require workflows.read or analytics.read; approvals/reports/connections/schedule require their own read permission.
Restricted lists are empty even when callers bypass navigation.

Approval decisions share a conditional D1 claim between Telegram and app. Concurrent decisions dispatch at most once; explicit GitHub client refusals keep the request pending.
Network/server ambiguity marks it uncertain and prevents another automatic dispatch; inspect GitHub run history.
Read-only app chat propagates model outages so the job and workflow fail, rather than saving a successful apology.

Public update discovery/downloads and private CI publication use the optional RELEASES R2 binding. See app-updates.md.

## Checks

* A row is counted as changed through `RETURNING`, not `meta.changes`. D1 also counts the rows its
  triggers change (the sessions revoked when access changes), which made every approval look stale.
* Every change writes `app_audit`. The last active administrator cannot be removed.
* A change of access or of a role's permissions signs the affected users out.

## Run, test, deploy

```powershell
cd services/app_api
npm ci
npm run check        # TypeScript
npm test             # the real Worker (wrangler.jsonc) on local D1 with every migration
# once: npx wrangler d1 create ultron   -> put the id in wrangler.jsonc and worker/wrangler.toml
npx wrangler d1 migrations apply ultron --remote
npx wrangler secret put AUTH_SECRET  # 32+ random characters
npx wrangler deploy
```

CI: the `app-api` job of `tests.yml` runs the check, the tests and `node --check worker/agent.js` on every push.
