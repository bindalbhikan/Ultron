# Shared agent controls

The app and Telegram use one action registry and one permission-checked execution service (25 Nov 2026).

- agent.toml defines allowed actions. Workflow dispatch declarations supply field descriptions and defaults.
- scripts/docs/sync_controls.py generates worker/actions.json; docs sync also refreshes it. Tests reject stale metadata and scheduled/command inputs outside the catalog.
- worker/control.js validates actions, parameters, run state, permissions and schedule revisions. Both interfaces, chat tools and approvals call it.
- worker/agent.js owns dispatch, atomic approval claims and account-service delegation through the APP binding.
- The app API supplies its session's user id; a chat tool supplies a claimed D1 job id. The service reads current access from D1. Caller/model permission lists are ignored.
- Telegram chats must pass the existing allowlist. The scheduler has an internal workflow-only identity which the HTTP API refuses.

## Available controls

| Control | App | Telegram |
|---|---|---|
| Preview and start a working with its allowed parameters | Workflows form | Existing commands, chat, or shared control command |
| Cancel a running working / rerun a completed working | Run details, with confirmation | Chat proposal or shared control command |
| Pause/resume/move a scheduled task | Schedule editor | Chat proposal or shared control command |
| Model, tier and provider order | Existing control panel | Shared model.get / model.set |
| Provider model lists and refresh | Existing model picker | models.list / models.refresh |
| Key status, reset/reorder/remove | Existing key panel | keys.list / keys.change / keys.remove; values stay hidden |
| Shared notes | Existing memory panel | memory.list / memory.remove |
| SMS phone block/unblock and Agent mode revocation | Existing phone panel | phones.list / phones.block / phoneAgents.list / phoneAgents.revoke |
| Approval decisions | Approvals | Existing Approve / Reject buttons |

New passwords, API key values, first administrator setup and device activation stay in their secure app forms.
Marketplace login and CAPTCHA remain manual. Cancelling a run cannot undo portal changes already made.
Rerun uses the original run's code and inputs; the app asks for confirmation and the backend rejects PR/foreign/unlisted workflows.

## Preview and confirmation

Preview checks the request and returns its plan. It does not dispatch a workflow, change settings, write a schedule revision or create an approval.
The app's Preview switch is forwarded to the backend; Preview and Start run are distinct button labels.
Older clients that omit the preview flag are refused rather than silently starting a real run.
An explicit app Start run tap or Telegram execute command confirms an operation.
Chat tools cannot self-confirm: mutating requests become approvals, except permitted report actions explicitly marked auto.
Permissions are checked again when an approval is decided and when the original request is executed. Revoked users cannot regain access through an old proposal.
All decisions share the same D1 atomic claim, so app/Telegram clicks cannot dispatch the same approval twice.

## Schedule history

Default times/day filters remain in worker SCHEDULE. Runtime overrides live in agent_schedule; changes and revisions are recorded atomically in agent_schedule_history.
Only existing trigger times are offered; day/weekday rules remain intact and no cron triggers are added.
The app, Telegram and scheduler read the effective state. Pausing stops future automatic starts, not existing jobs.
Work-schedule reporting reads the same baseline and history via the authenticated schedule endpoint.
It counts only slots due while each revision was active, preserving earlier days and already due starts. Rows with changes identify their time as changed rather than publishing one misleading historical time.

## Routes and usage

- App: GET/POST /api/agent/control; /api/agent/tools and /api/agent/execute use the same catalog/executor.
- Worker: POST /api/control (private service token); identity is supplied by its trusted adapter.
- Reporting: GET /api/control/schedule (private service token).
- Account service: POST /api/internal/control (private Worker binding); reuses existing model/key/memory/phone handlers and their permission checks.

Telegram: /control lists supported operations. /control preview operation {arguments} validates only; /control execute operation {arguments} explicitly confirms. Without execute, changes wait for approval.
Ordinary chat can discover the catalog and propose the same operations without JSON commands.

R2 free-allowance guards remain unchanged. No live marketplace actions are used for testing.
