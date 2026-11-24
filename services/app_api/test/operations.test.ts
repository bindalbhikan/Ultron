import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { createTestHarness, unstable_splitSqlQuery, type TestHarness } from 'wrangler';
import { makeAgent } from '../../../worker/agent.js';
import { phoneJobs } from '../../../worker/phone.js';
import { releases } from '../src/releases';
import { RELEASE_LIMITS } from '../src/release_limits';

let server: TestHarness;
let db: D1Database;
before(async () => {
  server = createTestHarness({workers:[{configPath:'wrangler.jsonc',secrets:{AUTH_SECRET:'public-integration-secret-32-characters-minimum'}},{configPath:'test/ops_stub/wrangler.jsonc'}]});
  await server.listen();
  db = (await server.getWorker<{DB:D1Database}>().getEnv()).DB;
  for (const file of readdirSync('migrations').filter(f=>f.endsWith('.sql')).sort()) {
    await db.batch(unstable_splitSqlQuery(readFileSync('migrations/'+file,'utf8')).map(sql=>db.prepare(sql)));
  }
});
after(async () => { await server?.close(); });

test('overlapping phone jobs retain independent results and claim each job once', async () => {
  const env = {AGENT_DB:db};
  const call = (action:string, data?:object, query='') => phoneJobs(new Request('https://worker.test/api/phone/'+action+query,
    {method:'POST',body:JSON.stringify(data??{})}),env,action);
  for (const id of ['myntra_style-zero-td','grouping']) assert.equal((await call('job',{id,kind:'myntra_style',items:[123]})).status,200);
  const claimed = await Promise.all([call('next'),call('next')]);
  const ids = await Promise.all(claimed.map(async r=>(await r.json() as {id:string}).id));
  assert.equal(new Set(ids).size,2);
  assert.deepEqual(await (await call('next')).json(),{});
  assert.equal((await call('result',{},'?job=myntra_style-zero-td&part=-1')).status,400);
  await call('result',{'123':{price:1}},'?job=myntra_style-zero-td&part=0&last=1');
  await call('result',{'123':{colours:[456]}},'?job=grouping&part=0&last=1');
  const zero = await (await call('collect',{},'?job=myntra_style-zero-td')).json() as {done:number;results:object};
  const group = await (await call('collect',{},'?job=grouping')).json() as {done:number;results:object};
  assert.equal(zero.done,1); assert.equal(group.done,1);
  assert.deepEqual(zero.results,{'123':{price:1}});
  assert.deepEqual(group.results,{'123':{colours:[456]}});
  assert.equal((await call('job',{id:'myntra_style-zero-td',kind:'myntra_style',items:[123]})).status,409);
});

test('concurrent approvals dispatch once; refusal retains request; ambiguous failure cannot retry', async () => {
  const original = globalThis.fetch;
  const saved = new Map<string,string>();
  const kv = {get:async(key:string,type?:string)=>{const v=saved.get(key);return v ? type==='json'?JSON.parse(v):v : null;},
    put:async(key:string,value:string)=>{saved.set(key,value);},delete:async(key:string)=>{saved.delete(key);}};
  const agent = makeAgent({repo:'example/test'});
  const env = {AGENT_DB:db,AGENT_KV:kv,AGENT_TOKEN:'test-token',AGENT_ACTIONS:{sale:{workflow:'sale.yml',inputs:[]}}};
  const seed = (id:string)=>saved.set('approval:'+id,JSON.stringify({action:'sale',inputs:{},chat:'test',at:Date.now()}));
  const decide = (id:string)=>agent.route(new Request('https://worker.test/api/app/decide',{method:'POST',
    headers:{Authorization:'Bearer test-token'},body:JSON.stringify({id,approve:true})}),env,'/api/app/decide') as Promise<Response>;
  let calls=0, status=204;
  globalThis.fetch=(async(url:unknown)=>{
    if (String(url).includes('api.github.com')) {calls++;return new Response(null,{status});}
    return Response.json({ok:true});
  }) as typeof fetch;
  try {
    seed('aaaaaa111111');
    const responses=await Promise.all([decide('aaaaaa111111'),decide('aaaaaa111111')]);
    assert.equal(calls,1);
    assert.deepEqual(responses.map(r=>r.status).sort(),[200,409]);
    seed('bbbbbb222222'); status=403;
    assert.equal((await decide('bbbbbb222222')).status,502);
    assert.ok(saved.has('approval:bbbbbb222222'));
    status=204;assert.equal((await decide('bbbbbb222222')).status,200);
    seed('cccccc333333');status=500;
    assert.equal((await decide('cccccc333333')).status,502);
    const before=calls;assert.equal((await decide('cccccc333333')).status,409);assert.equal(calls,before);
  } finally {globalThis.fetch=original;}
});

