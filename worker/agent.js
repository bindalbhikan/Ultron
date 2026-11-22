// Ultron routes for a seller's Cloudflare worker (the same for every seller):
//
//   POST /api/chat/completions  one chat-completions call to Workers AI (ultron.core.llm, the OpenAI SDK;
//                       /api/ai is the same, for older agents)
//   GET  /api/models    the Workers AI models allowed, in the OpenAI list shape (core/models.py auto-select)
//   POST /api/approval  ultron.agents.chat proposes an action: saved in KV, Approve / Reject buttons sent
//   /api/memory/notes[/<id>]    the agent's long-term notes (ultron.core.memory): GET all, PUT one, DELETE one
//   /api/memory/chats/<chat>    the last messages of a chat: GET, POST one, DELETE all
//   GET /api/settings   the model settings the app's control panel saved (core/llm.settings)
//   GET /api/keys       the model API keys added in the app (D1 api_key, AES-GCM with KEYS_SECRET), decrypted
//                       for the Python agent only; POST /api/keys/report marks one at its limit or refused
//   PUT /api/models     the models each provider offers, as the agent read them (the app's model picker)
//   POST /api/sms       one SMS from a phone in the app's "SMS only" mode (no account, no token): the
//                       worker records the phone (D1 sms_phone), and passes the SMS to the SMS sheet's
//                       Apps Script with SMS_WEBAPP_URL / SMS_WEBAPP_KEY (worker secrets), the phone's
//                       name in the sheet's User column; it answers the script's word (ok / duplicate ...)
//                       memory and settings live in the D1 database bound as `db` (tables in
//                       services/app_api/migrations/0002_agent.sql); the old KV document is moved in once
//   plain text          an owner's message starts the agent-chat workflow, which answers in the chat
//   ap:<id> / rj:<id>   a tap on Approve / Reject: only Approve starts the saved action
//
// The seller's setup comes from the worker's env:
//   AGENT_ACTIONS  (wrangler.toml [vars.AGENT_ACTIONS]) {name: {workflow, inputs: [..]}}: the only
//                  workflows and inputs an approval can start; the same list as agent.toml [actions]
//   GITHUB_TOKEN, TELEGRAM_BOT_TOKEN (secrets), the [ai] binding AI, the KV namespace passed as `kv`,
//   the D1 database passed as `db`.
//
// Use: const agent = makeAgent({ repo: "owner/name", token: (env) => env.AGENT_TOKEN, allowedChat, kv: "DASH" });
//      agent.route(request, env, path) -> Response | null;  agent.ask(env, chatId, messageId, text);
//      agent.isTap(data) / agent.decide(env, cb, data)

export const FREE_MODELS = ["@cf/openai/gpt-oss-120b", "@cf/qwen/qwen3.8-27b", "@cf/nvidia/nemotron-3-120b-a12b",
                            "@cf/openai/gpt-oss-20b"];

