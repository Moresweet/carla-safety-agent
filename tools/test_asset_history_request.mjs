import assert from 'node:assert/strict';
import {readAssetHistory,parseAssetAttempts} from './livery-designer/app/assetHistoryRequest.ts';
const record={attempt_id:'abc',job_id:'abc',state:'exported',started_at:1,report_path:'/report'};
assert.equal(parseAssetAttempts([record],true).length,1);
for(const bad of [null,{},[null],[record,record],[{...record,state:'registered'}],[{...record,started_at:Infinity}],
 [{...record,error:{}}],[{...record,observation:{coordinator:'exited',requires_attention:'yes'}}],
 [{...record,registration_observation:{state:'matching'}}]])assert.throws(()=>parseAssetAttempts(bad,true));
for(const generation of [true,false]){
 const rows=await readAssetHistory(generation,new AbortController().signal,async url=>{
  assert.equal(url,`http://127.0.0.1:8765/blender/${generation?'generations':'imports'}`);
  return {ok:true,json:async()=>({ok:true,attempts:[]})};
 });assert.deepEqual(rows,[]);
}
for(const phase of ['headers','body']){
 let signal,calls=0;
 await assert.rejects(readAssetHistory(false,new AbortController().signal,async(_,options)=>{
  calls++;signal=options.signal;
  return phase==='headers'?new Promise(()=>{}):{ok:true,json:()=>new Promise(()=>{})};
 },10),/超时/);
 assert.equal(calls,1);assert.equal(signal.aborted,true);
}
const cancel=new AbortController();cancel.abort();
await assert.rejects(readAssetHistory(false,cancel.signal,async()=>assert.fail('must not fetch')),/取消/);
console.log('Asset history endpoint selection, header/body timeout and pre-abort passed');
