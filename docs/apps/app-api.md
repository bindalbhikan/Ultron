# App API (`services/app_api`) — users, roles and the agent's control panel

**Status:** 22 Nov 2026: built and tested on the real Workers runtime (wrangler's test harness, local D1);
not deployed yet (`wrangler.jsonc` still has a placeholder `database_id`).

A Cloudflare Worker (TypeScript) that the Flutter app (`apps/ultron_app`) talks to. It runs on Cloudflare's
own runtime (workerd), never on Node; Node only runs the tools on a PC or in CI (wrangler, tsc, tests).

## One D1 database, two workers

The database is called `ultron`. Its tables come from `services/app_api/migrations` (applied in order by
`wrangler d1 migrations apply ultron`):

| Migration | Tables | Used by |
|---|---|---|
| `0001_identity.sql` | `user`, `session`, `account`, `verification`, `rate_limit` (better-auth), `app_role`, `app_access`, `app_audit` | app API |
| `0002_agent.sql` | `agent_note`, `agent_turn` (the agent's memory), `agent_setting` (model, tier, order); admin gets `agent.manage` and `memory.manage` | app API (binding `DB`) and the Telegram worker (`worker/`, binding `AGENT_DB`) |

The Python agent never reaches D1 directly. It calls the Telegram worker with its token
(`/api/memory/...`, `/api/settings`; see `docs/bots/worker-and-dashboard.md`). The app reaches D1 only
through this API, with a signed-in user's session and permissions.

## Routes

| Route | Permission | What |
|---|---|---|
| `POST /api/auth/sign-up/email`, `sign-in/email`, `sign-out`, `get-session`, `change-password` | none | better-auth. A public sign-up starts **pending** and cannot choose its role. |
| `GET /api/me` | signed in | the user, role and permissions |
| `GET /api/admin/users`, `PATCH /api/admin/users/<id>` | `users.manage` | list (50 a page, search), approve / disable / change role (revision checked) |
| `POST /api/admin/users` | `users.manage` | an administrator creates an account: name, email, password (12-128), an approved role. It starts **active**. The password is never audited. |
| `GET /api/admin/roles`, `PUT /api/admin/roles/<id>` | `roles.manage` | roles and their permissions (admin / pending cannot change) |
| `GET /api/admin/audit` | `users.manage` | the last 100 changes |
| `GET /api/agent/settings` | `agent.tools.read` | model (`auto` or `provider:model`), tier (`smart` / `fast`), provider order, revision |
| `PUT /api/agent/settings` | `agent.manage` | save them; a stale revision is refused (409) |
| `GET /api/agent/memory?kind=&search=` | `agent.tools.read` | the agent's notes, newest first (200), and the count of each kind |
| `DELETE /api/agent/memory/<id>` | `memory.manage` | drop one note (audited) |

The operational routes (`/api/reports`, `/api/workflows`, `/api/agent/chat` ...) check the permission
and then answer 503 until their services are connected.

What the panel saves reaches the agent within 5 minutes. The order is: the `AGENT_MODEL*` env vars first,
then the panel, then `[model]` in `agent.toml` (`ultron.core.llm.settings`, `src/ultron/core/models.py`).

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
