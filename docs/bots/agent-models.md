# The agent's models and memory (its brain)

**Status:** 22 Nov 2026: built and tested. It goes live when the Telegram worker is deployed
(`cd worker && npx wrangler deploy`, after `npx wrangler d1 create ultron` and the migrations).

## Models: every provider, auto-selected, with fallback

`src/ultron/core/models.py` picks the models. `src/ultron/core/llm.py` calls them, all through one
client, the official **OpenAI SDK** (chat completions with tools), each at the provider's
OpenAI-compatible address:

| Provider | Key (GitHub secret / env) | Smart tier picks | Fast tier picks |
|---|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | newest `claude-opus-*`, else `claude-sonnet-*` | newest `claude-haiku-*` |
| `openai` | `OPENAI_API_KEY` | newest `gpt-N` / `gpt-N.N` | newest `gpt-…-mini` |
| `google` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), Google AI Studio | `gemini-pro-latest` (Google still lists the retired `gemini-2.5-pro`, which answers 404), else the newest `gemini-…-pro` | newest `gemini-…-flash` |
| `nvidia` | `NVIDIA_API_KEY` | `openai/gpt-oss-120b`, else a Nemotron Ultra / Super | `openai/gpt-oss-20b`, Nemotron Nano |
| `groq` | `GROQ_API_KEY` | `openai/gpt-oss-120b` | `openai/gpt-oss-20b` |
| `cloudflare` | none: the worker (`DASHBOARD_URL` / `DASHBOARD_TOKEN`) | `@cf/openai/gpt-oss-120b` | `@cf/openai/gpt-oss-20b` |

* **Auto-select:** each provider's model list (`GET /models`) is read once a day and kept in
  `<output>/agent/models.json`. "Newest" is decided by the numbers in the id. Previews, dated snapshots,
  embedding, audio and image models never count. When a list cannot be read, the known model is used.
* **Fallback:** the models are tried in order: the pinned one first, then the best of every provider with
  a key. A model that fails (no credit, rate limit, down, a request it refuses) hands over to the next,
  and the log says which failed and why. A provider that refused the key, the credit or the rate
  (401 / 402 / 403 / 429) is left out for 10 minutes.
* **Groq free plan** (late 2026, third-party figures): about 30 requests a minute, 1,000 a day,
  8,000 tokens a minute and 200,000 a day for gpt-oss. A request bigger than 8,000 tokens is refused and
  goes to the next provider.
* **Cloudflare** stays last as the free safety net: the worker's `/api/chat/completions` and
  `/api/models` (OpenAI shape; `/api/ai` is the same route, for older agents).

### API keys: several per provider, rotated

Keys come from two places, tried in this order for each provider: the env var (GitHub secret) first, then the keys
added in the app (**Control -> Brain: API keys**), in the order set there. A key that hits its limit (HTTP 402 / 429)
rests until the provider's `retry-after` (else an hour) and the next key of the same provider answers at once; a
refused key (401 / 403) rests a day and shows *Refused* in the app until someone taps *Try again now* or removes it.
The agent reports both to the app (worker `POST /api/keys/report`), so the app shows *Limit · back HH:MM*.

App keys are stored in D1 `api_key`, AES-GCM encrypted with `KEYS_SECRET` (a secret of both the app API and the
Telegram worker). The app sees only the last four characters. The worker decrypts them only for the agent's token
(`GET /api/keys`, read every 5 minutes).

The model picker (Brain: model, auto off) lists each provider's models as the agent last read them (the agent
sends a fresh list to the worker's `PUT /api/models`; D1 `agent_model`), or a few known ones before that.

### Settings, in the order they count

1. `AGENT_MODEL`, `AGENT_MODEL_TIER`, `AGENT_MODEL_ORDER` (repository variables / env)
2. the app's **Control panel** (D1 `agent_setting`, read through the worker's `GET /api/settings`
   every 5 minutes; `docs/apps/app-api.md`)
3. `[model]` in `agent.toml`: `name` (`auto` or `provider:model`), `tier` (`smart` | `fast`), `order`

`ultron check` prints the models it would try, in order.

The log line of every answer names the model that gave it and its cost at list price
(`[model.prices]`, defaults in `core/config.py`). A model without a price is logged as "price unknown".

## Memory: Cloudflare D1

`src/ultron/core/memory.py` holds two kinds of memory:

* **Notes** are long-term: preferences, facts, known issues, decisions and incidents. A note is stored
  once; the same note again is refreshed and counted. When there are more than `max_notes`, incidents go
  first, then the least used. Preferences go last.
* **Chats** are short-term: the last `history_turns` messages of each chat, no older than
  `history_days`.

The memory is kept in the D1 database `ultron`, one row per note (`agent_note`) and per message
(`agent_turn`). Two runs writing at once never overwrite each other. The worker serves it (`worker/agent.js`):

| Route (worker token) | What |
|---|---|
| `GET /api/memory/notes` | every note |
| `PUT /api/memory/notes/<id>` | add or refresh one; the worker then trims to `max` in the same order |
| `DELETE /api/memory/notes/<id>` | drop one |
| `GET` / `POST` / `DELETE /api/memory/chats/<chat>` | the last messages; add one (keeps `keep`); clear |
| `GET /api/settings` | the control panel's model settings |

The KV document of older agents is copied into D1 once, on the first call, and KV keeps a "moved" mark.
The old `GET`/`PUT /api/memory` route answers 410.

Text that looks like a password, OTP, key, token, phone number or email is refused before it reaches
any store. `backend = "file"` keeps the same memory in `<output>/agent/memory.json`, for
`ultron serve` without a worker.

The control panel lists the notes and lets an administrator drop one (`memory.manage`).
