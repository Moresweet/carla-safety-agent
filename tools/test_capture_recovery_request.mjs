import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {stripTypeScriptTypes} from 'node:module';
const sourceCode=await readFile(new URL('./livery-designer/app/captureRecoveryRequest.ts',import.meta.url),'utf8');
const js=stripTypeScriptTypes(sourceCode).replace("'./captureRecoveryJob'",JSON.stringify(new URL('./livery-designer/app/captureRecoveryJob.ts',import.meta.url).href));
const {requestCaptureRecovery}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
const id='a'.repeat(32),source='capture-test';
const receipt={ok:true,request_id:id,source_run_id:source,state:'running'};
for(const mode of ['ok','network','http','wrong-id','headers-stall','body-stall','abort']){
 const outer=new AbortController();let calls=0,inner;
 const promise=requestCaptureRecovery(source,id,outer.signal,async(url,init)=>{
  calls++;inner=init.signal;
  assert.equal(url,'http://127.0.0.1:8765/datasets/recovery');
  assert.deepEqual(JSON.parse(init.body),{run_id:source,request_id:id,confirmed:true});
  if(mode==='network')throw Error('Connection lost');
  if(['headers-stall','abort'].includes(mode))return new Promise(()=>{});
  return {ok:mode!=='http',status:503,json:async()=>mode==='body-stall'?new Promise(()=>{}):mode==='wrong-id'?{...receipt,request_id:'other'}:receipt};
 },20);
 if(mode==='abort')outer.abort();
 if(mode==='ok')assert.equal((await promise).request_id,id);else await assert.rejects(promise);
 assert.equal(calls,1);
 if(['headers-stall','body-stall','abort'].includes(mode))assert.equal(inner.aborted,true);
}
const stopped=new AbortController();stopped.abort();let calls=0;
await assert.rejects(requestCaptureRecovery(source,id,stopped.signal,async()=>{calls++}));
assert.equal(calls,0);
console.log('Capture recovery: exact request, identity, bounded header/body waits, external abort, no auto retry passed');
