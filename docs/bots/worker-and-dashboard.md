# Telegram worker and dashboard

App/Telegram controls now share one catalog, validation and execution service. See ../apps/shared-controls.md.
The APP service binding delegates account controls to their existing handlers; no workers.dev inter-worker fetch is used.

**Worker** `bindal-telegram-bot` (`worker/`, Cloudflare): the Telegram webhook (commands + menu
buttons; only `ALLOWED_CHAT_IDS` + `EXTRA_CHAT_IDS` are obeyed), the scheduler (5 cron triggers to
GitHub `workflow_dispatch`, `SCHEDULE` with `day` / `weekdays` filters), `/api/push/<key>` for the
dashboard numbers (`DASHBOARD_TOKEN`, keys listed in `DASH_KEYS`), and `/api/myntra-session[/read]`
for the saved Myntra sessions (`?account=main|dbcc|fmcc`). Deploy after every change:
`cd worker && npx wrangler deploy`. Secrets: `TELEGRAM_BOT_TOKEN`, `GITHUB_TOKEN`, `WEBHOOK_SECRET`,
`ALLOWED_CHAT_IDS`, `EXTRA_CHAT_IDS`, `DASHBOARD_TOKEN`, `SESSION_KEY`.

**Dashboard** `bindal-dashboard` (`dashboard/`): reads KV `DASH`; sign-in through `/dashboard` in
Telegram (one-time link valid 10 minutes, then a 30-day cookie, signed with `SESSION_KEY`).
Sections per bot from the pushed numbers (see `dashboard/src/page.html`); the data keys it reads
are `KEYS` in `dashboard/src/index.js` and must also be in the worker's `DASH_KEYS`.

| Tab | Key(s) | Shows |
|---|---|---|
| Sale | `sale`, `sale_today` | daily gross chart, channels vs last month, today so far |
| VMS | `vms`, `vms_erp` | VMS % by SLA date, NO VMS list, ERP vs VMS by packer |
| TAT | `ajio_tat` | TAT result per day, couriers, pickup pending list |
| AJIO SPF | `ajio_spf` | open returns by age, run summary, courier pickup, tickets |
| Myntra SPF | `myntra_spf` | per account / total: final status, received source (ERP / OMSGuru / manual), claim status + value (and how many values are known), open by age, returns per month |
| Returns | `returns`, `returns_year` | return % per portal (month / year), % by month, top reasons, brands, categories, states (`src/ultron/workings/return_analysis/dash.py`) |
| Ads | `ajio_ads` | G4 per month, charge, charge / G4 %, pending months |

Operations reliability (24 Nov): approval decisions use atomic D1 claims shared by app/Telegram.
Explicit GitHub client refusals retain the request; network/server ambiguity blocks another dispatch.
Phone jobs/results have independent D1 rows (worker/phone.js, migration 0008), so Zero TD and Grouping cannot overwrite each other.
Next claims atomically with a 30-minute lease; collection needs every part. The current KV job is imported during deployment.

KPIs: sale, VMS %, AJIO pickup pending, AJIO open returns, Myntra claims eligible, last month's
return %. The run strip shows every bot's last run (`run_<key>`, pushed by `core/app.py`).
* `POST /api/chat/completions` (also `/api/ai`) and `GET /api/models` (`DASHBOARD_TOKEN`): Workers AI in the
  OpenAI shape for Ultron (`ultron.core.llm`, the OpenAI SDK; routes in `worker/agent.js`), only its
  `FREE_MODELS`, on the free daily allocation (`[ai]` binding).
* `/api/memory/notes`, `/api/memory/chats/<chat>`, `GET /api/settings` (`DASHBOARD_TOKEN`): the agent's
  memory and the control panel's model settings in D1 (binding `AGENT_DB`, database `ultron`; tables from
  `services/app_api/migrations`). See `docs/bots/agent-models.md`.
* `/api/phone/next` and `/api/phone/result` also take an Agent mode phone's own token (D1 `phone_agent`,
  made and revoked by the app API, `docs/apps/app-api.md`); `/api/phone/job` and `/collect` stay on `DASHBOARD_TOKEN`.
* `GET /api/keys`, `POST /api/keys/report`, `PUT /api/models` (`DASHBOARD_TOKEN`): the app's model API keys,
  decrypted (`KEYS_SECRET`) for the Python agent only; a key's limit / refusal reported back; the models each
  provider offers, for the app's model picker (`docs/bots/agent-models.md`).
* `POST /api/sms` (no token): one SMS from a phone in the Ultron app's "SMS only" mode. The body is JSON:
  `phone` (the app's random UUID), `name` (2-40 characters, typed once on the phone), `from`, `body`, `time`, `sim`,
  and the POD fields `pdf`, `pdftext`, `pdferror`, `html`. The worker records the phone in D1 `sms_phone` and refuses
  a blocked one (403) or more than 300 SMS an hour (429). It then posts the SMS to the SMS sheet's Apps Script
  (worker secrets `SMS_WEBAPP_URL`, `SMS_WEBAPP_KEY`, the same values as in `.env`) with `user` = the name, and
  answers the script's own word (`ok`, `duplicate`, `empty`, `error: ...`). The phone never holds the sheet's secret.
