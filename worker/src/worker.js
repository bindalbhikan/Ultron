// Telegram webhook for Bindal (@bindal_exports_bot): a button menu, portal by portal, that starts the
// report workflows of github.com/bindalbhikan/Ultron, and Ultron, Ecom Manager, for everything typed
// in plain words. The worker also starts the daily reports on time (cron triggers) and keeps the
// dashboard's numbers, the Myntra logins and Ultron's memory and approvals (KV "DASH").
//
// Secrets (wrangler secret put): TELEGRAM_BOT_TOKEN, GITHUB_TOKEN, WEBHOOK_SECRET, ALLOWED_CHAT_IDS
// ALLOWED_CHAT_IDS + EXTRA_CHAT_IDS (both secrets: the repo is public) are comma-separated chat ids;
// messages and button taps from any other chat are ignored. Each run's report goes to the chat
// that asked for it (workflows with a chat_id input).
//
// Every reply is written for a phone: a bold heading line, a blank line, short lines below,
// and at most two short buttons per row.

import { makeAgent } from "../agent.js";   // Ultron's worker routes (the same for every seller)

const OWNER = "bindalbhikan";
const REPO = "Ultron";
const DATE = /^\d{4}-\d{2}-\d{2}$/;

const none = (usage) => (args) => (args.length === 0 ? {} : `Use ${usage}`);
const oneDate = (key, usage) => (args) => {
  if (args.length === 0) return {};
  if (args.length === 1 && DATE.test(args[0])) return { [key]: args[0] };
  return `Use ${usage}`;
};

