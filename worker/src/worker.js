// Telegram webhook for Bindal: the bot is Ultron, Ecom Manager (github.com/bindalbhikan/Ultron).
// Every message in an allowed chat goes to Ultron, which answers in the same chat and asks
// Approve / Reject before it runs anything. The worker also starts the daily reports on time
// (cron triggers), keeps the dashboard's numbers and the Myntra logins (KV "DASH").
//
// Secrets (wrangler secret put): TELEGRAM_BOT_TOKEN, GITHUB_TOKEN, WEBHOOK_SECRET, ALLOWED_CHAT_IDS
// ALLOWED_CHAT_IDS + EXTRA_CHAT_IDS (both secrets: the repo is public) are comma-separated chat ids;
// messages and button taps from any other chat are ignored.
//
// The old command menu (/sale, /vms ... and its buttons) is retired (25 Oct 2026): a command or a
// tap on an old menu still works by going to Ultron, which proposes the same report.

import { makeAgent } from "../agent.js";   // Ultron's worker routes (the same for every seller)

// All bots live in one repo; the daily runs below start its workflows.
const OWNER = "bindalbhikan";
const REPO = "Ultron";

// The workflows the cron triggers start, with the name used when one does not start.
const WORKFLOWS = {
  sale: { workflow: "sale.yml", name: "Daily Sale" },
  vms: { workflow: "vms.yml", name: "Myntra VMS" },
  ajiotat: { workflow: "ajio-tat.yml", name: "AJIO TAT" },
  ajiospf: { workflow: "ajio-spf.yml", name: "AJIO SPF" },
  ajioads: { workflow: "ajio-ads.yml", name: "AJIO Ads / TOT gap" },
  myntraspf: { workflow: "myntra-spf.yml", name: "Myntra SPF" },
  returns: { workflow: "returns.yml", name: "Return Analysis" },
  myntraotp: { workflow: "myntra-otp.yml", name: "Myntra courier OTP" },
  myntrareports: { workflow: "myntra-reports.yml", name: "Myntra daily reports" },
};

// Daily automatic runs, in IST. Cloudflare cron is UTC (IST = UTC + 5:30); each `cron` below
// ("minute hour") must be one of the times the [triggers] in wrangler.toml fire at (one trigger
// can list several hours: the free plan allows 5 triggers). GitHub's own `schedule:` is not
// used: it ran hours late or skipped runs (24 Oct 2026: the 11 AM OTP never ran).
const SCHEDULE = [
  // 7 AM: Myntra report requests - they queue on the portal for a while. The same Myntra report
  // twice within 15 minutes is refused, so the SPF request leaves the order report to 9 AM.
  { ist: "7:00 AM daily", cron: "30 1 * * *", cmd: "sale", label: "SJIT report request", inputs: { sjit_request: "1" } },
  { ist: "7:00 AM daily", cron: "30 1 * * *", cmd: "myntraspf", label: "Myntra SPF report request",
    inputs: { request: "1" } },
  { ist: "7:00 AM on the 15th", cron: "30 1 * * *", day: 15, cmd: "returns", label: "Return analysis report request",
    inputs: { request: "1" } },
  // 9 AM: the SPF masters. AJIO tickets and replies only on Wed + Sat, the other days the master only.
  { ist: "9:00 AM daily", cron: "30 3 * * *", cmd: "myntraspf" },
  { ist: "9:00 AM Wed, Sat", cron: "30 3 * * *", weekdays: [3, 6], cmd: "ajiospf" },
  { ist: "9:00 AM other days", cron: "30 3 * * *", weekdays: [0, 1, 2, 4, 5], cmd: "ajiospf",
    label: "AJIO SPF master update", inputs: { master_only: "1" } },
  // AJIO ads / TOT gap: the 3rd, and the 5th only if the 3rd did not save the report
  { ist: "9:00 AM on the 3rd", cron: "30 3 * * *", day: 3, cmd: "ajioads" },
  { ist: "9:00 AM on the 5th", cron: "30 3 * * *", day: 5, cmd: "ajioads", label: "AJIO Ads / TOT gap (if missed)",
    inputs: { if_missing: "1" } },
  // 10 AM: Myntra courier OTPs and yesterday's Myntra reports; 11 AM: the OTPs again for couriers
  // that had no trip yet at 10 (sent only when a new code came)
  { ist: "10:00 AM daily", cron: "30 4 * * *", cmd: "myntraotp" },
  { ist: "10:00 AM daily", cron: "30 4 * * *", cmd: "myntrareports" },
  { ist: "11:00 AM daily", cron: "30 5 * * *", cmd: "myntraotp", label: "Myntra OTP retry", inputs: { retry: "1" } },
  { ist: "2:00 PM on the 15th", cron: "30 8 * * *", day: 15, cmd: "returns" },
  { ist: "3:30 PM daily", cron: "0 10 * * *", cmd: "sale" },
  { ist: "5:30 PM daily", cron: "0 12 * * *", cmd: "vms" },
  { ist: "5:30 PM daily", cron: "0 12 * * *", cmd: "ajiotat" },
];

