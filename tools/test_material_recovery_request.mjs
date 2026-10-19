import assert from 'node:assert/strict';
import {requestMaterialRecovery} from './livery-designer/app/materialRecoveryRequest.ts';
const inspection={recoverable:true,token:'a'.repeat(64),registered:'b'.repeat(64),source:null,target:'b'.repeat(64)};
const receipt={ok:true,operation_id:'op',recovery:{state:'confirmed',choice:'source',desired:null}};
let calls=0;
await requestMaterialRecovery('op',inspection,'source',async(url,init)=>{
 calls++;assert.equal(init.method,'POST');assert.equal(url,'http://127.0.0.1:8765/materials/history-recover');
 assert.deepEqual(JSON.parse(init.body),{operation_id:'op',inspection_token:inspection.token,choice:'source',registered_texture:inspection.registered,confirmed:true});
 return {ok:true,json:async()=>receipt};
});
assert.equal(calls,1);
await requestMaterialRecovery('op',inspection,'source',async(url)=>{
 assert.equal(url,'http://127.0.0.1:8765/materials/actor-history-recover');
 return {ok:true,json:async()=>receipt};
},30000,true);
for(const response of [null,[],{}, {...receipt,operation_id:'other'},{...receipt,recovery:{...receipt.recovery,desired:inspection.target}},{...receipt,recovery:{...receipt.recovery,state:'attempting'}}]){
 calls=0;await assert.rejects(requestMaterialRecovery('op',inspection,'source',async()=>{calls++;return {ok:true,json:async()=>response}}));assert.equal(calls,1);
}
for(const fail of ['network','http','json','fetch-timeout','body-timeout']){
 calls=0;let signal;
 await assert.rejects(requestMaterialRecovery('op',inspection,'source',async(_,init)=>{
  calls++;signal=init.signal;
  if(fail==='network')throw Error('Connection lost after write');
  if(fail==='fetch-timeout')return new Promise(()=>{});
  return {ok:fail!=='http',json:()=>fail==='json'?Promise.reject(Error('Invalid JSON')):fail==='body-timeout'?new Promise(()=>{}):Promise.resolve(receipt)};
 },20));
 assert.equal(calls,1);if(fail.endsWith('timeout'))assert.equal(signal.aborted,true);
}
calls=0;await assert.rejects(requestMaterialRecovery('op',{...inspection,recoverable:false},'source',async()=>{calls++}));assert.equal(calls,0);
console.log('Material recovery: exact write, receipt identity, network/HTTP/JSON failure, header/body timeout and no automatic retry passed');