test('completed multipart releases advance monotonically and serve their verified metadata', async () => {
  const objects = new Map<string, any>();
  const pending = new Map<string, any>();
  let sequence = 0;
  const bucket = {
    createMultipartUpload: async (key:string, options:any) => {
      const uploadId = String(++sequence);
      pending.set(uploadId,{key,meta:options.customMetadata,parts:[]});
      return {uploadId};
    },
    resumeMultipartUpload: (key:string, id:string) => ({
      uploadPart: async (partNumber:number, body:ReadableStream) => {
        const bytes = new Uint8Array(await new Response(body).arrayBuffer());
        pending.get(id).parts[partNumber-1]=bytes;
        return {partNumber,etag:'part-'+partNumber};
      },
      complete: async (_parts:unknown) => {
        const upload = pending.get(id);
        const payload = Buffer.concat(upload.parts);
        const object = {size:payload.length,customMetadata:upload.meta,httpEtag:'"release"',payload,range:{offset:0,length:payload.length}};
        objects.set(key,object);
        // Completion responses need not include persisted custom metadata.
        return {size:payload.length,httpEtag:'"release"',customMetadata:{}};
      },
    }),
    get: async (key:string) => {
      const obj=objects.get(key);
      return obj ? {...obj,body:new Response(obj.payload).body} : null;
    },
    head: async (key:string) => objects.get(key) ?? null,
  };
  const env={DB:db,RELEASES:bucket,WORKER_TOKEN:'private-test-token'} as unknown as Parameters<typeof releases>[1];
  const call=async(path:string,method='GET',body?:any)=>releases(new Request('https://api.test'+path,{
    method,headers:{Authorization:'Bearer private-test-token',...(body instanceof Uint8Array?{'Content-Length':String(body.length)}:{})},
    ...(body!==undefined?{body:body instanceof Uint8Array?body:JSON.stringify(body)}:{})
  }),env);
  for (const build of [200,199]) {
    const start=await call('/api/releases/upload','POST',{platform:'android',version:'0.1.42',build,size:3,sha256:'a'.repeat(64)});
    assert.equal(start!.status,200);
    const upload=await start!.json() as Record<string,string>;
    const query=new URLSearchParams(upload).toString();
    const part=await call('/api/releases/upload?'+query+'&part=1','PUT',new Uint8Array([1,2,3]));
    assert.equal(part!.status,200);
    const complete=await call('/api/releases/complete?'+query,'POST',{parts:[await part!.json()]});
    assert.equal(complete!.status,200);
  }
  const manifest=await (await call('/api/releases/latest?platform=android'))!.json() as {build:number;size:number;url:string;sha256:string};
  assert.equal(manifest.build,200);
  assert.equal(manifest.size,3);
  assert.equal(manifest.sha256,'a'.repeat(64));
  const download=await releases(new Request(manifest.url),env);
  assert.equal(download!.status,200);
  assert.equal(download!.headers.get('Content-Range'),null);
  assert.deepEqual([...new Uint8Array(await download!.arrayBuffer())],[1,2,3]);
  const head=await releases(new Request(manifest.url,{method:'HEAD'}),env);
  assert.equal(head!.status,200);
  assert.equal(head!.headers.get('Content-Length'),'3');
  assert.equal(head!.headers.get('Content-Range'),null);
  const ranged=await releases(new Request(manifest.url,{headers:{Range:'bytes=0-2'}}),env);
  assert.equal(ranged!.status,206);
  assert.equal(ranged!.headers.get('Content-Range'),'bytes 0-2/3');
});

test('concurrent download requests cannot cross the R2 read budget', async () => {
  const period=new Date().toISOString().slice(0,7);
  const old=await db.prepare("SELECT used FROM release_usage WHERE period=? AND kind='B'").bind(period).first<{used:number}>();
  await db.prepare("INSERT OR REPLACE INTO release_usage(period,kind,used) VALUES(?,'B',?)").bind(period,RELEASE_LIMITS.classB-1).run();
  let reads=0;
  const env={DB:db,RELEASES:{head:async()=>{reads++;return null;}} as unknown as R2Bucket} as Parameters<typeof releases>[1];
  const url='https://api.test/api/releases/files/releases/200/android/'+'a'.repeat(64)+'/ULTRON.apk';
  const responses=await Promise.all([releases(new Request(url,{method:'HEAD'}),env),releases(new Request(url,{method:'HEAD'}),env)]);
  assert.equal(reads,1);
  assert.deepEqual(responses.map(r=>r!.status).sort(),[404,429]);
  const used=await db.prepare("SELECT used FROM release_usage WHERE period=? AND kind='B'").bind(period).first<{used:number}>();
  assert.equal(used!.used,RELEASE_LIMITS.classB);
  await db.prepare("UPDATE release_usage SET used=? WHERE period=? AND kind='B'").bind(old?.used??0,period).run();
});

