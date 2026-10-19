import assert from 'node:assert/strict';
import {batchApi,requireBatchIdentity} from './livery-designer/app/batchApi.ts';
assert.deepEqual(requireBatchIdentity({batch_id:'a',report:{rows:[]}},'a'),{rows:[]});
for(const id of [undefined,'b',''])assert.throws(()=>requireBatchIdentity({batch_id:id,report:{}},'a'),/身份不匹配/);
let calls=0,signal;
const never=async(_,options)=>{calls++;signal=options.signal;return new Promise(()=>{})};
await assert.rejects(batchApi('/batches',undefined,never,5),/读取超时/);
assert.equal(calls,1);assert.equal(signal.aborted,true);
await assert.rejects(batchApi('/batches/control',{action:'advance'},never,5),/执行结果未知/);
assert.equal(calls,2,'Writes must not retry');
let resolveBody;
await assert.rejects(batchApi('/batches',undefined,async()=>({ok:true,json:()=>new Promise(resolve=>resolveBody=resolve)}),5),/读取超时/);
resolveBody({ok:true});
for(const value of [null,{}, {ok:false,error:'blocked'}]){
 await assert.rejects(batchApi('/batches',undefined,async()=>({ok:true,json:async()=>value})),/无效|blocked/);
}
assert.deepEqual(await batchApi('/batches',undefined,async()=>({ok:true,json:async()=>({ok:true,batches:[]})})),{ok:true,batches:[]});
await assert.rejects(batchApi('/batches/control',{},async()=>{throw Error('offline')}),/offline/);
console.log('Batch API: bounded read/write/body, uncertain write, no retry, response contract and recovery passed');