// Each command maps to one workflow. `inputs` turns the command's arguments into workflow_dispatch
// inputs, or returns a string error to show. `chat` = the workflow takes a chat_id (its report comes
// back to the chat that asked). `minutes` is the usual run time until the workflow has runs to measure.
// `portal` groups it in /status and /help.
const COMMANDS = {
  // Myntra
  vms: { workflow: "vms.yml", icon: "📹", name: "Myntra VMS", portal: "myntra", chat: true, minutes: 2,
         examples: ["/vms", "/vms 2026-10-01 2026-10-07", "/vms erp"],
         inputs: (args) => (args.length === 1 && args[0].toLowerCase() === "erp" ? { erp_only: "1" } : dateRange(args)) },
  vmspic: { workflow: "vms.yml", icon: "🖼", name: "VMS sheet photo", portal: "myntra", chat: true, picture: true, minutes: 4,
            examples: ["/vmspic", "/vmspic 2026-09"], inputs: monthArg },
  myntraspf: { workflow: "myntra-spf.yml", icon: "🧾", name: "Myntra SPF", portal: "myntra", chat: true, minutes: 30,
               examples: ["/myntraspf"], inputs: none("/myntraspf") },
  myntraotp: { workflow: "myntra-otp.yml", icon: "🔐", name: "Myntra courier OTP", portal: "myntra", minutes: 1,
               examples: ["/myntraotp"], inputs: none("/myntraotp") },
  myntrareports: { workflow: "myntra-reports.yml", icon: "📊", name: "Myntra daily reports", portal: "myntra", minutes: 8,
                   examples: ["/myntrareports", "/myntrareports 2026-10-23"],
                   inputs: oneDate("date", "/myntrareports or /myntrareports YYYY-MM-DD") },
  myntrazerotd: { workflow: "myntra-zero-td.yml", icon: "🏷", name: "Myntra zero TD", portal: "myntra", minutes: 3,
                  examples: ["/myntrazerotd"], inputs: none("/myntrazerotd") },
  myntratat: { workflow: "myntra-tat.yml", icon: "🚚", name: "Myntra courier scorecard", portal: "myntra", minutes: 3,
               examples: ["/myntratat"], inputs: none("/myntratat") },
  // Flipkart
  fktat: { workflow: "flipkart-tat.yml", icon: "📦", name: "Flipkart TAT", portal: "flipkart", chat: true, minutes: 6,
           examples: ["/fktat"], inputs: none("/fktat") },
  // AJIO
  ajiotat: { workflow: "ajio-tat.yml", icon: "📦", name: "AJIO TAT", portal: "ajio", chat: true, minutes: 2,
             examples: ["/ajiotat", "/ajiotat 3"],
             inputs: (args) => {
               if (args.length === 0) return {};
               if (args.length === 1 && /^\d{1,2}$/.test(args[0])) return { days: args[0] };
               return "Days must be a number, e.g. /ajiotat 3";
             } },
  ajiospf: { workflow: "ajio-spf.yml", icon: "🧾", name: "AJIO SPF", portal: "ajio", chat: true, minutes: 13,
             examples: ["/ajiospf dry", "/ajiospf master", "/ajiospf"],
             inputs: (args) => {
               if (args.length === 0) return {};
               const a = args.length === 1 ? args[0].toLowerCase() : "";
               if (a === "dry") return { dry_run: "1" };
               if (a === "master") return { master_only: "1" };
               return "Use /ajiospf, /ajiospf dry or /ajiospf master";
             } },
  ajioads: { workflow: "ajio-ads.yml", icon: "📣", name: "AJIO Ads / TOT gap", portal: "ajio", chat: true, minutes: 3,
             examples: ["/ajioads"], inputs: none("/ajioads") },
  // All channels (OMSGuru)
  sale: { workflow: "sale.yml", icon: "📈", name: "Daily Sale", portal: "all", chat: true, minutes: 1,
          examples: ["/sale", "/sale today", "/sale 2026-10-01 2026-10-07"],
          inputs: (args) => (args.length === 1 && args[0].toLowerCase() === "today" ? { today: "1" } : dateRange(args)) },
  salepic: { workflow: "sale.yml", icon: "🖼", name: "Sale sheet photo", portal: "all", chat: true, picture: true, minutes: 4,
             examples: ["/salepic", "/salepic 2026-09"], inputs: monthArg },
  morning: { workflow: "morning.yml", icon: "🌅", name: "Morning report", portal: "all", chat: true, minutes: 2,
             examples: ["/morning", "/morning 2026-10-23"], inputs: oneDate("day", "/morning or /morning YYYY-MM-DD") },
  sla: { workflow: "sla.yml", icon: "⏰", name: "SLA warning", portal: "all", minutes: 2,
         examples: ["/sla"], inputs: none("/sla") },
  stock: { workflow: "stock.yml", icon: "📉", name: "Stock-out alert", portal: "all", minutes: 4,
           examples: ["/stock"], inputs: none("/stock") },
  labels: { workflow: "labels.yml", icon: "🏷", name: "Label check", portal: "all", minutes: 3,
            examples: ["/labels"], inputs: none("/labels") },
  listings: { workflow: "listings.yml", icon: "🧩", name: "Listing health", portal: "all", minutes: 6,
              examples: ["/listings"], inputs: none("/listings") },
  invpush: { workflow: "inv-push.yml", icon: "🔄", name: "Inventory push", portal: "all", minutes: 3,
             examples: ["/invpush dry", "/invpush"],
             inputs: (args) => {
               if (args.length === 0) return {};
               if (args.length === 1 && args[0].toLowerCase() === "dry") return { dry_run: "1" };
               return "Use /invpush or /invpush dry";
             } },
  evening: { workflow: "evening.yml", icon: "🌙", name: "Evening summary", portal: "all", minutes: 3,
             examples: ["/evening"], inputs: none("/evening") },
  // Reports & MIS
  returns: { workflow: "returns.yml", icon: "↩️", name: "Return Analysis", portal: "reports", chat: true, minutes: 25,
             examples: ["/returns", "/returns 2026-09"],
             inputs: (args) => {
               if (args.length === 0) return {};
               if (args.length === 1 && /^\d{4}-\d{2}$/.test(args[0])) return { month: args[0] };
               return "Month must be YYYY-MM, e.g. /returns 2026-09";
             } },
  weekly: { workflow: "weekly.yml", icon: "📅", name: "Weekly review", portal: "reports", minutes: 5,
            examples: ["/weekly"], inputs: none("/weekly") },
  mis: { workflow: "mis.yml", icon: "📆", name: "Monthly MIS", portal: "reports", minutes: 6,
         examples: ["/mis", "/mis 2026-10-02"], inputs: oneDate("day", "/mis or /mis YYYY-MM-DD") },
  deadstock: { workflow: "deadstock.yml", icon: "🪦", name: "Dead stock", portal: "reports", minutes: 6,
               examples: ["/deadstock"], inputs: none("/deadstock") },
};

