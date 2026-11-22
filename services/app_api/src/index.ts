import { createAuth, type Env } from './auth';
import { HttpError, identity, PERMISSIONS, requirePermission, rolePermissions, type Identity, type Permission } from './access';

const json = (value: unknown, status = 200) => Response.json(value, { status });
const publicAuthPaths = new Set(['/sign-up/email', '/sign-in/email', '/sign-in/username', '/sign-out', '/get-session',
  '/change-password']);
async function body(request: Request): Promise<Record<string, unknown>> {
  if (!request.headers.get('content-type')?.includes('application/json')) throw new HttpError(415, 'Use JSON.');
  const reader = request.body?.getReader();
  if (!reader) throw new HttpError(400, 'A request body is required.');
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > 16384) { await reader.cancel(); throw new HttpError(413, 'Request too large.'); }
    chunks.push(value);
  }
  try {
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    const value: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value as Record<string, unknown>;
  } catch { throw new HttpError(400, 'Enter valid JSON.'); }
}
function revision(value: unknown) {
  if (!Number.isSafeInteger(value) || Number(value) < 1) throw new HttpError(400, 'A current revision is required.');
  return Number(value);
}
function cleanName(value: unknown) {
  if (typeof value !== 'string' || value.trim().length < 2 || value.trim().length > 80) {
    throw new HttpError(400, 'Use a name between 2 and 80 characters.');
  }
  return value.trim();
}
const PROVIDERS = ['anthropic', 'openai', 'google', 'nvidia', 'groq', 'cloudflare'] as const;
const TIERS = ['smart', 'fast'] as const;
const KINDS = ['preference', 'fact', 'known_issue', 'decision', 'incident'] as const;
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,63}$/;
const USERNAME = /^[A-Za-z0-9_.]{3,30}$/;
// An account made without an email gets this internal address: .invalid is reserved and never mailed
const internalEmail = (username: string) => `${username.toLowerCase()}@users.ultron.invalid`;
function cleanUsername(value: unknown) {
  if (typeof value !== 'string' || !USERNAME.test(value.trim())) {
    throw new HttpError(400, 'Use a username of 3 to 30 letters, digits, dots or underscores.');
  }
  return value.trim();
}

