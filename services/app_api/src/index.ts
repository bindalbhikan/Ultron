import { createAuth, type Env } from './auth';
import { HttpError, identity, PERMISSIONS, requirePermission, rolePermissions, type Identity, type Permission } from './access';

const json = (value: unknown, status = 200) => Response.json(value, { status });
const publicAuthPaths = new Set(['/sign-up/email', '/sign-in/email', '/sign-out', '/get-session', '/change-password']);
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
        WHERE user_id=? AND revision=?`).bind(input.status, input.roleId, Date.now(), id, expected),
      env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail)
        SELECT ?,?,'user.access',?,? WHERE changes()=1`).bind(crypto.randomUUID(), actor.id, id, detail),
    ]);
    if (result[0].meta.changes !== 1) throw new HttpError(409, 'Access changed. Refresh before saving.');
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
    ? env.DB.prepare('INSERT OR IGNORE INTO app_role(id,name,permissions) VALUES(?,?,?)').bind(id, name, JSON.stringify(permissions))
    : env.DB.prepare(`UPDATE app_role SET name=?,permissions=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?`)
      .bind(name, JSON.stringify(permissions), Date.now(), id, expected);
  const results = await env.DB.batch([sql,
    env.DB.prepare(`INSERT INTO app_audit(id,actor_id,action,target_id,detail)
      SELECT ?,?,'role.save',?,? WHERE changes()=1`).bind(crypto.randomUUID(), actor.id, id, detail),
  ]);
  if (results[0].meta.changes !== 1) throw new HttpError(409, 'Role changed. Refresh before saving.');
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
        for (const key of Object.keys(input)) if (!['name','email','password'].includes(key)) delete input[key];
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
    const { results } = await env.DB.prepare(`SELECT u.id,u.name,u.email,u.email_verified AS emailVerified,
      a.status,a.role_id AS roleId,a.revision,r.name AS roleName FROM user u JOIN app_access a ON a.user_id=u.id
      JOIN app_role r ON r.id=a.role_id WHERE u.name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\'
      ORDER BY u.created_at DESC,u.id LIMIT 51 OFFSET ?`).bind(`%${search}%`, `%${search}%`, page * 50).all();
    return json({ users: results.slice(0, 50), hasMore: results.length > 50, page });
  }
  if (path === '/api/admin/roles' && request.method === 'GET') {
    requirePermission(user, 'roles.manage');
    return json({ roles: await roles(env), permissions: PERMISSIONS });
  }
  const userMatch = path.match(/^\/api\/admin\/users\/([A-Za-z0-9_-]{1,128})$/);
  if (userMatch && request.method === 'PATCH') return updateUser(request, env, user, userMatch[1]);
  const roleMatch = path.match(/^\/api\/admin\/roles\/([a-z0-9-]+)$/);
  if (roleMatch && request.method === 'PUT') return saveRole(request, env, user, roleMatch[1]);
  if (path === '/api/admin/audit' && request.method === 'GET') {
    requirePermission(user, 'users.manage');
    const { results } = await env.DB.prepare('SELECT id,actor_id AS actorId,action,target_id AS targetId,detail,created_at AS createdAt FROM app_audit ORDER BY created_at DESC LIMIT 100').all();
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
      headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, OPTIONS');
      headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      headers.set('Access-Control-Expose-Headers', 'set-auth-token');
    }
    return new Response(response.body, { status: response.status, headers });
  },
};
