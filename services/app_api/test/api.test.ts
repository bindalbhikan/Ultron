import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { createTestHarness, unstable_splitSqlQuery, type TestHarness } from 'wrangler';
import { makeAgent } from '../../../worker/agent.js';

// The real Worker as `wrangler dev` runs it (its wrangler.jsonc, bundling and runtime), local D1.
let server: TestHarness;
let db: D1Database;
let ip = 0;
const password = 'public-test-password-only';
async function call(path: string, method='GET', body?: Record<string, unknown>, token?: string, address?: string) {
  return server.fetch(`https://api.example.test${path}`, { method, headers: {
    Origin: 'https://app.example.test', 'CF-Connecting-IP': address || `192.0.2.${++ip}`,
    ...(body ? {'Content-Type':'application/json'} : {}), ...(token ? {Authorization:`Bearer ${token}`} : {}),
  }, ...(body ? { body: JSON.stringify(body) } : {}) });
}
async function signup(email: string) {
  const response=await call('/api/auth/sign-up/email','POST',{name:'Test User',email,username:email.split('@')[0],password,roleId:'admin',status:'active',emailVerified:true});
  assert.equal(response.status,200);
  return db.prepare('SELECT id FROM user WHERE email=?').bind(email).first<{id:string}>();
}
async function signin(email: string) {
  const response=await call('/api/auth/sign-in/email','POST',{email,password});
  assert.equal(response.status,200);
  const data=await response.json() as {token:string};
  return response.headers.get('set-auth-token') || data.token;
}
async function signin2(username: string, pass: string) {
  const response=await call('/api/auth/sign-in/username','POST',{username,password:pass});
  assert.equal(response.status,200);
  return response.headers.get('set-auth-token')!;
}
before(async () => {
  server=createTestHarness({workers:[{configPath:'wrangler.jsonc',
    vars:{AUTH_BASE_URL:'https://api.example.test',APP_ORIGIN:'https://app.example.test'},
    secrets:{AUTH_SECRET:'integration-tests-only-secret-32-characters-minimum',
      KEYS_SECRET:'integration-tests-only-keys-secret-32-chars-min',
      SETUP_CODE_HASH:'5b02d4eb46b7e8525e3b26acb6b37563dcffc9981c86f352c70c2d4347fb5591',
      WORKER_TOKEN:'test-worker-token'}},
    {configPath:'test/ops_stub/wrangler.jsonc'}]});
  await server.listen();
  db=(await server.getWorker<{DB:D1Database}>().getEnv()).DB;
  // the migrations in order, as `wrangler d1 migrations apply` runs them
  for (const file of readdirSync('migrations').filter((f)=>f.endsWith('.sql')).sort()) {
    const queries:string[]=unstable_splitSqlQuery(readFileSync(`migrations/${file}`,'utf8'));
    await db.batch(queries.map((query)=>db.prepare(query)));
  }
});
after(async()=>{await server?.close();});

test('first-time setup: only with the code, only while no administrator exists',async()=>{
  assert.deepEqual(await (await call('/api/setup')).json(),{needed:true});
  assert.equal((await call('/api/setup','POST',{code:'wrong',name:'Owner',username:'Owner1',password:'Eight@8c'})).status,403);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM user').first<{n:number}>())!.n,0);
});

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
  assert.equal((await call('/api/agent/chat','POST',{},refreshed)).status,400);
  assert.equal((await call(`/api/admin/users/${member!.id}`,'PATCH',{status:'disabled',roleId:'viewer',revision:2},adminToken)).status,200);
  assert.equal((await call('/api/me','GET',undefined,refreshed)).status,401);
  const audit=await db.prepare('SELECT action FROM app_audit ORDER BY created_at,rowid').all();
  assert.deepEqual(audit.results.map((r)=>r.action),['user.access','role.save','user.access']);
  assert.equal((await call('/api/admin/roles/admin','PUT',{name:'Unsafe',permissions:[],revision:1},adminToken)).status,400);
});

