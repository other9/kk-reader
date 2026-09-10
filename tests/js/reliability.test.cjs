const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const source = name => fs.readFileSync(path.join(root,name),'utf8');

function clientFixture() {
  const data = new Map([['kkreader.syncToken','test-only']]);
  const timers = new Map();
  let next=0;
  const ctx=vm.createContext({window:{},Date,URLSearchParams,AbortController,
    localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)},
    setTimeout:(fn,ms)=>{timers.set(++next,{fn,ms});return next;},
    clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source('docs/sync.js')+';globalThis.Client=SyncClient;',ctx);
  return {client:new ctx.Client(),data,timers,ctx};
}

test('failed batch preserves edits added in flight and is persisted for restart', async()=>{
  const {client:c,data,ctx}=clientFixture();
  let finish;
  c.pushDiff=()=>new Promise(resolve=>{finish=resolve;});
  c.queueDiff('fav',{id:'a',state:1,ts:1});
  const flight=c.flush();
  assert(data.has('kkreader.pendingDiff'));
  c.queueDiff('fav',{id:'b',state:1,ts:2});
  assert.equal(c.flush(),flight);
  finish(null);
  await flight;
  assert.deepEqual(Array.from(c.pending.fav,e=>e.id),['a','b']);
  const restarted=new ctx.Client();
  assert.deepEqual(Array.from(restarted.pending.fav,e=>e.id),['a','b']);
});

test('acknowledging an old value does not delete a newer toggle of same article', async()=>{
  const {client:c,data}=clientFixture();
  let finish;
  c.pushDiff=()=>new Promise(resolve=>{finish=resolve;});
  c.queueDiff('fav',{id:'a',state:1,ts:1});
  const flight=c.flush();
  c.queueDiff('fav',{id:'a',state:0,ts:2});
  finish({read:{},fav:{}});
  await flight;
  assert.equal(c.pending.fav[0].state,0);
  c.pushDiff=async()=>({read:{},fav:{}});
  await c.flush();
  assert.equal(c.pending,null);
  assert(!data.has('kkreader.pendingDiff'));
});

test('network failure schedules retry without a new user action', async()=>{
  const {client:c,timers}=clientFixture();
  let calls=0;
  c.pushDiff=async()=>++calls===1?null:{read:{},fav:{}};
  c.queueDiff('read',{id:'a',state:1,ts:1});
  await c.flush();
  assert.equal(timers.size,1);
  const retry=[...timers.values()][0];
  assert.equal(retry.ms,6000);
  await retry.fn();
  assert.equal(calls,2);
  assert.equal(c.pending,null);
});

function workerFixture(legacy={read:{},fav:{}}, persisted=new Map()) {
  let queue=Promise.resolve();
  const ctx={
    storage:{get:async k=>structuredClone(persisted.get(k)),put:async(k,v)=>{persisted.set(k,structuredClone(v));}},
    blockConcurrencyWhile: fn=>{
      const work=queue.then(fn);
      queue=work.catch(()=>{});
      return work;
    }
  };
  let imports=0;
  const env={STATE:{get:async()=>{imports++;return structuredClone(legacy);}}};
  const sandbox=vm.createContext({Request,Response,URL,Date});
  vm.runInContext(source('worker/worker.js').replace('export class SyncState','class SyncState')
    .replace('export default {','globalThis.worker = {')+';globalThis.State=SyncState;',sandbox);
  const object=new sandbox.State(ctx,env);
  const request=diff=>new Request('https://test.invalid/'+(diff?'state/diff':'state'),{
    method:diff?'POST':'GET',headers:{Origin:'https://kk-reader.pages.dev','Content-Type':'application/json'},
    ...(diff?{body:JSON.stringify(diff)}:{})});
  return {object,request,persisted,imports:()=>imports,sandbox};
}