test('concurrent upload reservations cannot cross the storage budget and part sizes cannot bypass it', async () => {
  const existing=await db.prepare('SELECT COALESCE(SUM(size),0) AS n FROM release_upload').first<{n:number}>();
  await db.prepare("INSERT INTO release_upload(id,object_key,size,created) VALUES('test-fill','test-fill',?,0)")
    .bind(RELEASE_LIMITS.storageBytes-existing!.n-3).run();
  let creates=0,parts=0;
  const env={DB:db,WORKER_TOKEN:'private-test-token',RELEASES:{
    createMultipartUpload:async()=>({uploadId:'budget-'+(++creates)}),
    resumeMultipartUpload:()=>({uploadPart:async()=>{parts++;return {};}}),
  } as unknown as R2Bucket} as Parameters<typeof releases>[1];
  const start=(build:number)=>releases(new Request('https://api.test/api/releases/upload',{method:'POST',
    headers:{Authorization:'Bearer private-test-token'},
    body:JSON.stringify({platform:'android',version:'0.1.43',build,size:3,sha256:'b'.repeat(64)})}),env);
  const responses=await Promise.all([start(300),start(301)]);
  assert.equal(creates,1);
  assert.deepEqual(responses.map(r=>r!.status).sort(),[200,429]);
  const upload=await responses.find(r=>r!.status===200)!.json() as Record<string,string>;
  const result=await releases(new Request('https://api.test/api/releases/upload?'+new URLSearchParams({...upload,part:'1'}),{
    method:'PUT',headers:{Authorization:'Bearer private-test-token','Content-Length':'4'},body:new Uint8Array([1,2,3,4]),
  }),env);
  assert.equal(result!.status,400);
  assert.equal(parts,0);
  const reserved=await db.prepare('SELECT SUM(size) AS n FROM release_upload').first<{n:number}>();
  assert.equal(reserved!.n,RELEASE_LIMITS.storageBytes);
  await db.prepare("DELETE FROM release_upload WHERE id='test-fill'").run();
});

test('the write budget stops upload initialization before R2 and failed accounting fails closed', async () => {
  const period=new Date().toISOString().slice(0,7);
  const old=await db.prepare("SELECT used FROM release_usage WHERE period=? AND kind='A'").bind(period).first<{used:number}>();
  await db.prepare("INSERT OR REPLACE INTO release_usage(period,kind,used) VALUES(?,'A',?)").bind(period,RELEASE_LIMITS.classA).run();
  let creates=0;
  const env={DB:db,WORKER_TOKEN:'private-test-token',RELEASES:{createMultipartUpload:async()=>{creates++;return {uploadId:'unused'};}} as unknown as R2Bucket} as Parameters<typeof releases>[1];
  const request=()=>new Request('https://api.test/api/releases/upload',{method:'POST',headers:{Authorization:'Bearer private-test-token'},
    body:JSON.stringify({platform:'android',version:'0.1.44',build:400,size:3,sha256:'c'.repeat(64)})});
  assert.equal((await releases(request(),env))!.status,429);
  assert.equal(creates,0);
  await db.prepare("UPDATE release_usage SET used=? WHERE period=? AND kind='A'").bind(old?.used??0,period).run();
  const failing={prepare:()=>{throw new Error('accounting unavailable');}} as unknown as D1Database;
  await assert.rejects(()=>releases(request(),{...env,DB:failing}),/accounting unavailable/);
  assert.equal(creates,0);
});

test('release endpoints fail closed without storage and publishing requires the private credential', async () => {
  const env={DB:db,RELEASES:{} as R2Bucket,WORKER_TOKEN:'test-worker'} as Parameters<typeof releases>[1];
  assert.equal((await releases(new Request('https://api.test/api/releases/latest?platform=android'),{...env,RELEASES:undefined}))!.status,503);
  assert.equal((await releases(new Request('https://api.test/api/releases/upload',{method:'POST'}),env))!.status,403);
  assert.equal((await releases(new Request('https://api.test/api/releases/files/../../private'),env)),null);
});