const PORTALS = [["myntra", "🛍 Myntra"], ["ajio", "🟠 AJIO"], ["all", "📦 All channels (OMSGuru)"], ["reports", "📊 Reports & MIS"]];

function monthArg(args) {
  if (args.length === 0) return { snapshot: "current" };
  if (args.length === 1 && /^\d{4}-\d{2}$/.test(args[0])) return { snapshot: args[0] };
  return "Month must be YYYY-MM, e.g. 2026-09";
}

// Every automatic run, in IST. The worker is the only scheduler: GitHub's own `schedule:` started
// runs late or not at all (25 Oct 2026: morning, stock-out and listings never ran from it).
// Cloudflare cron is UTC (IST = UTC + 5:30); each `cron` below ("minute hour") must be one of the
// times the [triggers] in wrangler.toml fire at. One trigger lists many hours (the free plan allows
// 5): ":30" past the hours, ":00" past the hours, and Monday 4:45 UTC.
const INV_PUSH_HOURS = [0, 3, 6, 9, 12, 15, 18, 21];   // UTC: 6 AM, 9 AM ... 3 AM IST
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
  // Myntra zero TD: styles live at MRP on www.myntra.com, Monday to Saturday
  ...[["10:00 AM", 4], ["2:00 PM", 8], ["5:00 PM", 11]].map(([ist, h]) => (
    { ist: `${ist} Mon-Sat`, cron: `30 ${h} * * *`, weekdays: [1, 2, 3, 4, 5, 6], cmd: "myntrazerotd" })),
  { ist: "2:00 PM on the 15th", cron: "30 8 * * *", day: 15, cmd: "returns" },
  { ist: "3:30 PM daily", cron: "0 10 * * *", cmd: "sale" },
  { ist: "5:30 PM daily", cron: "0 12 * * *", cmd: "vms" },
  { ist: "5:30 PM daily", cron: "0 12 * * *", cmd: "ajiotat" },
  // the reports that used GitHub's schedule until 25 Oct 2026
  { ist: "9:30 AM daily", cron: "0 4 * * *", cmd: "morning" },
  { ist: "10:00 AM daily", cron: "30 4 * * *", cmd: "stock" },
  { ist: "10:15 AM Monday", cron: "45 4 * * *", weekdays: [1], cmd: "weekly" },
  { ist: "11:00 AM on the 1st", cron: "30 5 * * *", day: 1, cmd: "deadstock" },
  { ist: "11:00 AM on the 2nd", cron: "30 5 * * *", day: 2, cmd: "mis" },
  { ist: "11:30 AM daily", cron: "0 6 * * *", cmd: "listings" },
  { ist: "12:00 PM daily", cron: "30 6 * * *", cmd: "sla" },
  { ist: "3:00 PM daily", cron: "30 9 * * *", cmd: "sla" },
  { ist: "6:00 PM daily", cron: "30 12 * * *", cmd: "labels" },
  { ist: "6:00 PM daily", cron: "30 12 * * *", cmd: "fktat" },
  { ist: "6:30 PM daily", cron: "0 13 * * *", cmd: "myntratat" },
  { ist: "8:00 PM daily", cron: "30 14 * * *", cmd: "evening" },
  ...INV_PUSH_HOURS.map((h) => ({ ist: "every 3 hours from 6 AM", cron: `30 ${h} * * *`, cmd: "invpush" })),
];

