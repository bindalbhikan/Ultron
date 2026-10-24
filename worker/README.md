# Telegram worker (Bindal)

Cloudflare Worker behind @bindal_exports_bot. The bot is **Ultron · Ecom Manager**: every message
in an allowed chat goes to Ultron (`agent-chat.yml`), which answers in the same chat and asks
Approve / Reject before it runs anything (`[actions]` in `../agent.toml`, repeated in
`[vars.AGENT_ACTIONS]` of `wrangler.toml`). The worker is also the only scheduler of the daily
reports (cron triggers in `wrangler.toml`, times in `SCHEDULE` in `src/worker.js`), and keeps the
dashboard's numbers and the Myntra logins in KV.

| Message | What happens |
|---|---|
| plain words ("how many orders yesterday?", "run the sale report for 1-7 Oct") | Ultron answers; anything to run comes with Approve / Reject |
| `/start` | what Ultron can do (also removes the old menu keyboard and command list) |
| `/dashboard` | dashboard sign-in link, valid 10 min |
| an old command (`/sale ...`) or a tap on an old menu button | goes to Ultron / says the menu is retired |

The routes Ultron needs (`/api/ai` for its model, `/api/approval`, `/api/memory`, the plain-text
hand-off and the Approve / Reject taps) are `../agent.js`, the same for every seller.

Only chats in `ALLOWED_CHAT_IDS` (secret) + `EXTRA_CHAT_IDS` are obeyed; the webhook also checks
Telegram's secret header.

## Setup (once)

1. GitHub → Settings → Developer settings → Fine-grained tokens → **Generate new token**:
   repository `Ultron`, permission **Actions: Read and write**.
2. In PowerShell, from this folder: `powershell -ExecutionPolicy Bypass -File .\setup.ps1`
   and paste the token when asked. Bot token and chat id are read from `..\.env`.

After a code change: `npx wrangler deploy` from this folder. While the webhook is set,
`getUpdates` does not work for this bot (Telegram allows one or the other).