const WELCOME = [
  "🤖 <b>Ultron · Ecom Manager</b>",
  "",
  "Write to me in plain words, e.g.",
  "• how many orders yesterday?",
  "• where is order FN2511505146?",
  "• which orders are due today?",
  "• run the sale report for 1 to 7 Oct",
  "",
  "Anything I would run, I ask first with Approve / Reject. The daily reports keep coming on their own.",
  "",
  "<code>/dashboard</code>: dashboard sign-in link, valid 10 min",
].join("\n");
// The old menu's buttons under the chat box send these texts: answered with the welcome, which
// also takes that keyboard away.
const OLD_KEYBOARD = new Set(["📋 Menu", "📊 Status"]);
const BOT_COMMANDS = [
  { command: "start", description: "What Ultron can do" },
  { command: "dashboard", description: "Dashboard sign-in link (10 min)" },
];

function allowedChat(env, chatId) {
  const allowed = `${env.ALLOWED_CHAT_IDS || ""},${env.EXTRA_CHAT_IDS || ""}`.split(",").map((s) => s.trim()).filter(Boolean);
  return allowed.includes(String(chatId));
}

export default {
  async fetch(request, env, ctx) {
    const path = new URL(request.url).pathname;
    const agentApi = agent.route(request, env, path);       // its own methods (GET / PUT memory too)
    if (agentApi) return agentApi;
    if (request.method !== "POST") return new Response("ok");
    if (path.startsWith("/api/push/")) return pushDashboard(request, env, path.slice("/api/push/".length));
    if (path === "/api/myntra-session") return saveMyntraSession(request, env);
    if (path === "/api/myntra-session/read") return readMyntraSession(request, env);
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json().catch(() => null);

    // A tap on a button: Ultron's Approve / Reject, or a button of the retired menu
    const cb = update?.callback_query;
    if (cb?.message) {
      if (!allowedChat(env, cb.message.chat.id)) {
        console.log(`ignored button ${cb.data} from chat ${cb.message.chat.id} user ${cb.from?.id}`);
        return new Response("ok");
      }
      ctx.waitUntil(onTap(env, cb));
      return new Response("ok");
    }

    const msg = update?.message;
    const text = msg?.text?.trim();
    if (!text) return new Response("ok");
    if (!allowedChat(env, msg.chat.id)) {
      console.log(`ignored ${text.slice(0, 40)} from chat ${msg.chat.id} (${msg.chat.type} ${msg.chat.title || ""}) user ${msg.from?.id}`);
      return new Response("ok");
    }
    // Reply after the 200 so Telegram never retries a slow GitHub call.
    ctx.waitUntil(onMessage(env, msg, text));
    return new Response("ok");
  },

  // Cron trigger: start the reports scheduled for this time. With no chat_id input the
  // workflow sends its report to its default TELEGRAM_CHAT_ID, same as a scheduled run.
  async scheduled(event, env, ctx) {
    // Matched on the UTC minute + hour the trigger fired at: one trigger lists several hours
    // ("30 1,3,4,5,8 * * *"), and Cloudflare may hand the cron text back in another form.
    const at = (c) => String(c).trim().split(/\s+/).slice(0, 2).map(Number).join(" ");
    const fired = new Date(event.scheduledTime);
    const now = `${fired.getUTCMinutes()} ${fired.getUTCHours()}`;
    // `day` = IST day of the month, `weekdays` = IST weekdays (0 Sunday .. 6 Saturday): the free
    // plan allows 5 cron triggers, so monthly / weekly runs ride on daily ones
    const ist = new Date(event.scheduledTime + 5.5 * 3600 * 1000);
    const due = SCHEDULE.filter((s) => at(s.cron) === now && (!s.day || s.day === ist.getUTCDate())
      && (!s.weekdays || s.weekdays.includes(ist.getUTCDay())));
    ctx.waitUntil(
      Promise.all(
        due.map(async (s) => {
          const wf = WORKFLOWS[s.cmd];
          try {
            const res = await dispatch(env, wf.workflow, s.inputs || {});
            console.log(`cron ${event.cron} -> ${wf.workflow} ${res.status}`);
            if (res.status !== 204) throw new Error(`GitHub said ${res.status}: ${(await res.text()).slice(0, 200)}`);
          } catch (e) {
            console.log(`cron ${s.cmd} failed: ${e.stack || e}`);
            const chat = String(env.ALLOWED_CHAT_IDS || "").split(",")[0].trim();
            if (chat) {
              await sendMessage(env, chat, `❌ <b>${s.label || wf.name} did not start</b>\n<i>auto run, ${s.ist}</i>\n\n<code>${esc(e.message)}</code>`);
            }
          }
        })
      )
    );
  },
};