test('concurrent writes preserve both favorites and survive object restart', async()=>{
  const f=workerFixture({read:{old:{state:1,ts:1}},fav:{}});
  const replies=await Promise.all(['a','b'].map(id=>f.object.fetch(f.request({fav:[{id,state:1,ts:2}]}))));
  assert(replies.every(r=>r.status===200));
  const state=await (await f.object.fetch(f.request())).json();
  assert.deepEqual(Object.keys(state.fav).sort(),['a','b']);
  assert.equal(state.read.old.state,1);
  assert.equal(f.imports(),1);
  const restarted=workerFixture(null,f.persisted);
  assert.equal((await restarted.object.fetch(restarted.request())).status,200);
  assert.equal(restarted.imports(),0);
});

test('missing/corrupt legacy KV never initializes an empty authoritative state',async()=>{
  for(const legacy of [null,{}, {read:{},fav:[]},{read:{},fav:{bad:{state:1,ts:'bad'}}}]){
    const f=workerFixture(legacy);
    assert.equal((await f.object.fetch(f.request())).status,503);
    assert.equal(f.persisted.size,0);
  }
});

test('LWW preserves newer state and records explicit favorite removal',async()=>{
  const f=workerFixture({read:{},fav:{a:{state:1,ts:10}}});
  await f.object.fetch(f.request({fav:[{id:'a',state:0,ts:9}]}));
  let state=await (await f.object.fetch(f.request())).json();
  assert.equal(state.fav.a.state,1);
  await f.object.fetch(f.request({fav:[{id:'a',state:0,ts:11}]}));
  state=await (await f.object.fetch(f.request())).json();
  assert.equal(state.fav.a.state,0);
});

test('outer routing authenticates before reaching state and preserves CORS',async()=>{
  const f=workerFixture();
  let forwarded=0;
  const env={SYNC_SECRET:'test-only',SYNC_STATE:{
    idFromName:name=>name,get:()=>({fetch:req=>{forwarded++;return f.object.fetch(req);}})}};
  const unauth=await f.sandbox.worker.fetch(f.request(),env);
  assert.equal(unauth.status,401);
  assert.equal(forwarded,0);
  const req=f.request();
  req.headers.set('Authorization','Bearer test-only');
  const reply=await f.sandbox.worker.fetch(req,env);
  assert.equal(reply.status,200);
  assert.equal(reply.headers.get('Access-Control-Allow-Origin'),'https://kk-reader.pages.dev');
});

test('retry uses a click listener without inline script, retaining strict CSP',async()=>{
  const app=source('docs/app.js');
  const start=app.indexOf('async function renderArticleBodyLazy');
  const end=app.indexOf('window.retryArticleFetch =',start);
  let listener, retried;
  const body={innerHTML:'',querySelector:()=>({addEventListener:(event,fn)=>{
    assert.equal(event,'click');listener=fn;
  }})};
  const ctx=vm.createContext({state:{selectedId:'article'},escapeHtml:s=>s,
    window:{kkSync:{client:{enabled:true,fetchArticle:async()=>({ok:false,error:'offline'})}},
      retryArticleFetch:id=>{retried=id;}}});
  vm.runInContext(app.slice(start,end),ctx);
  await ctx.renderArticleBodyLazy({id:'article',url:'https://example.invalid'},body);
  assert(!body.innerHTML.includes('onclick='));
  listener();
  assert.equal(retried,'article');
  assert(source('docs/index.html').includes("script-src 'self'"));
});

test('hung POST times out without dropping persisted operations',async()=>{
  const {client:c,timers,ctx,data}=clientFixture();
  ctx.fetch=(url,options)=>new Promise((resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(new Error('timed out')));
  });
  c.queueDiff('fav',{id:'a',state:1,ts:1});
  const work=c.flush();
  const timeout=[...timers.values()].find(timer=>timer.ms===15000);
  assert(timeout);
  timeout.fn();
  await work;
  assert.equal(c.pending.fav.length,1);
  assert(data.has('kkreader.pendingDiff'));
  assert([...timers.values()].some(timer=>timer.ms===6000));
});

test('malformed success response is not an acknowledgement',async()=>{
  const {client:c,ctx}=clientFixture();
  ctx.fetch=async()=>({ok:true,json:async()=>({ok:true})});
  c.queueDiff('fav',{id:'a',state:1,ts:1});
  await c.flush();
  assert.equal(c.pending.fav.length,1);
  assert.equal(c.lastSync,null);
});
