# Agent chat — `python run.py agent-chat`

**When**: on a plain-text Telegram message from an allowed chat (`agent-chat.yml`, `workflow_dispatch`
started by the worker's `askAgent`; inputs `text`, `chat_id`, `reply_to`). Never on a schedule.

* The owner writes to the Telegram bot in plain words; Ultron (`src/ultron/agents/chat.py`) reads what
  it needs with its tools (`[chat] tools` in `agent.toml`: run history and logs, OMSGuru, the Myntra
  login checks) and answers in the same chat, at most about 10 lines, numbers exact.
* The model is Cloudflare Workers AI (free allocation) reached through the worker's `/api/ai` with the
  dashboard token; `AGENT_MODEL` (repo variable) overrides the model in `agent.toml`.
* Read-only. Anything to be done (start a report, add orders, push inventory) is proposed with
  `propose_action`: the owner gets Approve / Reject buttons and only an Approve tap starts it, from
  the fixed list in `agent.toml [actions]` (the worker's `AGENT_ACTIONS` must list the same).
* Memory: notes and earlier incidents from the worker's KV (`[memory]` in `agent.toml`).
* One message at a time per chat (`concurrency: agent-chat-<chat id>`); about 15 minutes at most.
* Not checked by the watcher (`[watch] skip`).
* Locally: `ultron serve` answers the same messages by Telegram long polling (`host/polling.py`).