// The button menu. Every screen edits the same message. Button data (64 bytes at most):
//   "m:<screen>" open a screen · "r:<command line>" start a run · "c:<command line>" ask first
//   "a:<question>" ask Ultron · "st" status · "db" dashboard · "hp" help
const back = (to = "main") => [["⬅️ Back", `m:${to}`]];
const SCREENS = {
  main: {
    title: "🏠 <b>Bindal Exports</b>\n<i>Ultron · Ecom Manager</i>\n\n⚡ Quick runs, or choose a portal 👇\n<i>or just write to me in plain words</i>",
    rows: [
      // the runs used most, one tap
      [["📈 Sale · yesterday", "r:sale"], ["📈 Sale · today", "r:sale today"]],
      [["📹 VMS · today", "r:vms"], ["📦 AJIO TAT · today", "r:ajiotat"]],
      [["🖼 Sale sheet photo", "r:salepic"], ["🖼 VMS sheet photo", "r:vmspic"]],
      // everything else, portal by portal
      [["🛍 Myntra", "m:myntra"], ["🟠 AJIO", "m:ajio"]],
      [["🛒 Flipkart", "m:flipkart"], ["📦 All channels", "m:all"]],
      [["📊 Reports & MIS", "m:reports"], ["📋 Status", "st"]],
      [["🖥 Dashboard", "db"], ["🤖 Ask Ultron / Help", "hp"]],
    ],
  },
  myntra: {
    title: "🛍 <b>Myntra</b>\n<i>MAIN · PPMP · DBCC · FMCC</i>\n\nWhat do you need?",
    rows: [
      [["📹 VMS", "m:vms"], ["🧾 Myntra SPF", "r:myntraspf"]],
      [["🔐 Courier OTP", "r:myntraotp"], ["📊 Daily reports", "r:myntrareports"]],
      [["🚚 Courier scorecard", "r:myntratat"], ["🔑 Login check", "a:mlogin"]],
      [["📈 Orders yesterday", "a:myn_orders"], ["🏷 Zero TD", "r:myntrazerotd"]],
      back(),
    ],
  },
  vms: {
    title: "📹 <b>Myntra VMS</b>\n<i>Packing video check</i>\n\nWhich SLA dates?",
    rows: [
      [["Today", "r:vms"], ["Last 7 days", "r:vms @week"]],
      [["This month", "r:vms @month"], ["🖼 Sheet photo", "r:vmspic"]],
      [["🏭 ERP vs VMS", "r:vms erp"]],
      back("myntra"),
    ],
  },
  ajio: {
    title: "🟠 <b>AJIO</b>\n\nWhat do you need?",
    rows: [
      [["📦 TAT + pickups", "m:tat"], ["🧾 SPF claims", "m:spf"]],
      [["📣 Ads / TOT gap", "r:ajioads"], ["📈 Orders yesterday", "a:ajio_orders"]],
      back(),
    ],
  },
  tat: {
    title: "📦 <b>AJIO TAT</b>\n<i>Dispatch TAT + courier pickup</i>\n\nWhich order dates?",
    rows: [
      [["Today", "r:ajiotat"], ["Last 3 days", "r:ajiotat 3"]],
      [["Last 7 days", "r:ajiotat 7"]],
      back("ajio"),
    ],
  },
  spf: {
    title: "🧾 <b>AJIO SPF</b>\n<i>SPF tickets + follow-ups</i>\n\n🧪 Dry = only lists\n📒 Master = sheet only\n⚠️ LIVE = posts on AJIO",
    rows: [
      [["🧪 Dry run", "r:ajiospf dry"], ["📒 Master only", "r:ajiospf master"]],
      [["⚠️ LIVE", "c:ajiospf"]],
      back("ajio"),
    ],
  },
  flipkart: {
    title: "🛒 <b>Flipkart</b>\n<i>incl. FBF</i>\n\nWhat do you need?",
    rows: [
      [["📈 Orders yesterday", "a:fk_orders"], ["⏰ Due today", "a:fk_due"]],
      [["📦 Flipkart TAT", "r:fktat"]],
      [["📈 Sale report", "m:sale"], ["↩️ Return analysis", "m:returns"]],
      back(),
    ],
  },
  all: {
    title: "📦 <b>All channels</b>\n<i>OMSGuru: every marketplace</i>\n\nWhat do you need?",
    rows: [
      [["📈 Sale", "m:sale"], ["🌅 Morning report", "r:morning"]],
      [["⏰ SLA warning", "r:sla"], ["📉 Stock-out", "r:stock"]],
      [["🏷 Label check", "r:labels"], ["🧩 Listing health", "r:listings"]],
      [["🔄 Inventory push", "m:inv"], ["🌙 Evening summary", "r:evening"]],
      back(),
    ],
  },
  sale: {
    title: "📈 <b>Daily Sale</b>\n<i>OMSGuru + FBF + SJIT</i>\n\nWhich days?",
    rows: [
      [["Yesterday", "r:sale"], ["Today", "r:sale today"]],
      [["Last 7 days", "r:sale @week"], ["This month", "r:sale @month"]],
      [["🖼 Sheet photo", "r:salepic"]],
      back("all"),
    ],
  },
  inv: {
    title: "🔄 <b>Inventory push</b>\n<i>OMSGuru Push Inventory, every channel</i>\n\nRuns by itself every 3 hours.",
    rows: [
      [["🧪 Dry run", "r:invpush dry"], ["⚠️ Push now", "c:invpush"]],
      back("all"),
    ],
  },
  reports: {
    title: "📊 <b>Reports & MIS</b>\n\nWhich report?",
    rows: [
      [["📅 Weekly review", "r:weekly"], ["📆 Monthly MIS", "r:mis"]],
      [["↩️ Return analysis", "m:returns"], ["🪦 Dead stock", "r:deadstock"]],
      [["📣 AJIO Ads gap", "r:ajioads"]],
      back(),
    ],
  },
  returns: {
    title: "↩️ <b>Return Analysis</b>\n<i>Myntra x3 + Ajio + Flipkart, Drive + Telegram</i>\n\n" +
      "Last month: sale 1st-last day, returns up to the 14th. Runs by itself on the 15th, 2 PM.",
    rows: [
      [["Last month", "r:returns"]],
      back("reports"),
    ],
  },
};
// "c:" buttons: what the run does, and the screen Cancel goes back to
const CONFIRM = {
  ajiospf: { text: "⚠️ <b>AJIO SPF · LIVE</b>\n\nRaises tickets and posts replies on AJIO.\nStart it?", back: "spf" },
  invpush: { text: "⚠️ <b>Inventory push · now</b>\n\nPushes inventory to every channel on OMSGuru.\nStart it?", back: "inv" },
};
// "a:" buttons: a question for Ultron, sent as if typed
const ASK = {
  mlogin: "Check the Myntra portal logins (MAIN, DBCC, FMCC): logged in or out, and when they run out.",
  myn_orders: "How many Myntra orders came yesterday, account-wise, with cancels?",
  ajio_orders: "How many AJIO orders came yesterday, with cancels?",
  fk_orders: "How many Flipkart orders came yesterday, with cancels?",
  fk_due: "Which Flipkart orders are due today or overdue and not ready to ship?",
};