// An administrator creates an account: the user signs in with the password given here (and should
// change it); the account starts active with the chosen role. Public sign-up still starts pending.
async function createUser(request: Request, env: Env, actor: Identity) {
  requirePermission(actor, 'users.manage');
  const input = await body(request);
  const name = cleanName(input.name);
  const user = cleanUsername(input.username);
  const typed = typeof input.email === 'string' ? input.email.trim().toLowerCase() : '';
  if (typed && !EMAIL.test(typed)) throw new HttpError(400, 'Enter a valid email address, or leave it empty.');
  const email = typed || internalEmail(user);
  if (typeof input.password !== 'string' || input.password.length < 8 || input.password.length > 128) {
    throw new HttpError(400, 'Use a password of 8 to 128 characters.');
  }
  const role = typeof input.roleId === 'string'
    ? await env.DB.prepare("SELECT id FROM app_role WHERE id=? AND id!='pending'").bind(input.roleId).first() : null;
  if (!role) throw new HttpError(400, 'Choose an approved role.');
  if (await env.DB.prepare('SELECT id FROM user WHERE email=? OR username=?').bind(email, user.toLowerCase()).first()) {
    throw new HttpError(409, 'An account with this username or email already exists.');
  }
  const created = await createAuth(env).api.signUpEmail({ body: { name, email, password: input.password, username: user } });
  const id = created.user.id;
  await env.DB.batch([
    env.DB.prepare(`UPDATE app_access SET status='active',role_id=?,revision=revision+1,updated_at=? WHERE user_id=?`)
      .bind(input.roleId, Date.now(), id),
    env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail) VALUES(?,?,'user.create',?,?)`)
      .bind(crypto.randomUUID(), actor.id, id, JSON.stringify({ username: user, roleId: input.roleId })),
  ]);
  return json({ user: await identity(env, id) }, 201);
}

// The agent's model settings (agent_setting): what the Python agent reads through the worker.
async function agentSettings(env: Env) {
  const { results } = await env.DB.prepare('SELECT key,value,revision,updated_at AS updatedAt FROM agent_setting').all();
  const saved = Object.fromEntries(results.map((r) => [r.key, { value: JSON.parse(String(r.value)), revision: r.revision, updatedAt: r.updatedAt }]));
  return { model: saved.model?.value ?? 'auto', tier: saved.tier?.value ?? 'smart', order: saved.order?.value ?? [...PROVIDERS],
    revision: Math.max(0, ...results.map((r) => Number(r.revision))), providers: PROVIDERS, tiers: TIERS };
}
async function saveAgentSettings(request: Request, env: Env, actor: Identity) {
  requirePermission(actor, 'agent.manage');
  const input = await body(request);
  const model = typeof input.model === 'string' ? input.model.trim() : '';
  const [provider, ...rest] = model.split(':');
  if (model !== 'auto' && (!PROVIDERS.includes(provider as typeof PROVIDERS[number]) || !/^[\w.@/:-]{1,120}$/.test(rest.join(':')))) {
    throw new HttpError(400, 'Choose auto or provider:model.');
  }
  if (!TIERS.includes(input.tier as typeof TIERS[number])) throw new HttpError(400, 'Choose smart or fast.');
  const order = input.order;
  if (!Array.isArray(order) || !order.length || new Set(order).size !== order.length
      || !order.every((p) => PROVIDERS.includes(p as typeof PROVIDERS[number]))) {
    throw new HttpError(400, 'List each provider at most once.');
  }
  const expected = Number(input.revision);
  const current = (await agentSettings(env)).revision;
  if (!Number.isSafeInteger(expected) || expected !== current) throw new HttpError(409, 'Settings changed. Refresh before saving.');
  const now = Date.now();
  const put = (key: string, value: unknown) => env.DB.prepare(`INSERT INTO agent_setting(key,value,revision,updated_at,updated_by)
    VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,revision=excluded.revision,
    updated_at=excluded.updated_at,updated_by=excluded.updated_by`).bind(key, JSON.stringify(value), current + 1, now, actor.id);
  await env.DB.batch([put('model', model), put('tier', input.tier), put('order', order),
    env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail) VALUES(?,?,'agent.settings','agent',?)`)
      .bind(crypto.randomUUID(), actor.id, JSON.stringify({ model, tier: input.tier, order }))]);
  return json({ settings: await agentSettings(env) });
}

