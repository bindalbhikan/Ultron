# Cloudflare and SMS boundaries
- worker/src/worker.js: Telegram routes, commands/menu, scheduler SCHEDULE, dashboard keys. worker/agent.js: shared agent routes. dashboard/ is separately deployed; services/app_api/ separately deployed app backend.
- Free plan at most five cron triggers; each SCHEDULE time must match configured worker/wrangler.toml triggers. Weekdays/day filters use IST. Mirror times in workings/work_schedule/pipeline.py TASKS/WORK.
- App API -> operations worker uses OPS service binding in services/app_api/wrangler.jsonc, never worker workers.dev URL (Cloudflare 1042/404).
- App username sessions differ from Telegram/dashboard authentication; enforce authorization server-side. Secrets never embedded in Flutter builds.
- App API commands/checks are in `mem:suggested_commands`; service behavior documented in docs/apps/app-api.md and docs/bots/worker-and-dashboard.md.
- services/sms_sheet/Code.gs deployed with clasp as a new version of the existing web app deployment; compare live code before push and keep URL. Deployment ids remain private.
- OTP team sheet name is phone username only; note ULTRON app identifies agent rows. Do not add Agent prefix.