// Always-visible buttons under the chat box; their text arrives as a normal message.
const KEYBOARD_MENU = "📋 Menu";
const KEYBOARD_STATUS = "📊 Status";
const REPLY_KEYBOARD = {
  keyboard: [[{ text: KEYBOARD_MENU }, { text: KEYBOARD_STATUS }]],
  resize_keyboard: true,
  is_persistent: true,
};
// the bot's command list in Telegram (setMyCommands on /start; worker/setup.ps1 sets the same)
const BOT_COMMANDS = [
  ["menu", "Buttons for every portal and report"], ["status", "Last run of each report"],
  ["sale", "Daily sale (optional: today, or from to dates)"], ["salepic", "Sale sheet photo (optional: YYYY-MM)"],
  ["vms", "Myntra VMS (optional: dates, or erp)"], ["vmspic", "VMS sheet photo (optional: YYYY-MM)"],
  ["ajiotat", "AJIO TAT (optional: days)"], ["ajiospf", "AJIO SPF (optional: dry, master)"],
  ["myntraspf", "Myntra SPF master"], ["returns", "Return analysis (optional: YYYY-MM)"],
  ["dashboard", "Dashboard sign-in link (10 min)"], ["help", "All commands, and how to ask Ultron"],
].map(([command, description]) => ({ command, description }));

function dateRange(args) {
  if (args.length === 0) return {};
  if (args.length > 2 || !args.every((a) => DATE.test(a))) return "Dates must be YYYY-MM-DD";
  return args.length === 2 ? { from: args[0], to: args[1] } : { from: args[0] };
}

// "@week" / "@month" from the buttons become dates, in IST. Sale reports end yesterday,
// the VMS report (by SLA date) ends today.
function expandPeriod(name, args) {
  if (args.length !== 1 || !args[0].startsWith("@")) return args;
  const ist = (d) => new Date(d.getTime() + 330 * 60000).toISOString().slice(0, 10);
  const today = new Date();
  const end = name === "sale" ? new Date(today.getTime() - 86400000) : today;
  const from = args[0] === "@week" ? ist(new Date(end.getTime() - 6 * 86400000)) : `${ist(end).slice(0, 8)}01`;
  return [from, ist(end)];
}

function scheduleOf(key) {
  return [...new Set(SCHEDULE.filter((s) => s.cmd === key && !s.inputs).map((s) => s.ist))];
}