// The agent's long-term notes (agent_note), newest first; a kind and words narrow them.
async function agentMemory(env: Env, url: URL) {
  const kind = url.searchParams.get('kind') || '';
  if (kind && !KINDS.includes(kind as typeof KINDS[number])) throw new HttpError(400, 'Unknown kind.');
  const search = (url.searchParams.get('search') || '').slice(0, 100).replace(/[\\%_]/g, '\\$&');
  const { results } = await env.DB.prepare(`SELECT id,kind,text,tags,source,uses,created,updated FROM agent_note
    WHERE (?='' OR kind=?) AND text LIKE ? ESCAPE '\\' ORDER BY updated DESC,id LIMIT 200`)
    .bind(kind, kind, `%${search}%`).all();
  const counts = await env.DB.prepare('SELECT kind,count(*) AS n FROM agent_note GROUP BY kind').all();
  return json({ notes: results.map((r) => ({ ...r, tags: JSON.parse(String(r.tags)) })),
    counts: Object.fromEntries(counts.results.map((r) => [r.kind, r.n])), kinds: KINDS });
}
async function forgetNote(env: Env, actor: Identity, id: string) {
  requirePermission(actor, 'memory.manage');
  const results = await env.DB.batch([
    env.DB.prepare('DELETE FROM agent_note WHERE id=? RETURNING id').bind(id),
    env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail) SELECT ?,?,'agent.forget',?,'{}' WHERE changes()=1`)
      .bind(crypto.randomUUID(), actor.id, id),
  ]);
  if (results[0].results.length !== 1) throw new HttpError(404, 'This note is already gone.');
  return json({ deleted: id });
}

// The phones in "SMS only" mode (sms_phone, written by the Telegram worker's POST /api/sms): newest first;
// a blocked phone's SMS are refused by the worker.
async function smsPhones(env: Env) {
  const { results } = await env.DB.prepare(`SELECT id,name,first_seen AS firstSeen,last_seen AS lastSeen,sent,
    blocked,app_version AS appVersion,revision FROM sms_phone ORDER BY last_seen DESC LIMIT 200`).all();
  return json({ phones: results.map((r) => ({ ...r, blocked: Boolean(r.blocked) })) });
}
async function blockPhone(request: Request, env: Env, actor: Identity, id: string) {
  requirePermission(actor, 'phone.manage');
  const input = await body(request);
  if (typeof input.blocked !== 'boolean') throw new HttpError(400, 'Say whether the phone is blocked.');
  const expected = revision(input.revision);
  const results = await env.DB.batch([
    env.DB.prepare('UPDATE sms_phone SET blocked=?,revision=revision+1 WHERE id=? AND revision=? RETURNING id')
      .bind(input.blocked ? 1 : 0, id, expected),
    env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail) SELECT ?,?,'phone.block',?,? WHERE changes()=1`)
      .bind(crypto.randomUUID(), actor.id, id, JSON.stringify({ blocked: input.blocked })),
  ]);
  if (results[0].results.length !== 1) throw new HttpError(409, 'This phone changed. Refresh before saving.');
  return smsPhones(env);
}

async function roles(env: Env) {
  const { results } = await env.DB.prepare('SELECT id,name,permissions,revision FROM app_role ORDER BY name').all();
  return results.map((row) => ({ ...row, permissions: JSON.parse(String(row.permissions)) }));
}
async function updateUser(request: Request, env: Env, actor: Identity, id: string) {
  requirePermission(actor, 'users.manage');
  const input = await body(request);
  if (!['active', 'pending', 'disabled'].includes(String(input.status)) || typeof input.roleId !== 'string') {
    throw new HttpError(400, 'Select a valid status and role.');
  }
  const expected = revision(input.revision);
  const role = await env.DB.prepare('SELECT id FROM app_role WHERE id=?').bind(input.roleId).first();
  if (!role || (input.status === 'active' && input.roleId === 'pending')) throw new HttpError(400, 'Choose an approved role.');
  const detail = JSON.stringify({ status: input.status, roleId: input.roleId });
  try {
    const result = await env.DB.batch([
      env.DB.prepare(`UPDATE app_access SET status=?,role_id=?,revision=revision+1,updated_at=?
        WHERE user_id=? AND revision=? RETURNING user_id`).bind(input.status, input.roleId, Date.now(), id, expected),
      env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail)
        SELECT ?,?,'user.access',?,? WHERE changes()=1`).bind(crypto.randomUUID(), actor.id, id, detail),
    ]);
    // RETURNING, not meta.changes: D1 counts the rows its triggers change too (the revoked sessions)
    if (result[0].results.length !== 1) throw new HttpError(409, 'Access changed. Refresh before saving.');
  } catch (error) {
    if (error instanceof Error && error.message.includes('last_admin')) {
      throw new HttpError(409, 'Keep at least one active administrator.');
    }
    throw error;
  }
  return json({ user: await identity(env, id) });
}
async function saveRole(request: Request, env: Env, actor: Identity, id: string) {
  requirePermission(actor, 'roles.manage');
  if (!/^[a-z][a-z0-9-]{1,39}$/.test(id) || ['admin', 'pending'].includes(id)) {
    throw new HttpError(400, 'This role cannot be changed.');
  }
  const input = await body(request);
  const name = cleanName(input.name);
  const permissions = rolePermissions(input.permissions);
  const expected = input.revision === null ? null : revision(input.revision);
  const detail = JSON.stringify({ name, permissions });
  const sql = expected === null
    ? env.DB.prepare('INSERT OR IGNORE INTO app_role(id,name,permissions) VALUES(?,?,?) RETURNING id').bind(id, name, JSON.stringify(permissions))
    : env.DB.prepare(`UPDATE app_role SET name=?,permissions=?,revision=revision+1,updated_at=? WHERE id=? AND revision=? RETURNING id`)
      .bind(name, JSON.stringify(permissions), Date.now(), id, expected);
  const results = await env.DB.batch([sql,
    env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail)
      SELECT ?,?,'role.save',?,? WHERE changes()=1`).bind(crypto.randomUUID(), actor.id, id, detail),
  ]);
  if (results[0].results.length !== 1) throw new HttpError(409, 'Role changed. Refresh before saving.');
  return json({ roles: await roles(env) });
}