test('invalid origins, unknown permissions and auth brute force are rejected',async()=>{
  const wrongOrigin=await server.fetch('https://api.example.test/api/auth/sign-up/email',{method:'POST',headers:{Origin:'https://hostile.example.test'}});
  assert.equal(wrongOrigin.status,403); assert.equal(wrongOrigin.headers.get('access-control-allow-origin'),null);
  const adminToken=await signin('admin@example.test');
  assert.equal((await call('/api/admin/roles/custom','PUT',{name:'Custom role',permissions:['invented.permission'],revision:null},adminToken)).status,400);
  assert.equal((await call('/api/auth/admin/set-role','POST',{role:'admin'},adminToken)).status,404);
  let last=0;
  for(let count=0;count<6;count++) last=(await call('/api/auth/sign-in/email','POST',{email:'missing@example.test',password},undefined,'192.0.2.250')).status;
  assert.equal(last,429);
});

test('an administrator creates an active account; others cannot',async()=>{
  const adminToken=await signin('admin@example.test');
  const created=await call('/api/admin/users','POST',{name:'Store Manager',username:'Manager',password:'a-long-public-test-pass',roleId:'manager'},adminToken);
  assert.equal(created.status,201);
  const {user}=await created.json() as {user:{status:string;roleId:string;email:string}};
  assert.equal(user.status,'active'); assert.equal(user.roleId,'manager'); assert.equal(user.email,'manager@users.ultron.invalid');
  assert.equal((user as unknown as {username:string}).username,'Manager');
  const managerSignin=await call('/api/auth/sign-in/username','POST',{username:'manager',password:'a-long-public-test-pass'});
  assert.equal(managerSignin.status,200);
  const managerToken=managerSignin.headers.get('set-auth-token')!;
  assert.equal((await call('/api/me','GET',undefined,managerToken)).status,200);
  assert.equal((await call('/api/admin/users','POST',{name:'Again',username:'MANAGER',password:'a-long-public-test-pass',roleId:'viewer'},adminToken)).status,409);
  assert.equal((await call('/api/admin/users','POST',{name:'Short',username:'shorty',password:'seven77',roleId:'viewer'},adminToken)).status,400);
  assert.equal((await call('/api/admin/users','POST',{name:'Pending',username:'pend',password:'a-long-public-test-pass',roleId:'pending'},adminToken)).status,400);
  assert.equal((await call('/api/admin/users','POST',{name:'Sneaky',username:'sneaky',password:'a-long-public-test-pass',roleId:'admin'},managerToken)).status,403);
  const audit=await db.prepare("SELECT detail FROM app_audit WHERE action='user.create'").all();
  assert.equal(audit.results.length,1);
  assert.ok(!String(audit.results[0].detail).includes('pass'));      // the password never reaches the audit
});

test('the control panel reads and saves the model settings, with revisions and checks',async()=>{
  const adminToken=await signin('admin@example.test');
  const read=await call('/api/agent/settings','GET',undefined,adminToken);
  assert.equal(read.status,200);
  const {settings}=await read.json() as {settings:{model:string;tier:string;order:string[];revision:number}};
  assert.equal(settings.model,'auto'); assert.equal(settings.revision,0); assert.equal(settings.order.at(-1),'cloudflare');
  const save=(body:Record<string,unknown>,token=adminToken)=>call('/api/agent/settings','PUT',body,token);
  assert.equal((await save({model:'anthropic:claude-sonnet-5-5',tier:'fast',order:['groq','cloudflare'],revision:0})).status,200);
  const row=await db.prepare("SELECT value FROM agent_setting WHERE key='order'").first<{value:string}>();
  assert.deepEqual(JSON.parse(row!.value),['groq','cloudflare']);
  assert.equal((await save({model:'auto',tier:'smart',order:['groq'],revision:0})).status,409);           // stale
  assert.equal((await save({model:'someone:x',tier:'smart',order:['groq'],revision:1})).status,400);
  assert.equal((await save({model:'auto',tier:'huge',order:['groq'],revision:1})).status,400);
  assert.equal((await save({model:'auto',tier:'smart',order:['groq','groq'],revision:1})).status,400);
  const managerToken=await signin2('manager','a-long-public-test-pass');
  assert.equal((await call('/api/agent/settings','GET',undefined,managerToken)).status,200);
  assert.equal((await save({model:'auto',tier:'smart',order:['groq'],revision:1},managerToken)).status,403);
});