function helpText() {
  const blocks = PORTALS.map(([key, title]) => [
    `<b>${title}</b>`,
    ...Object.values(COMMANDS).filter((c) => c.portal === key)
      .map((c) => `${c.icon} ${c.name}: ${c.examples.map((e) => `<code>${e}</code>`).join(" ")}`),
  ].join("\n"));
  return [
    "❓ <b>Help</b>",
    "",
    `Tap <b>${KEYBOARD_MENU}</b> below, type a command, or write to <b>Ultron</b> in plain words, e.g.`,
    "<i>how many orders yesterday? · where is order FN2511505146? · check the Myntra logins</i>",
    "Anything Ultron would run, it asks first with Approve / Reject.",
    "",
    ...blocks.flatMap((b) => [b, ""]),
    "🖥 <code>/dashboard</code> sign-in link, valid 10 min · 📋 <code>/status</code> last runs",
  ].join("\n");
}

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

    // A tap on a button: the menu, or Ultron's Approve / Reject
    const cb = update?.callback_query;
    if (cb?.message) {
      if (!allowedChat(env, cb.message.chat.id)) {
        console.log(`ignored button ${cb.data} from chat ${cb.message.chat.id} user ${cb.from?.id}`);
        return new Response("ok");
      }
      ctx.waitUntil(handleTap(env, cb));
      return new Response("ok");
    }

    const msg = update?.message;
    let text = msg?.text?.trim();
    if (text === KEYBOARD_MENU) text = "/menu";
    if (text === KEYBOARD_STATUS) text = "/status";
    if (!text) return new Response("ok");
    if (!allowedChat(env, msg.chat.id)) {
      console.log(`ignored ${text.slice(0, 40)} from chat ${msg.chat.id} (${msg.chat.type} ${msg.chat.title || ""}) user ${msg.from?.id}`);
      return new Response("ok");
    }
    // plain words go to Ultron (ultron.agents.chat); a command runs here.
    // Reply after the 200 so Telegram never retries a slow GitHub call.
    ctx.waitUntil(text.startsWith("/") ? handle(env, msg.chat.id, msg.message_id, text)
                                       : agent.ask(env, msg.chat.id, msg.message_id, text));
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
          const cmd = COMMANDS[s.cmd];
          try {
            const res = await dispatch(env, cmd, s.inputs || {});
            console.log(`cron ${event.cron} -> ${cmd.workflow} ${res.status}`);
            if (res.status !== 204) throw new Error(`GitHub said ${res.status}: ${(await res.text()).slice(0, 200)}`);
          } catch (e) {
            console.log(`cron ${s.cmd} failed: ${e.stack || e}`);
            const chat = String(env.ALLOWED_CHAT_IDS || "").split(",")[0].trim();
            if (chat) {
              await sendMessage(env, chat, `❌ <b>${s.label || cmd.name} did not start</b>\n<i>auto run, ${s.ist}</i>\n\n<code>${esc(e.message)}</code>`);
            }
          }
        })
      )
    );
  },
};

async function handleTap(env, cb) {
  const chatId = cb.message.chat.id;
  const messageId = cb.message.message_id;
  const data = String(cb.data || "");
  const answer = (text) => telegram(env, "answerCallbackQuery", { callback_query_id: cb.id, ...(text ? { text } : {}) });
  const show = (text, rows) =>
    telegram(env, "editMessageText", { chat_id: chatId, message_id: messageId, text, parse_mode: "HTML",
                                       disable_web_page_preview: true, reply_markup: keyboard(rows) });

  if (agent.isTap(data)) return agent.decide(env, cb, data);        // Ultron's Approve / Reject
  if (data.startsWith("m:")) {
    await answer();
    const screen = SCREENS[data.slice(2)] || SCREENS.main;
    return show(screen.title, screen.rows);
  }
  if (data === "st") {
    await answer("Checking…");
    return show(await statusText(env), [[["🔄 Refresh", "st"], ["🏠 Menu", "m:main"]]]);
  }
  if (data === "db") {
    await answer();
    return sendDashboardLink(env, chatId, undefined);
  }
  if (data === "hp") {
    await answer();
    return show(helpText(), [back()[0]]);
  }
  if (data.startsWith("a:")) {
    const question = ASK[data.slice(2)];
    await answer(question ? "Asking Ultron…" : undefined);
    return question ? agent.ask(env, chatId, undefined, question) : undefined;
  }
  if (data.startsWith("c:")) {
    await answer();
    const line = data.slice(2);
    const c = CONFIRM[line.split(" ")[0]] || { text: `Start <code>/${esc(line)}</code>?`, back: "main" };
    return show(c.text, [[["✅ Yes, start", `r:${line}`], ["✖️ Cancel", `m:${c.back}`]]]);
  }
  if (data.startsWith("r:")) {
    await answer("Starting…");
    await show(SCREENS.main.title, SCREENS.main.rows);   // menu stays ready for the next tap
    return handle(env, chatId, undefined, `/${data.slice(2)}`);
  }
  // a button of an older menu, or anything else
  return answer("Send /menu for the current menu.");
}

