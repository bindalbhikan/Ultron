import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { Miniflare } from 'miniflare';
import { readD1Migrations } from 'wrangler';

let mf: Miniflare;
let db: D1Database;
let ip = 0;
const password = 'public-test-password-only';
async function call(path: string, method='GET', body?: Record<string, unknown>, token?: string, address?: string) {
  return mf.dispatchFetch(`https://api.example.test${path}`, { method, headers: {
    Origin: 'https://app.example.test', 'CF-Connecting-IP': address || `192.0.2.${++ip}`,
    ...(body ? {'Content-Type':'application/json'} : {}), ...(token ? {Authorization:`Bearer ${token}`} : {}),
  }, ...(body ? { body: JSON.stringify(body) } : {}) });
}
async function signup(email: string) {
  const response=await call('/api/auth/sign-up/email','POST',{name:'Test User',email,password,roleId:'admin',status:'active',emailVerified:true});
  assert.equal(response.status,200);
  return db.prepare('SELECT id FROM user WHERE email=?').bind(email).first<{id:string}>();
}
async function signin(email: string) {
  const response=await call('/api/auth/sign-in/email','POST',{email,password});
  assert.equal(response.status,200);
  const data=await response.json() as {token:string};
  return response.headers.get('set-auth-token') || data.token;
}
before(async () => {
  const bundled=await build({entryPoints:['src/index.ts'],bundle:true,write:false,format:'esm',platform:'node',target:'es2023',external:['node:*'],conditions:['workerd','worker']});
  mf=new Miniflare({modules:true,script:bundled.outputFiles[0].text,compatibilityDate:'2026-11-17',compatibilityFlags:['nodejs_compat'],
    d1Databases:['DB'],bindings:{AUTH_SECRET:'integration-tests-only-secret-32-characters-minimum',AUTH_BASE_URL:'https://api.example.test',APP_ORIGIN:'https://app.example.test'}});
  db=await mf.getD1Database('DB') as unknown as D1Database;
  for (const migration of await readD1Migrations('migrations')) await db.batch(migration.queries.map((query)=>db.prepare(query)));
});
after(async()=>{await mf?.dispose();});

test('registration is pending, cannot self-assign admin and stores a hash',async()=>{
  const registered=await signup('pending@example.test');
  assert.ok(registered);
  const token=await signin('pending@example.test');
  const response=await call('/api/me','GET',undefined,token);
  const {user}=await response.json() as {user: {status:string;roleId:string;permissions:unknown[];emailVerified:boolean}};
  assert.equal(user.status,'pending'); assert.equal(user.roleId,'pending'); assert.deepEqual(user.permissions,[]); assert.equal(user.emailVerified,false);
  const account=await db.prepare('SELECT password FROM account WHERE user_id=?').bind(registered.id).first<{password:string}>();
  assert.ok(account?.password && account.password!==password && account.password.length>80);
  for (const path of ['/api/admin/users','/api/admin/roles','/api/reports','/api/agent/chat','/api/agent/execute']) {
    assert.equal((await call(path,'GET',undefined,token)).status,403);
  }
  assert.equal((await call('/api/admin/users')).status,401);
});

test('admin approves roles, revokes sessions immediately and retains the last administrator',async()=>{
  const admin=await signup('admin@example.test');
  await db.prepare("UPDATE app_access SET status='active',role_id='admin' WHERE user_id=?").bind(admin!.id).run();
  const adminToken=await signin('admin@example.test');
  assert.equal((await call('/api/admin/users','GET',undefined,adminToken)).status,200);
  const member=await signup('member@example.test');
  const pendingToken=await signin('member@example.test');
  const approved=await call(`/api/admin/users/${member!.id}`,'PATCH',{status:'active',roleId:'viewer',revision:1},adminToken);
  assert.equal(approved.status,200);
  assert.equal((await call('/api/me','GET',undefined,pendingToken)).status,401);
  const viewer=await signin('member@example.test');
  assert.equal((await call('/api/reports','GET',undefined,viewer)).status,503);
  assert.equal((await call('/api/agent/chat','POST',{},viewer)).status,403);
  assert.equal((await call('/api/workflows/run','POST',{},viewer)).status,403);
  assert.equal((await call('/api/admin/users','GET',undefined,viewer)).status,403);
  const stale=await call(`/api/admin/users/${member!.id}`,'PATCH',{status:'active',roleId:'admin',revision:1},adminToken);
  assert.equal(stale.status,409);
  assert.equal((await call(`/api/admin/users/${admin!.id}`,'PATCH',{status:'disabled',roleId:'admin',revision:2},adminToken)).status,409);
  assert.equal((await call('/api/me','GET',undefined,adminToken)).status,200);
  const role=await call('/api/admin/roles/viewer','PUT',{name:'Viewer',permissions:['app.access','reports.read','agent.chat'],revision:1},adminToken);
  assert.equal(role.status,200);
  assert.equal((await call('/api/me','GET',undefined,viewer)).status,401);
  const refreshed=await signin('member@example.test');
  assert.equal((await call('/api/agent/chat','POST',{},refreshed)).status,503);
  assert.equal((await call(`/api/admin/users/${member!.id}`,'PATCH',{status:'disabled',roleId:'viewer',revision:2},adminToken)).status,200);
  assert.equal((await call('/api/me','GET',undefined,refreshed)).status,401);
  const audit=await db.prepare('SELECT action FROM app_audit ORDER BY created_at').all();
  assert.deepEqual(audit.results.map((r)=>r.action),['user.access','role.save','user.access']);
  assert.equal((await call('/api/admin/roles/admin','PUT',{name:'Unsafe',permissions:[],revision:1},adminToken)).status,400);
});

test('invalid origins, unknown permissions and auth brute force are rejected',async()=>{
  const wrongOrigin=await mf.dispatchFetch('https://api.example.test/api/auth/sign-up/email',{method:'POST',headers:{Origin:'https://hostile.example.test'}});
  assert.equal(wrongOrigin.status,403); assert.equal(wrongOrigin.headers.get('access-control-allow-origin'),null);
  const adminToken=await signin('admin@example.test');
  assert.equal((await call('/api/admin/roles/custom','PUT',{name:'Custom role',permissions:['invented.permission'],revision:null},adminToken)).status,400);
  assert.equal((await call('/api/auth/admin/set-role','POST',{role:'admin'},adminToken)).status,404);
  let last=0;
  for(let count=0;count<6;count++) last=(await call('/api/auth/sign-in/email','POST',{email:'missing@example.test',password},undefined,'192.0.2.250')).status;
  assert.equal(last,429);
});