async function onMessage(env, msg, text) {
  const chatId = msg.chat.id;
  const command = text.startsWith("/") ? text.split(/\s+/)[0].slice(1).split("@")[0].toLowerCase() : "";
  try {
    if (command === "start" || command === "help" || command === "menu" || OLD_KEYBOARD.has(text)) {
      // also replaces the old command list in Telegram's menu with Ultron's two commands
      await telegram(env, "setMyCommands", { commands: BOT_COMMANDS });
      return await sendMessage(env, chatId, WELCOME, msg.message_id, { remove_keyboard: true });
    }
    if (command === "dashboard") return await sendDashboardLink(env, chatId, msg.message_id);
    // anything else, an old command like /sale included: Ultron (ultron.agents.chat)
    return await agent.ask(env, chatId, msg.message_id, text);
  } catch (e) {
    console.log(`message failed: ${e.stack || e}`);
    await sendMessage(env, chatId, `❌ <b>Error</b>\n\n<code>${esc(e.message)}</code>`, msg.message_id);
  }
}

async function onTap(env, cb) {
  const data = String(cb.data || "");
  if (agent.isTap(data)) return agent.decide(env, cb, data);
  // a button of the retired menu: say so, and take the old buttons off that message
  await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id, show_alert: true,
                                              text: "This menu is retired. Write to Ultron in plain words, e.g. \"run the sale report\"." });
  return telegram(env, "editMessageReplyMarkup", { chat_id: cb.message.chat.id, message_id: cb.message.message_id,
                                                  reply_markup: { inline_keyboard: [] } });
}

// The bots' latest numbers for the dashboard, stored in KV under their key.
const DASH_KEYS = new Set(["sale", "sale_today", "vms", "vms_erp", "ajio_tat", "ajio_spf",
                           "returns", "returns_year", "myntra_spf", "ajio_ads", "run_sale", "run_vms", "run_ajio_tat", "run_ajio_spf", "run_returns", "run_myntra_spf", "run_ajio_ads"]);

async function pushDashboard(request, env, key) {
  const token = env.DASHBOARD_TOKEN || "";
  if (!token || request.headers.get("Authorization") !== `Bearer ${token}`) return new Response("forbidden", { status: 403 });
  if (!DASH_KEYS.has(key)) return new Response("unknown key", { status: 404 });
  const body = await request.text();
  if (body.length > 1_000_000) return new Response("too large", { status: 413 });
  try {
    JSON.parse(body);
  } catch {
    return new Response("not JSON", { status: 400 });
  }
  await env.DASH.put(key, body);
  return new Response("stored");
}

// Myntra partner portal login cookies, one per seller account (?account=main|dbcc|fmcc; main =
// the SJIT report's account). Saved by scripts/myntra_session.py when someone pastes a new login
// (announced on Telegram) and by the bot's runs with the cookies the portal renewed (quiet).
// Same DASHBOARD_TOKEN; kept in KV under keys the dashboard never reads.
const MYNTRA_ACCOUNTS = { main: "myntra_session", dbcc: "myntra_session_dbcc", fmcc: "myntra_session_fmcc" };
const myntraAccount = (request) => new URL(request.url).searchParams.get("account") || "main";

