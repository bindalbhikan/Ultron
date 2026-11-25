import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { createTestHarness, unstable_splitSqlQuery, type TestHarness } from 'wrangler';
import { makeAgent } from '../../../worker/agent.js';

let server: TestHarness, db: D1Database;
const stored = new Map<string,string>();
const kv = {get:async(k:string,type?:string)=>{const v=stored.get(k);return v ? type==='json'?JSON.parse(v):v : null;},
  put:async(k:string,v:string)=>{stored.set(k,v);},delete:async(k:string)=>{stored.delete(k);}};
const agent = makeAgent({repo:'example/test',allowedChat:(_env:unknown,id:string)=>id==='owner-chat',
  schedule:[{cmd:'report',workflow:'report.yml',name:'Report',cron:'30 3 * * *',ist:'9:00 AM daily'},
            {cmd:'stock',workflow:'stock.yml',name:'Stock',cron:'0 4 * * *',ist:'9:30 AM daily'}]});
let env:Record<string,unknown>;
let requests:{url:string;body:any}[]=[];
let runStatus='in_progress', runFile='report.yml';
let original:typeof fetch;
const call=(actor:object,operation:string,args:object={},extra:object={})=>agent.route(new Request('https://worker.test/api/control',{
  method:'POST',headers:{Authorization:'Bearer test-token','Content-Type':'application/json'},
  body:JSON.stringify({actor,operation,args,...extra})}),env,'/api/control') as Promise<Response>;
const app=(id='control-owner')=>({source:'app',userId:id});
before(async()=>{
  server=createTestHarness({workers:[{configPath:'wrangler.jsonc',secrets:{AUTH_SECRET:'public-control-test-secret-32-characters',WORKER_TOKEN:'test-token'}},{configPath:'test/ops_stub/wrangler.jsonc'}]});
  await server.listen();
  db=(await server.getWorker<{DB:D1Database}>().getEnv()).DB;
  for(const f of readdirSync('migrations').filter(f=>f.endsWith('.sql')).sort())
    await db.batch(unstable_splitSqlQuery(readFileSync('migrations/'+f,'utf8')).map(sql=>db.prepare(sql)));
  await db.prepare("INSERT INTO app_role(id,name,permissions) VALUES('control-runner','Runner',?)").bind(JSON.stringify(['app.access','agent.chat','workflows.read','workflows.run','schedule.read','approvals.read','approvals.decide'])).run();
  await db.prepare("INSERT INTO app_role(id,name,permissions) VALUES('control-viewer','Viewer',?)").bind(JSON.stringify(['app.access','agent.chat','workflows.read'])).run();
  for(const [id,role] of [['control-owner','admin'],['control-runner','control-runner'],['control-viewer','control-viewer']]) {
    await db.prepare('INSERT INTO user(id,name,email,created_at,updated_at) VALUES(?,?,?,1,1)').bind(id,id,id+'@example.test').run();
    await db.prepare("UPDATE app_access SET status='active',role_id=? WHERE user_id=?").bind(role,id).run();
  }
  env={APP:{fetch:(url:string,init:Parameters<TestHarness['fetch']>[1])=>server.fetch(url,init)},AGENT_DB:db,AGENT_KV:kv,AGENT_TOKEN:'test-token',ALLOWED_CHAT_IDS:'owner-chat',
    AGENT_ACTIONS:{report:{workflow:'report.yml',inputs:['day'],auto:true},inventory:{workflow:'inventory.yml',inputs:['dry_run']}}};
  original=globalThis.fetch;
  globalThis.fetch=(async(url:unknown,init?:RequestInit)=>{
    const address=String(url);requests.push({url:address,body:init?.body?JSON.parse(String(init.body)):null});
    if(address.includes('/actions/runs/')) {
      if(init?.method==='POST') return new Response(null,{status:202});
      return Response.json({path:'.github/workflows/'+runFile,status:runStatus,event:'workflow_dispatch',head_repository:{full_name:'example/test'}});
    }
    return address.includes('api.github.com')?new Response(null,{status:204}):Response.json({ok:true});
  }) as typeof fetch;
});
after(async()=>{globalThis.fetch=original;await server?.close();});

test('app and Telegram use the same preview and validation; Preview never dispatches',async()=>{
  const before=requests.length;
  const inputs={action:'inventory',inputs:{dry_run:'1'}};
  const a=await call(app(),'workflow.run',inputs,{preview:true,confirmed:true});
  const t=await call({source:'telegram',chatId:'owner-chat'},'workflow.run',inputs,{preview:true,confirmed:true});
  assert.equal(a.status,200);assert.deepEqual(await a.json(),await t.json());
  assert.equal(requests.length,before);
  assert.equal((await call(app(),'workflow.run',{action:'inventory',inputs:{secret:'bad'}},{preview:true})).status,400);
  assert.equal((await call(app('control-viewer'),'workflow.run',inputs,{preview:true})).status,403);
  assert.equal(requests.length,before);
});