export function makeAgent({
  repo,                                  // "owner/name" of the seller's bots repo
  token = (env) => env.AGENT_TOKEN,      // bearer token the Python side sends
  allowedChat = (env, chatId) => String(env.ALLOWED_CHAT_IDS || "").split(",").map((s) => s.trim()).includes(String(chatId)),
  kv = "AGENT_KV",                       // KV binding name for pending approvals
  db = "AGENT_DB",                       // D1 binding name for the memory and the settings
  chatWorkflow = "agent-chat.yml",
  ref = "main",
  models = FREE_MODELS,                  // Workers AI models allowed on /api/ai
  approvalHours = 24,
  smsPerHour = 300,                      // SMS one phone may send in an hour ("SMS only" mode)
  userAgent = "ultron-worker",
} = {}) {
  const allowedModels = new Set(models);

  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const github = (env, path, init = {}) => fetch(`https://api.github.com${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": userAgent },
  });

  const telegram = async (env, method, body) => {
    const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!res.ok) console.log(`${method} ${res.status}: ${await res.text()}`);
    return res;
  };

  const send = (env, chatId, text, replyTo, markup) => telegram(env, "sendMessage", {
    chat_id: chatId, text, parse_mode: "HTML", disable_web_page_preview: true,
    ...(replyTo ? { reply_parameters: { message_id: replyTo, allow_sending_without_reply: true } } : {}),
    ...(markup ? { reply_markup: markup } : {}),
  });

  const authorised = (request, env) => {
    const t = token(env) || "";
    return t && request.headers.get("Authorization") === `Bearer ${t}`;
  };

  const actions = (env) => {
    const a = env.AGENT_ACTIONS;
    return typeof a === "string" ? JSON.parse(a) : (a || {});
  };

  const dispatch = (env, workflow, inputs) => github(env, `/repos/${repo}/actions/workflows/${workflow}/dispatches`, {
    method: "POST", body: JSON.stringify({ ref, inputs }),
  });

  async function ask(env, chatId, messageId, text) {
    try {
      const res = await dispatch(env, chatWorkflow, { text: text.slice(0, 1500), chat_id: String(chatId),
                                                      reply_to: messageId ? String(messageId) : "" });
      if (res.status !== 204) throw new Error(`GitHub said ${res.status}: ${(await res.text()).slice(0, 200)}`);
      await send(env, chatId, "🤖 On it… (about 1-2 minutes)", messageId);
    } catch (e) {
      await send(env, chatId, `❌ <b>The agent did not start</b>\n<code>${esc(e.message)}</code>`, messageId);
    }
  }

  async function saveApproval(request, env) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    let req;
    try {
      req = JSON.parse(await request.text());
    } catch {
      return new Response("not JSON", { status: 400 });
    }
    const action = actions(env)[req.action];
    if (!action) return Response.json({ error: `unknown action ${req.action}` }, { status: 400 });
    const inputs = {};
    for (const [k, v] of Object.entries(req.inputs || {})) {
      if (!(action.inputs || []).includes(k)) return Response.json({ error: `input ${k} not allowed for ${req.action}` }, { status: 400 });
      inputs[k] = String(v).slice(0, 1000);
    }
    const chat = String(req.chat_id || "");
    if (!allowedChat(env, chat)) return Response.json({ error: "chat not allowed" }, { status: 400 });
    const id = crypto.randomUUID().slice(0, 12);
    await env[kv].put(`approval:${id}`, JSON.stringify({ action: req.action, inputs, chat }),
                      { expirationTtl: approvalHours * 3600 });
    const args = Object.entries(inputs).map(([k, v]) => `${k} = ${v}`).join("\n") || "(no inputs)";
    await send(env, chat,
      `🙋 <b>Approve this?</b>\n\n${esc(String(req.summary || req.action).slice(0, 600))}\n\n` +
      `<b>Run:</b> ${esc(action.workflow)}\n<code>${esc(args)}</code>\n\n<i>Expires in ${approvalHours} hours.</i>`,
      undefined, { inline_keyboard: [[{ text: "✅ Approve", callback_data: `ap:${id}` }, { text: "✖️ Reject", callback_data: `rj:${id}` }]] });
    return Response.json({ id });
  }

  const isTap = (data) => /^(ap|rj):/.test(String(data || ""));

  async function decide(env, cb, data) {
    const key = `approval:${data.slice(3)}`;
    const saved = await env[kv].get(key, "json");
    const edit = (text) => telegram(env, "editMessageText", { chat_id: cb.message.chat.id, message_id: cb.message.message_id,
                                                             text, parse_mode: "HTML", disable_web_page_preview: true });
    if (!saved || String(saved.chat) !== String(cb.message.chat.id)) {     // a tap from another chat uses nothing up
      await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Expired or already decided" });
      return edit(`${cb.message.text ? esc(cb.message.text) : ""}\n\n⌛ <i>Expired or already decided.</i>`);
    }
    await env[kv].delete(key);                     // one tap decides it, a second does nothing
    const who = esc(cb.from?.first_name || "someone");
    if (data.startsWith("rj:")) {
      await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Rejected" });
      return edit(`${esc(cb.message.text || "")}\n\n✖️ <b>Rejected</b> by ${who}.`);
    }
    const action = actions(env)[saved.action];
    if (!action) {
      await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Action no longer allowed" });
      return edit(`${esc(cb.message.text || "")}\n\n❌ <i>${esc(saved.action)} is no longer in AGENT_ACTIONS.</i>`);
    }
    const res = await dispatch(env, action.workflow, saved.inputs);
    await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: res.status === 204 ? "Started" : "Failed" });
    return edit(`${esc(cb.message.text || "")}\n\n` + (res.status === 204
      ? `✅ <b>Approved</b> by ${who}: ${esc(action.workflow)} started.`
      : `❌ Approved by ${who}, but GitHub said ${res.status}: ${esc((await res.text()).slice(0, 200))}`));
  }

  // Workers AI on the account's free daily allocation: one chat-completions call (OpenAI shape:
  // messages, tools, tool_calls), only the allowed models.
  async function runAI(request, env) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    const body = await request.text();
    if (body.length > 1_500_000) return new Response("too large", { status: 413 });
    let req;
    try {
      req = JSON.parse(body);
    } catch {
      return new Response("not JSON", { status: 400 });
    }
    const { model, ...input } = req;
    if (!allowedModels.has(model)) return new Response("model not allowed", { status: 400 });
    try {
      return Response.json(await env.AI.run(model, { ...input, stream: false }));
    } catch (e) {
      // the free allocation used up, or the model failing: the caller reports it
      return Response.json({ error: String(e && e.message || e) }, { status: 502 });
    }
  }

  function listModels(request, env) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    return Response.json({ object: "list", data: models.map((id) => ({ id, object: "model", owned_by: "workers-ai" })) });
  }

  // The agent's memory (ultron.core.memory, WorkerStore) in D1: one row per note (agent_note) and
  // per message (agent_turn), so two runs writing at once never overwrite each other.
  const KINDS = new Set(["preference", "fact", "known_issue", "decision", "incident"]);
  const OLD_MEMORY = "agent:memory", MOVED = "agent:memory:moved";
  const TRIM = `DELETE FROM agent_note WHERE id IN (SELECT id FROM agent_note ORDER BY
    CASE kind WHEN 'incident' THEN 0 WHEN 'known_issue' THEN 2 WHEN 'preference' THEN 3 ELSE 1 END, uses, updated
    LIMIT (SELECT MAX(0, COUNT(*) - ?) FROM agent_note))`;
  let moved = false;

  const bad = (why, status = 400) => Response.json({ error: why }, { status });
  async function jsonBody(request, limit = 20000) {
    const text = await request.text();
    if (text.length > limit) throw bad("too large", 413);
    try {
      const value = JSON.parse(text);
      if (value && typeof value === "object" && !Array.isArray(value)) return value;
    } catch { /* below */ }
    throw bad("not JSON");
  }

  // the KV document of older agents, copied into D1 once (then KV keeps a "moved" mark)
  async function moveOldMemory(env) {
    if (moved || await env[kv].get(MOVED)) { moved = true; return; }
    const saved = await env[kv].get(OLD_MEMORY, "json");
    const data = (saved && saved.data) || {};
    const rows = [];
    for (const n of data.notes || []) {
      if (!KINDS.has(n.kind) || !n.text) continue;
      const id = /^[a-f0-9]{6,16}$/.test(String(n.id)) ? String(n.id) : crypto.randomUUID().replace(/-/g, "").slice(0, 12);
      rows.push(env[db].prepare(`INSERT OR IGNORE INTO agent_note(id,kind,text,tags,source,uses,created,updated)
        VALUES(?,?,?,?,?,?,?,?)`).bind(id, n.kind, String(n.text), JSON.stringify(n.tags || []),
        String(n.source || ""), Number(n.uses) || 0, Number(n.created) || 0, Number(n.updated) || 0));
    }
    for (const [chat, turns] of Object.entries(data.chats || {})) {
      for (const t of turns || []) {
        rows.push(env[db].prepare("INSERT INTO agent_turn(chat,at,q,a) VALUES(?,?,?,?)")
          .bind(String(chat), Number(t.at) || 0, String(t.q || ""), String(t.a || "")));
      }
    }
    for (let i = 0; i < rows.length; i += 50) await env[db].batch(rows.slice(i, i + 50));
    await env[kv].put(MOVED, new Date().toISOString());
    moved = true;
  }

  async function memory(request, env, path) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    if (path === "/api/memory") return bad("the memory moved to D1: update ultron", 410);
    try {
      await moveOldMemory(env);
      const m = request.method;
      const note = path.match(/^\/api\/memory\/notes(?:\/([a-f0-9]{6,16}))?$/);
      if (note && !note[1] && m === "GET") {
        const { results } = await env[db].prepare(
          "SELECT id,kind,text,tags,source,uses,created,updated FROM agent_note ORDER BY created,id").all();
        return Response.json({ notes: results.map((r) => ({ ...r, tags: JSON.parse(r.tags) })) });
      }
      if (note && note[1] && m === "PUT") {
        const n = await jsonBody(request);
        const tags = Array.isArray(n.tags) ? n.tags.filter((t) => typeof t === "string").map((t) => t.slice(0, 60)).slice(0, 20) : [];
        if (!KINDS.has(n.kind) || typeof n.text !== "string" || !n.text.trim() || n.text.length > 2000) return bad("bad note");
        const max = Math.min(Math.max(Number(n.max) || 400, 1), 5000);
        await env[db].batch([
          env[db].prepare(`INSERT INTO agent_note(id,kind,text,tags,source,uses,created,updated) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,text=excluded.text,tags=excluded.tags,
            uses=excluded.uses,updated=excluded.updated`).bind(note[1], n.kind, n.text, JSON.stringify(tags),
            String(n.source || "").slice(0, 40), Number(n.uses) || 0, Number(n.created) || 0, Number(n.updated) || 0),
          env[db].prepare(TRIM).bind(max),
        ]);
        return Response.json({ id: note[1] });
      }
      if (note && note[1] && m === "DELETE") {
        const r = await env[db].prepare("DELETE FROM agent_note WHERE id=?").bind(note[1]).run();
        return Response.json({ deleted: r.meta.changes > 0 });
      }
      const chat = path.match(/^\/api\/memory\/chats\/(-?[0-9A-Za-z_:-]{1,64})$/);
      if (chat && m === "GET") {
        const { results } = await env[db].prepare(
          "SELECT at,q,a FROM agent_turn WHERE chat=? ORDER BY id DESC LIMIT 100").bind(chat[1]).all();
        return Response.json({ turns: results.reverse() });
      }
      if (chat && m === "POST") {
        const t = await jsonBody(request);
        if (typeof t.q !== "string" || typeof t.a !== "string") return bad("bad turn");
        const keep = Math.min(Math.max(Number(t.keep) || 10, 1), 100);
        await env[db].batch([
          env[db].prepare("INSERT INTO agent_turn(chat,at,q,a) VALUES(?,?,?,?)")
            .bind(chat[1], Number(t.at) || Math.floor(Date.now() / 1000), t.q.slice(0, 1500), t.a.slice(0, 2500)),
          env[db].prepare(`DELETE FROM agent_turn WHERE chat=? AND id NOT IN
            (SELECT id FROM agent_turn WHERE chat=? ORDER BY id DESC LIMIT ?)`).bind(chat[1], chat[1], keep),
        ]);
        return Response.json({ ok: true });
      }
      if (chat && m === "DELETE") {
        await env[db].prepare("DELETE FROM agent_turn WHERE chat=?").bind(chat[1]).run();
        return Response.json({ ok: true });
      }
      return new Response("not found", { status: 404 });
    } catch (e) {
      if (e instanceof Response) return e;
      return Response.json({ error: String(e && e.message || e) }, { status: 500 });
    }
  }

  // The model settings the control panel saved (agent_setting: model, tier, order), for core/llm.settings.
  async function settings(request, env) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    const { results } = await env[db].prepare(
      "SELECT key,value FROM agent_setting WHERE key IN ('model','tier','order')").all();
    return Response.json(Object.fromEntries(results.map((r) => [r.key, JSON.parse(r.value)])));
  }

  // "SMS only" phones: no account, so the phone never holds the sheet's secret; it sends its random id,
  // the name its person typed, and the SMS. A blocked phone, a bad id or too many SMS in an hour is refused.
  const PHONE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const SMS_FIELDS = ["from", "body", "time", "sim", "pdf", "pdftext", "pdferror", "html", "rework"];
  async function sms(request, env) {
    if (request.method !== "POST") return new Response("method not allowed", { status: 405 });
    if (!env.SMS_WEBAPP_URL || !env.SMS_WEBAPP_KEY) return bad("the SMS sheet is not set up on the worker", 503);
    let m;
    try {
      m = await jsonBody(request, 15_000_000);         // a POD PDF rides along, base64
    } catch (e) {
      return e instanceof Response ? e : bad("not JSON");
    }
    const id = String(m.phone || "").toLowerCase();
    const name = String(m.name || "").replace(/\s+/g, " ").trim();
    if (!PHONE_ID.test(id)) return bad("bad phone id");
    if (name.length < 2 || name.length > 40) return bad("a name of 2 to 40 characters");
    if (typeof m.body !== "string" || m.body.length > 5000) return bad("bad message");
    const now = Date.now(), hour = Math.floor(now / 3_600_000);
    const row = await env[db].prepare(`INSERT INTO sms_phone(id,name,first_seen,last_seen,hour,hour_count,app_version)
      VALUES(?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,last_seen=excluded.last_seen,
      app_version=COALESCE(NULLIF(excluded.app_version,''),sms_phone.app_version),
      hour_count=CASE WHEN sms_phone.hour=excluded.hour THEN sms_phone.hour_count+1 ELSE 1 END,
      hour=excluded.hour RETURNING blocked,hour_count`)
      .bind(id, name, now, now, hour, String(m.version || "").slice(0, 20)).first();
    if (row.blocked) return new Response("blocked", { status: 403 });
    if (row.hour_count > smsPerHour) return new Response("error: too many SMS this hour", { status: 429 });
    const form = new URLSearchParams({ key: env.SMS_WEBAPP_KEY, user: name });
    for (const f of SMS_FIELDS) if (m[f] !== undefined && m[f] !== null) form.set(f, String(m[f]));
    let res, text;
    try {
      res = await fetch(env.SMS_WEBAPP_URL, { method: "POST", body: form, redirect: "follow" });
      text = (await res.text()).trim();
    } catch (e) {
      return new Response(`error: sheet not reached`, { status: 502 });
    }
    // only the script's own words count: Google's error page also comes with HTTP 200
    const word = text.split(/\s/)[0].replace(/:$/, "");
    if (!["ok", "duplicate", "empty", "error", "unauthorized"].includes(word)) {
      return new Response(`error: the sheet answered HTTP ${res.status}`, { status: 502 });
    }
    if (word === "unauthorized") return new Response("error: the worker's SMS_WEBAPP_KEY is wrong", { status: 502 });
    if (word === "ok") await env[db].prepare("UPDATE sms_phone SET sent=sent+1 WHERE id=?").bind(id).run();
    return new Response(text.slice(0, 200), { status: word === "error" ? 502 : 200 });
  }

  // The model API keys added in the app's control panel (services/app_api/src/keys.ts encrypts them with the same
  // KEYS_SECRET): decrypted only here, only for the agent's token. A key the agent reported at its limit is
  // still listed with its resting time, so the agent can tell how long to skip it.
  async function aesKey(env) {
    const raw = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(env.KEYS_SECRET));
    return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  }
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

  async function keys(request, env, path) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    if (path === "/api/keys" && request.method === "GET") {
      if (!env.KEYS_SECRET) return Response.json({ keys: [] });
      const { results } = await env[db].prepare(`SELECT id,provider,iv,ciphertext,resting_until FROM api_key
        WHERE status!='bad' ORDER BY provider,position,created_at`).all();
      const key = await aesKey(env);
      const out = [];
      for (const r of results) {
        try {
          const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(r.iv) }, key, unb64(r.ciphertext));
          out.push({ id: r.id, provider: r.provider, key: new TextDecoder().decode(plain), restingUntil: r.resting_until });
        } catch {
          /* a key sealed with another secret: left out, never sent broken */
        }
      }
      return Response.json({ keys: out });
    }
    if (path === "/api/keys/report" && request.method === "POST") {
      const m = await jsonBody(request).catch((e) => e);
      if (m instanceof Response) return m;
      const status = String(m.status || "");
      if (!["ok", "limit", "bad"].includes(status) || typeof m.id !== "string") return bad("bad report");
      const until = status === "limit" ? Math.max(Number(m.until) || 0, Date.now() + 60_000) : 0;
      await env[db].prepare(`UPDATE api_key SET status=?,resting_until=?,last_error=?,last_used=? WHERE id=?`)
        .bind(status, until, String(m.error || "").slice(0, 200), Date.now(), m.id).run();
      return Response.json({ ok: true });
    }
    return new Response("not found", { status: 404 });
  }

  async function putModels(request, env) {
    if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
    const m = await jsonBody(request, 400_000).catch((e) => e);
    if (m instanceof Response) return m;
    const rows = Object.entries(m).filter(([p, ids]) => /^[a-z]{3,12}$/.test(p) && Array.isArray(ids));
    if (!rows.length) return bad("no models");
    await env[db].batch(rows.map(([p, ids]) => env[db].prepare(`INSERT INTO agent_model(provider,ids,updated_at) VALUES(?,?,?)
      ON CONFLICT(provider) DO UPDATE SET ids=excluded.ids,updated_at=excluded.updated_at`)
      .bind(p, JSON.stringify(ids.filter((i) => typeof i === "string").slice(0, 500)), Date.now())));
    return Response.json({ ok: true });
  }

  function route(request, env, path) {
    if (path === "/api/ai" || path === "/api/chat/completions") return runAI(request, env);
    if (path === "/api/models") return listModels(request, env);
    if (path === "/api/approval") return saveApproval(request, env);
    if (path === "/api/memory" || path.startsWith("/api/memory/")) return memory(request, env, path);
    if (path === "/api/settings" && request.method === "GET") return settings(request, env);
    if (path === "/api/sms") return sms(request, env);
    if (path === "/api/keys" || path === "/api/keys/report") return keys(request, env, path);
    if (path === "/api/models" && request.method === "PUT") return putModels(request, env);
    return null;
  }

  return { route, ask, isTap, decide, runAI, saveApproval, memory, settings };
}
