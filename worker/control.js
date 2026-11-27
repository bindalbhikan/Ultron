// One control service for app buttons, Telegram commands, approvals and chat tools.
export class ControlError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
export const CONTROL_OPERATIONS = {
  "workflow.run": { permission: "workflows.run", changes: true, about: "Start an allowed working", fields: ["action", "inputs"] },
  "workflow.cancel": { permission: "workflows.run", changes: true, about: "Cancel a running working", fields: ["runId"] },
  "workflow.rerun": { permission: "workflows.run", changes: true, about: "Run a completed working again", fields: ["runId"] },
  "schedule.list": { permission: "schedule.read", changes: false, about: "Read the effective schedule", fields: [] },
  "schedule.set": { permission: "agent.manage", changes: true, about: "Pause, resume or move a scheduled task to an existing trigger time", fields: ["id", "enabled", "cron", "revision"] },
  "model.get": { permission: "agent.tools.read", changes: false, about: "Read the shared model settings", fields: [] },
  "model.set": { permission: "agent.manage", changes: true, about: "Save model, tier and fallback order", fields: ["model", "tier", "order", "revision"] },
  "models.list": { permission: "agent.tools.read", changes: false, about: "List provider models", fields: [] },
  "models.refresh": { permission: "agent.manage", changes: true, about: "Refresh provider model lists", fields: [] },
  "keys.list": { permission: "agent.tools.read", changes: false, about: "List key status and last four characters only", fields: [] },
  "keys.remove": { permission: "agent.manage", changes: true, about: "Remove a stored model key", fields: ["id"] },
  "keys.change": { permission: "agent.manage", changes: true, about: "Reset or reorder a stored key", fields: ["id", "move", "reset"] },
  "memory.list": { permission: "agent.tools.read", changes: false, about: "Read shared agent notes", fields: ["kind", "search"] },
  "memory.remove": { permission: "memory.manage", changes: true, about: "Remove a shared note", fields: ["id"] },
  "phones.list": { permission: "phone.manage", changes: false, about: "Read SMS phones", fields: [] },
  "phones.block": { permission: "phone.manage", changes: true, about: "Block or unblock an SMS phone", fields: ["id", "blocked", "revision"] },
  "phoneAgents.list": { permission: "phone.manage", changes: false, about: "Read Agent mode phones", fields: [] },
  "phoneAgents.revoke": { permission: "phone.manage", changes: true, about: "Revoke an Agent mode phone", fields: ["id"] },
};

export function scheduleKey(s) {
  return encodeURIComponent(JSON.stringify([s.cmd || s.name, s.cron, s.day || 0, s.weekdays || [], s.inputs || {}]));
}
export async function effectiveSchedule(database, schedule) {
  const { results } = await database.prepare("SELECT id,enabled,cron,revision FROM agent_schedule").all();
  const changes = new Map(results.map((r) => [r.id, r]));
  return schedule.map((s) => {
    const id = scheduleKey(s), saved = changes.get(id);
    const cron = saved?.cron || s.cron;
    const [minute, hour] = String(cron || "").split(/\s+/).map(Number);
    const time = Number.isFinite(minute + hour) ? (hour * 60 + minute + 330) % 1440 : null;
    const clock = time === null ? "" : String(Math.floor(time / 60)).padStart(2, "0") + ":" + String(time % 60).padStart(2, "0");
    const suffix = String(s.ist || "").replace(/^.*? [AP]M\s*/i, "");
    const human = time === null ? s.ist : ((Math.floor(time / 60) % 12) || 12) + ":" + String(time % 60).padStart(2, "0") + (time >= 720 ? " PM" : " AM");
    return { ...s, id, cron, clock, enabled: saved ? Boolean(saved.enabled) : true, revision: saved?.revision || 0,
      ist: human + (suffix && suffix !== s.ist ? " " + suffix : "") };
  });
}