test('the control panel lists the agent memory and an administrator drops a note',async()=>{
  const adminToken=await signin('admin@example.test');
  await db.batch([
    db.prepare("INSERT INTO agent_note(id,kind,text,tags,created,updated) VALUES('a1b2c3','fact','Ajio pays on Wednesdays','[\"ajio\"]',1,2)"),
    db.prepare("INSERT INTO agent_note(id,kind,text,tags,created,updated) VALUES('d4e5f6','incident','vms.yml failed','[]',1,3)"),
  ]);
  const list=await call('/api/agent/memory?kind=fact&search=ajio','GET',undefined,adminToken);
  const data=await list.json() as {notes:{id:string;tags:string[]}[];counts:Record<string,number>};
  assert.deepEqual(data.notes.map((n)=>n.id),['a1b2c3']); assert.deepEqual(data.notes[0].tags,['ajio']);
  assert.equal(data.counts.incident,1);
  const managerToken=await signin2('manager','a-long-public-test-pass');
  assert.equal((await call('/api/agent/memory/d4e5f6','DELETE',undefined,managerToken)).status,403);
  assert.equal((await call('/api/agent/memory/d4e5f6','DELETE',undefined,adminToken)).status,200);
  assert.equal((await call('/api/agent/memory/d4e5f6','DELETE',undefined,adminToken)).status,404);
  assert.equal((await call('/api/agent/memory?kind=bogus','GET',undefined,adminToken)).status,400);
});

test('SMS-only phones are listed and an administrator blocks one',async()=>{
  const adminToken=await signin('admin@example.test');
  const id='0b7e3c1a-2f4d-4e5a-9b8c-1d2e3f4a5b6c';
  await db.prepare("INSERT INTO sms_phone(id,name,first_seen,last_seen,sent) VALUES(?,'Ramesh SIM2',1,2,5)").bind(id).run();
  const list=await call('/api/admin/phones','GET',undefined,adminToken);
  const {phones}=await list.json() as {phones:{id:string;name:string;sent:number;blocked:boolean;revision:number}[]};
  assert.equal(phones[0].name,'Ramesh SIM2'); assert.equal(phones[0].blocked,false); assert.equal(phones[0].sent,5);
  assert.equal((await call(`/api/admin/phones/${id}`,'PATCH',{blocked:true,revision:1},adminToken)).status,200);
  assert.equal((await db.prepare('SELECT blocked FROM sms_phone WHERE id=?').bind(id).first<{blocked:number}>())!.blocked,1);
  assert.equal((await call(`/api/admin/phones/${id}`,'PATCH',{blocked:false,revision:1},adminToken)).status,409);
  const viewerToken=await signin2('manager','a-long-public-test-pass');
  assert.equal((await call('/api/admin/phones','GET',undefined,viewerToken)).status,200);   // managers have phone.manage
});

test('an eight-character password and a username are enough; a bad username is refused',async()=>{
  const adminToken=await signin('admin@example.test');
  assert.equal((await call('/api/admin/users','POST',{name:'Owner Two',username:'Owner.Two',password:'Eight@8c',roleId:'viewer'},adminToken)).status,201);
  assert.equal((await call('/api/auth/sign-in/username','POST',{username:'owner.two',password:'Eight@8c'})).status,200);
  assert.equal((await call('/api/admin/users','POST',{name:'Bad Name',username:'no spaces',password:'Eight@8c',roleId:'viewer'},adminToken)).status,400);
  const reg=await call('/api/auth/sign-up/email','POST',{name:'New Person',username:'newperson',password:'Eight@8c'});
  assert.equal(reg.status,200);
  const row=await db.prepare("SELECT a.status FROM user u JOIN app_access a ON a.user_id=u.id WHERE u.username='newperson'").first<{status:string}>();
  assert.equal(row!.status,'pending');                       // a public registration waits for an administrator
});

test('an administrator turns a phone into an agent with a token kept only as a hash, and revokes it',async()=>{
  const adminToken=await signin('admin@example.test');
  const made=await call('/api/admin/phone-agents','POST',{device:'Xiaomi Redmi 12'},adminToken);
  assert.equal(made.status,201);
  const {id,token}=await made.json() as {id:string;token:string};
  assert.ok(token.length>=40);
  const row=await db.prepare('SELECT token_hash,revoked FROM phone_agent WHERE id=?').bind(id).first<{token_hash:string;revoked:number}>();
  assert.notEqual(row!.token_hash,token); assert.equal(row!.token_hash.length,64); assert.equal(row!.revoked,0);
  const list=await (await call('/api/admin/phone-agents','GET',undefined,adminToken)).json() as {agents:{id:string}[]};
  assert.equal(list.agents[0].id,id);
  assert.equal((await call(`/api/admin/phone-agents/${id}`,'DELETE',undefined,adminToken)).status,200);
  assert.equal((await call(`/api/admin/phone-agents/${id}`,'DELETE',undefined,adminToken)).status,404);
  assert.equal((await call('/api/admin/phone-agents','POST',{device:'x'},adminToken)).status,400);
  const viewerToken=await signin2('owner.two','Eight@8c');            // a viewer: no phone.manage
  assert.equal((await call('/api/admin/phone-agents','POST',{device:'Some phone'},viewerToken)).status,403);
});