async function route(request: Request, env: Env) {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === '/health' && request.method === 'GET') {
    await env.DB.prepare('SELECT id FROM app_role WHERE id=?').bind('admin').first();
    return json({ ok: true, service: 'ultron-app-api' });
  }
  const auth = createAuth(env);
  if (path.startsWith('/api/auth/')) {
    const authPath = path.slice('/api/auth'.length);
    if (!publicAuthPaths.has(authPath)) throw new HttpError(404, 'Route unavailable.');
    if (request.method === 'POST') {
      const input = await body(request);
      if (authPath === '/sign-up/email') {
        input.name = cleanName(input.name);
        // Public registration may never set access, roles, verification or session policy.
        for (const key of Object.keys(input)) if (!['name','email','password','username'].includes(key)) delete input[key];
        input.username = cleanUsername(input.username);
        if (!input.email) input.email = internalEmail(String(input.username));
      }
      request = new Request(request.url, { method: 'POST', headers: request.headers, body: JSON.stringify(input) });
    }
    return auth.handler(request);
  }
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) throw new HttpError(401, 'Sign in to continue.');
  const user = await identity(env, session.user.id);
  if (path === '/api/me' && request.method === 'GET') return json({ user });
  if (path === '/api/admin/users' && request.method === 'GET') {
    requirePermission(user, 'users.manage');
    const page = Number(url.searchParams.get('page') || '0');
    const search = (url.searchParams.get('search') || '').slice(0, 100).replace(/[\\%_]/g, '\\$&');
    if (!Number.isSafeInteger(page) || page < 0 || page > 100000) throw new HttpError(400, 'Invalid page.');
    const { results } = await env.DB.prepare(`SELECT u.id,u.name,COALESCE(u.display_username,u.username,'') AS username,
      u.email,u.email_verified AS emailVerified,
      a.status,a.role_id AS roleId,a.revision,r.name AS roleName FROM user u JOIN app_access a ON a.user_id=u.id
      JOIN app_role r ON r.id=a.role_id WHERE u.name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\' OR u.username LIKE ? ESCAPE '\\'
      ORDER BY u.created_at DESC,u.id LIMIT 51 OFFSET ?`).bind(`%${search}%`, `%${search}%`, `%${search}%`, page * 50).all();
    return json({ users: results.slice(0, 50), hasMore: results.length > 50, page });
  }
  if (path === '/api/admin/roles' && request.method === 'GET') {
    requirePermission(user, 'roles.manage');
    return json({ roles: await roles(env), permissions: PERMISSIONS });
  }
  if (path === '/api/admin/users' && request.method === 'POST') return createUser(request, env, user);
  if (path === '/api/agent/settings' && request.method === 'GET') {
    requirePermission(user, 'agent.tools.read');
    return json({ settings: await agentSettings(env) });
  }
  if (path === '/api/agent/settings' && request.method === 'PUT') return saveAgentSettings(request, env, user);
  if (path === '/api/agent/memory' && request.method === 'GET') {
    requirePermission(user, 'agent.tools.read');
    return agentMemory(env, url);
  }
  if (path === '/api/admin/phones' && request.method === 'GET') {
    requirePermission(user, 'phone.manage');
    return smsPhones(env);
  }
  const phoneMatch = path.match(/^\/api\/admin\/phones\/([0-9a-f-]{36})$/);
  if (phoneMatch && request.method === 'PATCH') return blockPhone(request, env, user, phoneMatch[1]);
  const noteMatch = path.match(/^\/api\/agent\/memory\/([a-f0-9]{6,16})$/);
  if (noteMatch && request.method === 'DELETE') return forgetNote(env, user, noteMatch[1]);
  const userMatch = path.match(/^\/api\/admin\/users\/([A-Za-z0-9_-]{1,128})$/);
  if (userMatch && request.method === 'PATCH') return updateUser(request, env, user, userMatch[1]);
  const roleMatch = path.match(/^\/api\/admin\/roles\/([a-z0-9-]+)$/);
  if (roleMatch && request.method === 'PUT') return saveRole(request, env, user, roleMatch[1]);
  if (path === '/api/admin/audit' && request.method === 'GET') {
    requirePermission(user, 'users.manage');
    const { results } = await env.DB.prepare('SELECT id,actor_id AS actorId,action,target_id AS targetId,detail,created_at AS createdAt FROM app_audit ORDER BY created_at DESC,rowid DESC LIMIT 100').all();
    return json({ events: results.map((row) => ({ ...row, detail: JSON.parse(String(row.detail)) })) });
  }
  // Explicit fail-closed gates for future operational adapters. No generic proxy or shared token reaches clients.
  const operational: Record<string, Permission> = {
    '/api/workspace': 'app.access', '/api/reports': 'reports.read', '/api/workflows': 'workflows.read',
    '/api/workflows/run': 'workflows.run', '/api/approvals': 'approvals.read', '/api/approvals/decide': 'approvals.decide',
    '/api/analytics': 'analytics.read', '/api/connections': 'connections.read', '/api/phone': 'phone.manage',
    '/api/schedule': 'schedule.read', '/api/agent/chat': 'agent.chat', '/api/agent/tools': 'agent.tools.read',
    '/api/agent/execute': 'agent.tools.execute',
  };
  if (operational[path]) {
    requirePermission(user, operational[path]);
    throw new HttpError(503, 'This operational service is not connected yet. Your access is enforced; no action was started.');
  }
  throw new HttpError(404, 'Route unavailable.');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get('origin');
    const allowed = env.APP_ORIGIN.split(',').map((value) => value.trim());
    let response: Response;
    try {
      if (origin && !allowed.includes(origin)) throw new HttpError(403, 'Origin is not allowed.');
      if (!env.AUTH_SECRET || env.AUTH_SECRET.length < 32) throw new HttpError(503, 'Authentication is not configured.');
      response = request.method === 'OPTIONS' ? new Response(null, { status: 204 }) : await route(request, env);
    } catch (error) {
      response = error instanceof HttpError ? json({ error: error.message }, error.status)
        : json({ error: 'The request could not finish. Try again.' }, 500);
    }
    const headers = new Headers(response.headers);
    headers.set('Cache-Control', 'no-store');
    headers.set('X-Content-Type-Options', 'nosniff');
    headers.set('Referrer-Policy', 'no-referrer');
    headers.set('Vary', 'Origin');
    if (origin && allowed.includes(origin)) {
      headers.set('Access-Control-Allow-Origin', origin);
      headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
      headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      headers.set('Access-Control-Expose-Headers', 'set-auth-token');
    }
    return new Response(response.body, { status: response.status, headers });
  },
};
