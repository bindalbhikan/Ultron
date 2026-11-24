# Agent chat — `python run.py agent-chat`

**When**: on a plain-text Telegram message from an allowed chat (`agent-chat.yml`, `workflow_dispatch`
started by the worker's `askAgent`; inputs `text`, `chat_id`, `reply_to`). Never on a schedule.
Also started by authenticated app chat with `app_request`: only a request id is passed to GitHub;
the question and plain-text reply stay in D1 `app_chat_job`, isolated by the signed-in user.
App chat uses the same model/fallback chain and private conversation history, with only read-only
run/order/business/knowledge tools. It has no owner action tools or shared-note writes, and never
sends the answer or failure to Telegram. The worker rechecks access when the agent claims its request.

* The owner writes to the Telegram bot in plain words; Ultron (`src/ultron/agents/chat.py`) reads what
  it needs with its tools (`[chat] tools` in `agent.toml`: run history and logs, OMSGuru, the Myntra
  login checks, public web pages) and answers in the same chat, at most about 10 lines, numbers exact.
* Run times reach the model in UTC and as `started_local` (the machine's zone, the workflows' `TZ`), so
  the owner is told their own time and "today" is their day (`integrations/github.py` `brief`; it gave UTC
  times as the owner's and missed two of three zero TD failures, 23 Nov 2026).
* Web pages: `browser_read` (`ultron.tools.browser`) opens them in Patchright, the only browser Ultron
  uses (`ultron.core.browser`). Public internet only, new empty profile each time, no logins; it
  reads and never clicks, types or sends. A page with a CAPTCHA or bot check is named and left out,
  never solved. CI installs it through the setup action (`browser: "true"`); on a seller's machine:
  `pip install -e ".[browser]"`, then `patchright install chromium`. `BROWSER_HEADLESS=0` shows the
  window; `BROWSER_CHANNEL=chrome` uses the installed Chrome.
* The model: the best of every provider with a key (Anthropic, OpenAI, Google AI Studio, NVIDIA, Groq),
  Cloudflare Workers AI last as the free fallback; the next one answers when one fails
  (`docs/bots/agent-models.md`). The control panel or `AGENT_MODEL*` variables override `agent.toml`.
* Business questions: `business_numbers` (sale, cancelled, RTO, returns, net qty / value, GMV, by portal / month /
  account / brand, any period: "Oct-26", "2026-10-01 to 2026-10-15", "last month") and `business_query` (one read-only
  SQL over the same facts: brand, category, design, top N ...). The facts are the business report's own order lines
  (Drive AGENT WORK/BUSINESS FACTS, refreshed with each report; `run.py business-report --facts-only` rebuilds only them),
  so the agent's numbers are the report's.
* A report-only action (`auto = true` in `agent.toml` and the worker's `AGENT_ACTIONS`: sale, VMS, morning, SLA, stock,
  evening, weekly, deadstock, listings, MIS, Myntra / Flipkart TAT, returns, AJIO ads) starts at once with `run_now`
  (worker `POST /api/run`, which refuses any other). Anything that changes something outside is proposed with
  `propose_action`: the owner gets Approve / Reject buttons and only an Approve tap starts it, from
  the fixed list in `agent.toml [actions]` (the worker's `AGENT_ACTIONS` must list the same).
* Memory: notes and earlier incidents from the worker's D1 database (`[memory]` in `agent.toml`).
* One message at a time per chat (`concurrency: agent-chat-<chat id>`); about 15 minutes at most.
* Not checked by the watcher (`[watch] skip`).
* Locally: `ultron serve` answers the same messages by Telegram long polling (`host/polling.py`).