async function handle(env, chatId, replyTo, text) {
  const [head, ...rawArgs] = text.split(/\s+/);
  const name = head.slice(1).split("@")[0].toLowerCase();
  const reply = (t, markup) => sendMessage(env, chatId, t, replyTo, markup);

  try {
    if (name === "start") {
      await telegram(env, "setMyCommands", { commands: BOT_COMMANDS });
      await reply("👋 <b>Bindal Exports · Ultron</b>\n\nUse the buttons below the chat box any time, or write to me in plain words.",
                  REPLY_KEYBOARD);
      return await reply(SCREENS.main.title, keyboard(SCREENS.main.rows));
    }
    if (name === "help") return await reply(helpText());
    if (name === "dashboard") return await sendDashboardLink(env, chatId, replyTo);
    if (name === "menu") return await reply(SCREENS.main.title, keyboard(SCREENS.main.rows));
    if (name === "status") return await reply(await statusText(env), keyboard([[["🔄 Refresh", "st"], ["🏠 Menu", "m:main"]]]));

    const cmd = COMMANDS[name];
    // not a command: Ultron reads it like any message ("/sales yesterday", "/where is FN123")
    if (!cmd) return await agent.ask(env, chatId, replyTo, text);

    const args = expandPeriod(name, rawArgs);
    const inputs = cmd.inputs(args);
    if (typeof inputs === "string") {
      return await reply(`⚠️ <b>${cmd.name}</b>\n\n${esc(inputs)}\n\nExamples:\n${cmd.examples.map((e) => `<code>${e}</code>`).join("\n")}`);
    }

    // Measured before dispatching, so the new run is not counted as "already running".
    const eta = await estimate(env, cmd, inputs);
    // The run's report goes back to the chat that asked for it, when the workflow can.
    const res = await dispatch(env, cmd, cmd.chat ? { ...inputs, chat_id: String(chatId) } : inputs);
    console.log(`dispatch ${cmd.workflow} ${JSON.stringify(inputs)} -> ${res.status}`);
    if (res.status !== 204) {
      return await reply(`❌ <b>${cmd.name} did not start</b>\n\nGitHub said ${res.status}\n<code>${esc((await res.text()).slice(0, 200))}</code>`);
    }
    const what = describe(name, inputs);
    await reply([
      `⏳ <b>${cmd.name} started</b>`,
      "",
      ...(what ? [`📅 ${esc(what)}`] : []),
      eta,
      "",
      `<i>${cmd.chat ? "Report will come here." : "Report will come to the main chat."}</i>`,
    ].join("\n"));
  } catch (e) {
    console.log(`handle /${name} failed: ${e.stack || e}`);
    await reply(`❌ <b>Error</b>\n\n<code>${esc(e.message)}</code>`);
  }
}