test('an administrator adds API keys (encrypted, shown by their last four), orders, resets and removes them',async()=>{
  const adminToken=await signin('admin@example.test');
  const add=(b:Record<string,unknown>,t=adminToken)=>call('/api/agent/keys','POST',b,t);
  assert.equal((await add({provider:'groq',key:'gsk_test_aaaaaaaaaaaaaaaaaaaa1111',label:'first'})).status,200);
  const second=await add({provider:'groq',key:'gsk_test_bbbbbbbbbbbbbbbbbbbb2222',label:'second'});
  const {keys}=await second.json() as {keys:{id:string;provider:string;last4:string;position:number;status:string}[]};
  assert.deepEqual(keys.map((k)=>[k.last4,k.position]),[['1111',0],['2222',1]]);
  assert.ok(!JSON.stringify(keys).includes('gsk_test'));                        // the key never comes back
  const row=await db.prepare('SELECT ciphertext FROM api_key WHERE last4=?').bind('1111').first<{ciphertext:string}>();
  assert.ok(!row!.ciphertext.includes('gsk_test'));                             // encrypted at rest
  assert.equal((await add({provider:'groq',key:'gsk_test_aaaaaaaaaaaaaaaaaaaa1111',label:'first'})).status,409);
  assert.equal((await add({provider:'someone',key:'x'.repeat(20)})).status,400);
  assert.equal((await add({provider:'groq',key:'short'})).status,400);
  const moved=await call(`/api/agent/keys/${keys[1].id}`,'PATCH',{move:'up'},adminToken);
  const after=(await moved.json() as {keys:{last4:string}[]}).keys;
  assert.deepEqual(after.map((k)=>k.last4),['2222','1111']);
  await db.prepare(`UPDATE api_key SET status='limit',resting_until=? WHERE last4='2222'`).bind(Date.now()+3600000).run();
  const reset=await call(`/api/agent/keys/${keys[1].id}`,'PATCH',{reset:true},adminToken);
  assert.equal((await reset.json() as {keys:{last4:string;status:string}[]}).keys[0].status,'ok');
  assert.equal((await call(`/api/agent/keys/${keys[0].id}`,'DELETE',undefined,adminToken)).status,200);
  const managerToken=await signin2('manager','a-long-public-test-pass');
  assert.equal((await add({provider:'groq',key:'gsk_test_cccccccccccccccccccc3333'},managerToken)).status,403);
  assert.equal((await call('/api/agent/keys','GET',undefined,managerToken)).status,200);
  await db.prepare(`INSERT INTO agent_model(provider,ids,updated_at) VALUES('groq','["openai/gpt-oss-120b"]',1)`).run();
  const models=await (await call('/api/agent/models','GET',undefined,adminToken)).json() as {models:Record<string,{ids:string[]}>};
  assert.deepEqual(models.models.groq.ids,['openai/gpt-oss-120b']);
});

test('workspace, run and decide check the role, then reach the operations service by its binding',async()=>{
  const adminToken=await signin('admin@example.test');
  // the OPS binding reaches the stand-in worker (test/ops_stub) with WORKER_TOKEN; a refused user gets 403 first
  const ws=await call('/api/workspace','GET',undefined,adminToken);
  assert.equal(ws.status,200);
  assert.equal(((await ws.json()) as {github:string}).github,'ok');
  const run=await call('/api/workflows/run','POST',{action:'sale'},adminToken);
  assert.equal(run.status,200);
  assert.equal(((await run.json()) as {started:string}).started,'sale.yml');
  const gone=await call('/api/approvals/decide','POST',{id:'abcdef123456',approve:true},adminToken);
  assert.equal(gone.status,404);
  assert.equal(((await gone.json()) as {error:string}).error,'expired or already decided');
  assert.equal((await call('/api/workflows/run','POST',{action:'BAD ACTION'},adminToken)).status,400);
  const viewerToken=await signin2('owner.two','Eight@8c');            // a viewer: app.access only
  assert.equal((await call('/api/workflows/run','POST',{action:'sale'},viewerToken)).status,403);
  assert.equal((await call('/api/approvals/decide','POST',{id:'abcdef123456',approve:true},viewerToken)).status,403);
});