test('user permissions are read from D1 and cannot be supplied by the model or client',async()=>{
  const r=await call({...app('control-viewer'),permissions:['*']},'workflow.run',{action:'report'},{confirmed:true});
  assert.equal(r.status,403);
  assert.equal((await call({source:'system'},'workflow.run',{action:'report'},{confirmed:true})).status,403);
  assert.equal((await call({source:'telegram',chatId:'someone-else'},'model.get')).status,403);
  const catalog=await (await call(app('control-runner'),'catalog')).json() as any;
  assert.ok(catalog.operations['workflow.run']);assert.equal(catalog.operations['model.set'],undefined);
});

test('a claimed app chat job cannot borrow an owner identity or self-confirm a live action',async()=>{
  const job='10000000-0000-4000-8000-000000000001';
  await db.prepare("INSERT INTO app_chat_job(id,user_id,question,status,created_at,updated_at) VALUES(?,'control-runner','test','running',?,?)")
    .bind(job,Date.now(),Date.now()).run();
  const before=requests.filter(r=>r.url.includes('api.github.com')).length;
  const proposed=await call({source:'job',jobId:job,userId:'control-owner'},'workflow.run',{action:'inventory'},{confirmed:true});
  assert.equal(proposed.status,200);const out=await proposed.json() as any;assert.ok(out.proposed);
  assert.equal(requests.filter(r=>r.url.includes('api.github.com')).length,before);
  assert.equal((await call({source:'job',jobId:job,userId:'control-owner'},'model.set',{model:'auto'})).status,403);
  await db.prepare("UPDATE app_access SET role_id='control-viewer' WHERE user_id='control-runner'").run();
  const response=await agent.route(new Request('https://worker.test/api/app/decide',{method:'POST',headers:{Authorization:'Bearer test-token'},
    body:JSON.stringify({id:out.proposed,approve:true,userId:'control-owner'})}),env,'/api/app/decide') as Response;
  assert.equal(response.status,403);
  assert.equal(requests.filter(r=>r.url.includes('api.github.com')).length,before);
  await db.prepare("UPDATE app_access SET role_id='control-runner' WHERE user_id='control-runner'").run();
  await db.prepare("UPDATE app_chat_job SET status='completed' WHERE id=?").bind(job).run();
  assert.equal((await call({source:'job',jobId:job},'catalog')).status,403);
});

test('shared cancel and rerun reject runs outside the action catalog and enforce run state',async()=>{
  runStatus='in_progress';runFile='report.yml';
  assert.equal((await call(app(),'workflow.cancel',{runId:'123'},{confirmed:true})).status,200);
  assert.equal((await call(app(),'workflow.rerun',{runId:'123'},{confirmed:true})).status,409);
  runStatus='completed';
  assert.equal((await call({source:'telegram',chatId:'owner-chat'},'workflow.rerun',{runId:'123'},{confirmed:true})).status,200);
  runFile='ci-fix.yml';
  assert.equal((await call(app(),'workflow.rerun',{runId:'123'},{confirmed:true})).status,403);
});

test('app and Telegram model settings reuse the same account handlers',async()=>{
  const before=await (await call(app(),'model.get')).json() as any;
  const settings={...before.settings,model:'groq:openai/gpt-oss-120b'};
  delete settings.providers;delete settings.tiers;
  const changed=await call({source:'telegram',chatId:'owner-chat'},'model.set',settings,{confirmed:true});
  assert.equal(changed.status,200);
  const after=await (await call(app(),'model.get')).json() as any;
  assert.equal(after.settings.model,'groq:openai/gpt-oss-120b');
  assert.equal(after.settings.revision,before.settings.revision+1);
  assert.equal((await call(app('control-viewer'),'model.get')).status,403);
});

test('runtime schedule edits preserve revisions and append history atomically',async()=>{
  const catalog=await (await call(app(),'catalog')).json() as any;
  const item=catalog.schedule[0];
  assert.equal((await call(app(),'schedule.set',{id:item.id,enabled:false,cron:item.cron,revision:0},{confirmed:true})).status,200);
  assert.equal((await call(app(),'schedule.set',{id:item.id,enabled:true,cron:item.cron,revision:0},{confirmed:true})).status,409);
  assert.equal((await call(app(),'schedule.set',{id:item.id,enabled:true,cron:'0 4 * * *',revision:1},{confirmed:true})).status,200);
  const current=await (await call(app(),'schedule.list')).json() as any;
  assert.equal(current.schedule[0].enabled,true);assert.equal(current.schedule[0].ist,'9:30 AM daily');assert.equal(current.schedule[0].revision,2);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM agent_schedule_history').first<{n:number}>())!.n,2);
  assert.equal((await call(app(),'schedule.set',{id:item.id,enabled:true,cron:'15 4 * * *',revision:2},{preview:true})).status,400);
});