export function makeControl({ repo, actions, github, dispatch, allowedChat, database, invalidate, schedule = [], delegate, propose }) {
  const fail = (status, message) => { throw new ControlError(status, message); };
  async function actor(env, context) {
    if (context?.source === "system") return { source: "system", id: "scheduler", name: "Scheduler", permissions: ["workflows.run"] };
    if (context?.source === "telegram") {
      if (!allowedChat(env, context.chatId)) fail(403, "This Telegram chat is not allowed.");
      return { source: "telegram", id: "telegram:" + context.chatId, chatId: String(context.chatId), name: "Telegram owner", permissions: ["*"] };
    }
    let userId = context?.userId;
    if (context?.source === "job") {
      const job = await database(env).prepare("SELECT user_id FROM app_chat_job WHERE id=? AND status='running' AND created_at>?")
        .bind(context.jobId, Date.now() - 1800000).first();
      if (!job) fail(403, "The chat request is expired or unavailable.");
      userId = job.user_id;
    } else if (context?.source !== "app") fail(403, "A verified identity is required.");
    if (typeof userId !== "string" || !userId || userId.length > 128) fail(403,"A verified account is required.");
    const row = await database(env).prepare("SELECT u.id,u.name,r.permissions FROM user u JOIN app_access a ON a.user_id=u.id JOIN app_role r ON r.id=a.role_id WHERE u.id=? AND a.status='active'")
      .bind(userId).first();
    const permissions = row ? JSON.parse(row.permissions) : [];
    if (!permissions.includes("app.access") || context?.source === "job" && !permissions.includes("agent.chat")) fail(403, "Your account cannot use these controls.");
    return { source: "app", id: row.id, userId: row.id, name: row.name, permissions };
  }
  const can = (who, permission) => who.permissions.includes("*") || who.permissions.includes(permission);
  async function catalog(env, context) {
    const who = await actor(env, context);
    return {
      operations: Object.fromEntries(Object.entries(CONTROL_OPERATIONS).filter(([, o]) => can(who, o.permission))),
      actions: can(who, "workflows.read") || can(who, "workflows.run") ? actions(env) : {},
      schedule: can(who, "schedule.read") ? await effectiveSchedule(database(env), schedule) : [],
      times: can(who, "schedule.read") ? [...new Set(schedule.map((s) => s.cron))].sort() : [],
    };
  }
  function plan(env, operation, args) {
    const definition = CONTROL_OPERATIONS[operation];
    if (!definition) fail(400, "Choose an operation from the control catalog.");
    if (!args || typeof args !== "object" || Array.isArray(args)) fail(400, "Arguments must be an object.");
    if (Object.keys(args).some((key) => !definition.fields.includes(key))) fail(400, "Unknown operation argument.");
    const out = { operation, args };
    if (operation === "workflow.run") {
      const available = actions(env);
      const action = Object.hasOwn(available, args.action || "") ? available[args.action] : null;
      if (!action) fail(400, "This working is not in the shared action catalog.");
      const input = args.inputs ?? {};
      if (!input || typeof input !== "object" || Array.isArray(input) ||
          Object.keys(input).some((k) => !(action.inputs || []).includes(k))) fail(400, "This working does not accept those inputs.");
      if (Object.values(input).some((v) => !["string", "number", "boolean"].includes(typeof v) || String(v).length > 1000)) fail(400, "Invalid workflow input.");
      out.workflow = action.workflow;
      out.inputs = Object.fromEntries(Object.entries(input).map(([k, v]) => [k, String(v)]));
      out.auto = Boolean(action.auto);
      out.chat = Boolean(action.chat);
    }
    if (["workflow.cancel", "workflow.rerun"].includes(operation) && !/^[1-9][0-9]{0,19}$/.test(String(args.runId || ""))) fail(400, "Choose a valid run.");
    if (operation === "schedule.set") {
      if (!schedule.some((s) => scheduleKey(s) === args.id)) fail(400, "Unknown scheduled task.");
      if (typeof args.enabled !== "boolean" || !Number.isSafeInteger(args.revision) || args.revision < 0) fail(400, "Choose enabled state and current revision.");
      if (args.cron !== undefined && !schedule.some((s) => s.cron === args.cron)) fail(400, "Choose a time from the existing cron triggers.");
    }
    return out;
  }
  async function execute(env, context, operation, args = {}, options = {}) {
    const who = await actor(env, context);
    const definition = CONTROL_OPERATIONS[operation];
    if (!definition || !can(who, definition.permission)) fail(403, "Your role does not allow this operation.");
    const prepared = plan(env, operation, args);
    if (options.preview) return { preview: true, plan: prepared, message: "Preview only. Nothing was started or changed." };
    if (definition.changes && !options.confirmed && !(operation === "workflow.run" && prepared.auto)) {
      if (!propose) fail(409, "Confirm this operation before it can run.");
      return propose(env, who, operation, args);
    }
    const event = crypto.randomUUID();
    if (definition.changes) await database(env).prepare("INSERT INTO agent_control_event(id,actor,operation,target,status,created_at) VALUES(?,?,?,?,'processing',?)")
      .bind(event, who.id, operation, String(args.action || args.runId || args.id || operation), Date.now()).run();
    try {
      let result;
      if (operation === "workflow.run") {
        const inputs = { ...prepared.inputs };
        if (who.chatId && prepared.chat) inputs.chat_id = who.chatId;
        if (who.source === "app" && args.action === "sale" && !inputs.snapshot && !inputs.sjit_request) {
          inputs.chat_id = `report:${event}`;
        }
        const r = await dispatch(env, prepared.workflow, inputs);
        if (r.status !== 204) {
          const error = new ControlError(502,"GitHub did not confirm the run (" + r.status + "). Check run history before retrying.");
          error.retryable = r.status >= 400 && r.status < 500;
          throw error;
        }
        result = { started: prepared.workflow, inputs: prepared.inputs };
      } else if (["workflow.cancel", "workflow.rerun"].includes(operation)) {
        const r = await github(env, "/repos/" + repo + "/actions/runs/" + args.runId);
        if (!r.ok) fail(404, "The run could not be found.");
        const run = await r.json();
        const file = String(run.path || "").split("/").pop().split("@")[0];
        if (!Object.values(actions(env)).some((a) => a.workflow === file) || run.event === "pull_request" ||
            run.head_repository?.full_name && run.head_repository.full_name !== repo) fail(403, "This run is outside the shared action catalog.");
        if (operation === "workflow.cancel" && run.status === "completed" ||
            operation === "workflow.rerun" && run.status !== "completed") fail(409, "Refresh the run; its state does not allow this operation.");
        const verb = operation === "workflow.cancel" ? "cancel" : "rerun";
        const changed = await github(env, "/repos/" + repo + "/actions/runs/" + args.runId + "/" + verb, { method: "POST" });
        if (![201, 202].includes(changed.status)) fail(502, "GitHub did not confirm " + verb + ". Check run history before retrying.");
        result = { [verb]: String(args.runId) };
      } else if (operation === "schedule.list") {
        result = { schedule: await effectiveSchedule(database(env), schedule) };
      } else if (operation === "schedule.set") {
        const claim = crypto.randomUUID();
        const changed = await database(env).batch([database(env).prepare("INSERT INTO agent_schedule(id,enabled,cron,revision,updated_at,updated_by,change_id) SELECT ?,?,?,1,?,?,? WHERE ?=0 OR EXISTS(SELECT 1 FROM agent_schedule WHERE id=? AND revision=?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,cron=excluded.cron,revision=agent_schedule.revision+1,updated_at=excluded.updated_at,updated_by=excluded.updated_by,change_id=excluded.change_id WHERE agent_schedule.revision=? RETURNING revision")
          .bind(args.id, args.enabled ? 1 : 0, args.cron || null, Date.now(), who.id, claim, args.revision, args.id, args.revision, args.revision),
          database(env).prepare("INSERT INTO agent_schedule_history(change_id,id,enabled,cron,created_at,revision) SELECT change_id,id,enabled,cron,updated_at,revision FROM agent_schedule WHERE change_id=?").bind(claim),
        ]);
        if (!changed[0].results.length) fail(409, "The schedule changed. Refresh before saving.");
        result = { saved: true, revision: changed[0].results[0].revision };
      } else {
        if (!delegate) fail(503, "This control service is unavailable.");
        result = await delegate(env, who, operation, args);
      }
      if (definition.changes) {
        await database(env).prepare("UPDATE agent_control_event SET status='completed' WHERE id=?").bind(event).run();
        await invalidate(env);
      }
      return result;
    } catch (error) {
      if (definition.changes) await database(env).prepare("UPDATE agent_control_event SET status='uncertain' WHERE id=?").bind(event).run();
      throw error;
    }
  }
  return { actor, catalog, execute, plan, can };
}