test('app chat binds requests to the authenticated user and validates message length',async()=>{
  const token=await signin('admin@example.test');
  const actor=await db.prepare("SELECT id FROM user WHERE email='admin@example.test'").first<{id:string}>();
  const sent=await call('/api/agent/chat','POST',{text:'Hello',userId:'someone-else'},token);
  assert.equal(sent.status,202);
  assert.equal((await sent.json() as {id:string}).id,actor!.id);
  const history=await call('/api/agent/chat','GET',undefined,token);
  assert.equal(history.status,200);
  assert.equal((await history.json() as {messages:{question:string}[]}).messages[0].question,actor!.id);
  assert.equal((await call('/api/agent/chat','POST',{text:' '.repeat(3)},token)).status,400);
  assert.equal((await call('/api/agent/chat','POST',{text:'x'.repeat(2001)},token)).status,400);
  assert.equal((await call('/api/agent/chat')).status,401);
});

test('real chat routes isolate users, serialize requests and persist answers exactly once',async()=>{
  const one=(await signup('chatone@example.test'))!;
  const two=(await signup('chattwo@example.test'))!;
  for (const u of [one,two]) await db.prepare("UPDATE app_access SET status='active',role_id='admin' WHERE user_id=?").bind(u.id).run();
  const agent=makeAgent({repo:'example/test'});
  const env={AGENT_DB:db,AGENT_TOKEN:'test-token',GITHUB_TOKEN:'test-github'};
  const request=(path:string,method:string,input?:Record<string,unknown>)=>agent.route(new Request(`https://worker.test${path}`,{
    method,headers:{Authorization:'Bearer test-token','Content-Type':'application/json'},
    ...(input?{body:JSON.stringify(input)}:{})}),env,path)! as Promise<Response>;
  const original=globalThis.fetch;
  const dispatched:Record<string,unknown>[]=[];
  globalThis.fetch=(async(_url:unknown,init?:RequestInit)=>{dispatched.push(JSON.parse(String(init?.body)));return new Response(null,{status:204});}) as typeof fetch;
  try {
    const sent=await request('/api/app/chat','POST',{userId:one.id,text:'Private question'});
    assert.equal(sent.status,202);
    const {id}=await sent.json() as {id:string};
    assert.ok(!JSON.stringify(dispatched).includes('Private question'));
    assert.equal((await request('/api/app/chat','POST',{userId:one.id,text:'Another'})).status,409);
    assert.deepEqual(await (await request('/api/app/chat/history','POST',{userId:two.id})).json(),{messages:[]});
    const jobPath=`/api/app/chat/job/${id}`;
    assert.equal((await request(jobPath,'GET')).status,200);
    assert.equal((await request(jobPath,'GET')).status,404);
    assert.equal((await request(jobPath,'PUT',{status:'completed',answer:'Private answer'})).status,200);
    assert.equal((await request(jobPath,'PUT',{status:'completed',answer:'Replacement'})).status,409);
    const history=await (await request('/api/app/chat/history','POST',{userId:one.id})).json() as {messages:{answer:string}[]};
    assert.equal(history.messages[0].answer,'Private answer');
    const next=await request('/api/app/chat','POST',{userId:one.id,text:'Next'});
    const nextId=(await next.json() as {id:string}).id;
    await db.prepare("UPDATE app_access SET status='disabled' WHERE user_id=?").bind(one.id).run();
    assert.equal((await request(`/api/app/chat/job/${nextId}`,'GET')).status,404);
    assert.equal((await request('/api/app/chat/history','POST',{userId:one.id})).status,403);
    const expired=await request('/api/app/chat','POST',{userId:two.id,text:'Wait'});
    const expiredId=(await expired.json() as {id:string}).id;
    await db.prepare('UPDATE app_chat_job SET created_at=? WHERE id=?').bind(Date.now()-31*60000,expiredId).run();
    const expiredHistory=await (await request('/api/app/chat/history','POST',{userId:two.id})).json() as {messages:{status:string}[]};
    assert.equal(expiredHistory.messages[0].status,'failed');
  } finally {globalThis.fetch=original;}
});