function describe(name, inputs) {
  const d = (s) => new Date(`${s}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
  if (inputs.today) return "Today so far";
  if (inputs.erp_only) return "ERP vs VMS · yesterday and today";
  if (inputs.snapshot) return inputs.snapshot === "current" ? "This month" : inputs.snapshot;
  if (inputs.dry_run) return "Dry run · nothing posted";
  if (inputs.master_only) return "Master sheet only · nothing posted";
  if (name === "returns") return inputs.month ? `Month ${inputs.month}` : "Last month";
  if (name === "ajiospf") return "LIVE · posts on AJIO";
  if (name === "invpush") return "LIVE · pushes every channel";
  if (inputs.days) return `Today + ${inputs.days} days back`;
  if (inputs.day) return d(inputs.day);
  if (inputs.date) return d(inputs.date);
  if (inputs.from) return inputs.to && inputs.to !== inputs.from ? `${d(inputs.from)} → ${d(inputs.to)}` : d(inputs.from);
  return "";
}

// How long the run will take: the median of this workflow's recent successful runs
// (command to finish, so GitHub's queue time is included), plus any run already in progress.
async function estimate(env, cmd, inputs) {
  let minutes = cmd.minutes;
  let waiting = "";
  try {
    const res = await github(env, `/repos/${OWNER}/${REPO}/actions/workflows/${cmd.workflow}/runs?per_page=20`);
    if (res.ok) {
      const runs = (await res.json()).workflow_runs || [];
      const done = runs
        .filter((r) => r.status === "completed" && r.conclusion === "success")
        .map((r) => (Date.parse(r.updated_at) - Date.parse(r.created_at)) / 60000)
        .slice(0, 15)
        .sort((a, b) => a - b);
      if (!cmd.picture && done.length >= 3) minutes = done[Math.floor(done.length / 2)];
      const busy = runs.filter((r) => r.status !== "completed");
      if (busy.length) {
        const ranFor = (Date.now() - Date.parse(busy[0].created_at)) / 60000;
        const left = Math.max(1, Math.ceil(minutes - ranFor));
        minutes += left;
        waiting = `\n🚦 Waits ~${left} min for a run in progress`;
      }
    }
  } catch (e) {
    console.log(`estimate ${cmd.workflow} failed: ${e}`);
  }
  const more = inputs.from && inputs.to && inputs.from !== inputs.to ? "+" : "";
  const finish = new Date(Date.now() + minutes * 60000).toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit",
  });
  return `⏱ ~${fmt(minutes)}${more} · ready by <b>${finish}</b>${waiting}`;
}

function fmt(minutes) {
  return minutes < 1.5 ? "1 min" : `${Math.round(minutes)} min`;
}

// The last run of every report, portal by portal (one GitHub call per workflow).
async function statusText(env) {
  const line = async ([key, c]) => {
    const head = `${c.icon} <b>${c.name}</b>`;
    const auto = scheduleOf(key).map((t) => `⏰ ${t}`);
    const res = await github(env, `/repos/${OWNER}/${REPO}/actions/workflows/${c.workflow}/runs?per_page=1`);
    if (!res.ok) return [head, `⚠️ GitHub ${res.status}`].join("\n");
    const run = (await res.json()).workflow_runs?.[0];
    if (!run) return [head, "No runs yet", ...auto].join("\n");
    const when = new Date(run.created_at).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
    });
    const took = ((run.status === "completed" ? Date.parse(run.updated_at) : Date.now()) - Date.parse(run.created_at)) / 60000;
    const state = run.status !== "completed"
      ? `⏳ Running · ${fmt(took)}`
      : run.conclusion === "success" ? `✅ Done · ${fmt(took)}` : `❌ ${run.conclusion}`;
    return [head, `${state} · 🕒 ${when}`, ...auto].join("\n");
  };
  const sections = await Promise.all(PORTALS.map(async ([key, title]) => {
    const rows = await Promise.all(Object.entries(COMMANDS).filter(([, c]) => c.portal === key && !c.picture).map(line));
    return [`<b>${title}</b>`, "", rows.join("\n\n")].join("\n");
  }));
  const now = new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit" });
  return [`📋 <b>Status</b> · ${now}`, "", sections.join("\n\n")].join("\n");
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
// The agent's routes are ../agent.js, the same for every seller. Plain text in an allowed chat goes
// to the agent-chat workflow (ultron.agents.chat), which answers in the same chat. The agent can
// only read; anything it wants done it proposes with POST /api/approval, and only an Approve tap
// starts it - one of AGENT_ACTIONS (wrangler.toml, the same list as agent.toml), with only the
// inputs listed there. /api/ai serves its model (Workers AI, free daily allocation), /api/memory
// its memory.
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

function dispatch(env, cmd, inputs) {
  return github(env, `/repos/${OWNER}/${REPO}/actions/workflows/${cmd.workflow}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main", inputs }),
  });
}

function keyboard(rows) {
  return { inline_keyboard: rows.map((row) => row.map(([text, data]) => ({ text, callback_data: data }))) };
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
