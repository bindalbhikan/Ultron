# Ultron's brain — what the agent knows and where it is kept

The agent (Ultron: the watcher and the Telegram chat) has three kinds of memory. People can read
the same things.

| Layer | What | Where | Who writes it | How the agent reads it |
|---|---|---|---|---|
| **Knowledge** | lasting facts about the portals and their APIs: every call seen, what it is for, what is safe | this folder, `docs/knowledge/` (public: names only, never values) | `scripts/knowledge/learn_netcap.py` from captures + agents / people by hand | tools `knowledge_search`, `knowledge_read` (`ultron.tools.knowledge`) |
| **Memory** | the owner's preferences, decisions, known harmless errors, past incidents | the dashboard worker's KV (private, not in the repo) | the chat (`remember`), the watcher (incidents) | `recall`; the watcher reads it before judging a run |
| **Docs** | how each working runs, its rules and schedule | `docs/bots/`, `docs/PORTALS.md`, `docs/CONTEXT.md`, `AGENTS.md` | every change (AGENTS.md rules) | the watcher gets the bot's page; `knowledge_*` also search `docs/PORTALS.md` |

Raw captures stay in `netcap/` on the owner's PC (git-ignored: they hold cookies and customer data).

## Pages

- `myntra-partner.md` — Myntra partner portal: what each call is for, what it could give us
  (notices, payments, seller rating, pricing), what is read-only and what changes something.
- `omsguru.md` — OMSGuru web app calls (inventory push, catalogue sync).
- `flipkart-seller.md` — Flipkart Seller Hub: every report centre report (Orders, Returns, Sales,
  Settled Transactions, Profit and Loss ...), payments pages, seller tier (W8).
- `api/<host>.md` — generated catalogues: every call seen on that host (method, path, query,
  body and answer field names, the page it came from, whether the code uses it yet).

## Teaching the agent something new

1. **A new capture** (the owner records a portal page with netcap): save the export in `netcap/`,
   run `python scripts/knowledge/learn_netcap.py`, then write in the portal's page what the new
   calls are for. Commit (the catalogue is names only).
2. **A fact learned while building**: add it to the portal's page here (or `docs/PORTALS.md` when a
   working already uses it).
3. **Something the owner says** ("this error is harmless", "I want X"): tell Ultron on Telegram; it
   keeps it in memory with `remember`.

Rules: names, paths and meanings only. Never a cookie, token, password, OTP, signed link, customer
name / phone / address, order-level amount or account id in this folder (the repo is public).
