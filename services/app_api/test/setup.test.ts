import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { createTestHarness, unstable_splitSqlQuery, type TestHarness } from 'wrangler';

// First-time setup on an empty database: the first administrator, made with the setup code, once.
let server: TestHarness;
let db: D1Database;
let ip = 0;
const CODE = 'test-setup-code';
async function call(path: string, method = 'GET', body?: Record<string, unknown>) {
  return server.fetch(`https://api.example.test${path}`, { method, headers: {
    Origin: 'https://app.example.test', 'CF-Connecting-IP': `198.51.100.${++ip}`,
    ...(body ? { 'Content-Type': 'application/json' } : {}),
  }, ...(body ? { body: JSON.stringify(body) } : {}) });
}
before(async () => {
  server = createTestHarness({ workers: [{ configPath: 'wrangler.jsonc',
    vars: { AUTH_BASE_URL: 'https://api.example.test', APP_ORIGIN: 'https://app.example.test' },
    secrets: { AUTH_SECRET: 'integration-tests-only-secret-32-characters-minimum',
      SETUP_CODE_HASH: createHash('sha256').update(CODE).digest('hex') } }] });
  await server.listen();
  db = (await server.getWorker<{ DB: D1Database }>().getEnv()).DB;
  for (const file of readdirSync('migrations').filter((f) => f.endsWith('.sql')).sort()) {
    const queries: string[] = unstable_splitSqlQuery(readFileSync(`migrations/${file}`, 'utf8'));
    await db.batch(queries.map((query) => db.prepare(query)));
  }
});
after(async () => { await server?.close(); });

test('the code makes the first administrator, who signs in by username; then setup is closed', async () => {
  assert.deepEqual(await (await call('/api/setup')).json(), { needed: true });
  assert.equal((await call('/api/setup', 'POST', { code: 'nope', name: 'Owner', username: 'Bhikan', password: 'Eight@8c' })).status, 403);
  assert.equal((await call('/api/setup', 'POST', { code: CODE, name: 'Owner', username: 'Bhikan', password: 'short' })).status, 400);
  const made = await call('/api/setup', 'POST', { code: CODE, name: 'Bhikan Deshmukh', username: 'Bhikan', password: 'Eight@8c' });
  assert.equal(made.status, 201);
  const row = await db.prepare(`SELECT a.status,a.role_id FROM user u JOIN app_access a ON a.user_id=u.id WHERE u.username='bhikan'`)
    .first<{ status: string; role_id: string }>();
  assert.deepEqual({ ...row }, { status: 'active', role_id: 'admin' });
  const signin = await call('/api/auth/sign-in/username', 'POST', { username: 'bhikan', password: 'Eight@8c' });
  assert.equal(signin.status, 200);
  const token = signin.headers.get('set-auth-token');
  const me = await server.fetch('https://api.example.test/api/me', { headers: { Authorization: `Bearer ${token}` } });
  const { user } = await me.json() as { user: { roleId: string; permissions: string[] } };
  assert.equal(user.roleId, 'admin'); assert.ok(user.permissions.includes('users.manage'));
  assert.deepEqual(await (await call('/api/setup')).json(), { needed: false });
  assert.equal((await call('/api/setup', 'POST', { code: CODE, name: 'Second', username: 'second', password: 'Eight@8c' })).status, 409);
});
