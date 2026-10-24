# Telegram worker (Bindal)

Cloudflare Worker behind @bindal_exports_bot: a button menu, portal by portal, that starts the
report workflows of this repo; Ultron, Ecom Manager, for everything typed in plain words; and the
only scheduler of the worker-cron daily runs (cron triggers in `wrangler.toml`, times in `SCHEDULE`
in `src/worker.js`). It also keeps the dashboard's numbers, the Myntra logins and Ultron's memory
and approvals in KV.

## The menu (`/menu`, or **📋 Menu** under the chat box)

| Screen | Buttons |
|---|---|
| 🏠 Main | quick runs: sale yesterday / today, VMS today, AJIO TAT today, sale and VMS sheet photos; then the portals |
| 🛍 Myntra | VMS (today / 7 days / month / sheet photo / ERP vs VMS), Myntra SPF, courier OTP, daily reports, courier scorecard, login check (Ultron), orders yesterday (Ultron) |
| 🟠 AJIO | TAT (today / 3 / 7 days), SPF (dry run / master only / LIVE, asks first), ads / TOT gap, orders yesterday (Ultron) |
| 🛒 Flipkart | orders yesterday and due today (Ultron), sale report, return analysis |
| 📦 All channels | sale (yesterday / today / 7 days / month / sheet photo), morning, SLA, stock-out, labels, listing health, inventory push (dry / now, asks first), evening |
| 📊 Reports & MIS | weekly review, monthly MIS, return analysis, dead stock, AJIO ads gap |
| 📋 Status · 🖥 Dashboard · 🤖 Help | last run of every report, portal by portal; sign-in link; every command |

A report started from the menu or a command comes back to the chat that asked (workflows with a
`chat_id` input), else to the main chat.

## Commands

Every report has a command (`/help` lists them, portal by portal), e.g. `/sale today`,
`/sale 2026-10-01 2026-10-07`, `/vms erp`, `/ajiotat 3`, `/ajiospf dry`, `/ajiospf master`,
`/returns 2026-09`, `/salepic 2026-09`, `/morning`, `/sla`, `/invpush dry`, `/mis`. A command the
menu does not know, and any plain words, go to Ultron, which answers in the same chat and asks
Approve / Reject before it runs anything (`[actions]` in `../agent.toml`, repeated in
`[vars.AGENT_ACTIONS]` of `wrangler.toml`).

Only chats in `ALLOWED_CHAT_IDS` (secret) + `EXTRA_CHAT_IDS` are obeyed; the webhook also checks
Telegram's secret header.

## Setup (once)

1. GitHub → Settings → Developer settings → Fine-grained tokens → **Generate new token**:
   repository `Ultron`, permission **Actions: Read and write**.
2. In PowerShell, from this folder: `powershell -ExecutionPolicy Bypass -File .\setup.ps1`
   and paste the token when asked. Bot token and chat id are read from `..\.env`.

After a code change: `npx wrangler deploy` from this folder. While the webhook is set,
`getUpdates` does not work for this bot (Telegram allows one or the other).