function authorised(request, env) {
  const token = env.DASHBOARD_TOKEN || "";
  return token && request.headers.get("Authorization") === `Bearer ${token}`;
}

async function saveMyntraSession(request, env) {
  if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
  const account = myntraAccount(request);
  const key = MYNTRA_ACCOUNTS[account];
  if (!key) return new Response("unknown account", { status: 404 });
  const body = await request.text();
  if (body.length > 100_000) return new Response("too large", { status: 413 });
  let data;
  try {
    data = JSON.parse(body);
  } catch {
    return new Response("not JSON", { status: 400 });
  }
  if (!Array.isArray(data.cookies) || !data.cookies.length) return new Response("no cookies", { status: 400 });
  await env.DASH.put(key, body);
  const chat = String(env.ALLOWED_CHAT_IDS || "").split(",")[0].trim();
  if (chat && data.source !== "bot") {   // the bot saving renewed cookies after a run stays quiet
    const ends = data.expiresAt ? new Date(data.expiresAt).toLocaleString("en-IN", { timeZone: "Asia/Kolkata",
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "not given";
    await sendMessage(env, chat, `🔐 <b>Myntra ${account.toUpperCase()} session saved</b>\n<i>new partner portal login</i>\n\n` +
      `Cookies: ${data.cookies.length}\nLogin expires: ${esc(ends)}`);
  }
  return new Response("stored");
}

async function readMyntraSession(request, env) {
  if (!authorised(request, env)) return new Response("forbidden", { status: 403 });
  const key = MYNTRA_ACCOUNTS[myntraAccount(request)];
  if (!key) return new Response("unknown account", { status: 404 });
  const body = await env.DASH.get(key);
  return body ? new Response(body, { headers: { "Content-Type": "application/json" } }) : new Response("none", { status: 404 });
}

// ------------------------------------------------------------------ Ultron
// The agent's routes are worker/agent.js of the Ultron repo, the same for every seller. Plain text in an
// allowed chat goes to the agent-chat workflow (ultron.agents.chat), which answers in the same chat.
// The agent can only read; anything it wants done it proposes with POST /api/approval, and only an
// Approve tap starts it - one of AGENT_ACTIONS (wrangler.toml, the same list as agent.toml), with
// only the inputs listed there. /api/ai serves its model (Workers AI, free daily allocation), and
// /api/memory its memory.
const agent = makeAgent({ repo: `${OWNER}/${REPO}`, token: (env) => env.DASHBOARD_TOKEN, allowedChat, kv: "DASH",
                          userAgent: "bindal-ultron-worker" });

// Dashboard sign-in: a link carrying a token signed with SESSION_KEY (shared with the dashboard
// worker), valid 10 minutes and usable once. Only allowed chats ever reach this.
async function sendDashboardLink(env, chatId, replyTo) {
  if (!env.SESSION_KEY || !env.DASHBOARD_PAGE) {
    return sendMessage(env, chatId, "🖥 <b>Dashboard</b>\n\nSign-in is not set up yet.", replyTo);
  }
  const claim = { kind: "login", chat: String(chatId), nonce: crypto.randomUUID(), exp: Date.now() + 10 * 60000 };
  const body = b64url(new TextEncoder().encode(JSON.stringify(claim)));
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.SESSION_KEY), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)));
  const link = `${env.DASHBOARD_PAGE.replace(/\/$/, "")}/login?t=${body}.${b64url(sig)}`;
  return sendMessage(env, chatId, "🖥 <b>Dashboard</b>\n\nTap below to sign in on this device.\n<i>Link works once, for 10 minutes.</i>", replyTo,
                     { inline_keyboard: [[{ text: "Open dashboard", url: link }]] });
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function dispatch(env, workflow, inputs) {
  return github(env, `/repos/${OWNER}/${REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main", inputs }),
  });
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function github(env, path, init = {}) {
  return fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "bindal-ultron-worker",
    },
  });
}

async function telegram(env, method, body) {
  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) console.log(`${method} ${res.status}: ${await res.text()}`);
  return res;
}

function sendMessage(env, chatId, text, replyTo, markup) {
  return telegram(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    ...(replyTo ? { reply_parameters: { message_id: replyTo, allow_sending_without_reply: true } } : {}),
    disable_web_page_preview: true,
    ...(markup ? { reply_markup: markup } : {}),
  });
}
