import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(specifier,context,next){
 return next(specifier==='./batchApi'&&context.parentURL?.endsWith('/recordingControl.ts')?specifier+'.ts':specifier,context);
}});
const {setRecording}=await import('./livery-designer/app/recordingControl.ts');
const response=value=>({ok:true,json:async()=>value});
const session={ok:true,session:{run_id:'execution-a',state:'running'}};
for(const every of [0,101,1.5,NaN,Infinity,'5']){
 let calls=0;
 await assert.rejects(setRecording(true,every,async()=>{calls++;throw Error('must not fetch')}),/整数/);
 assert.equal(calls,0);
}
for(const recording of [true,false]){
 const calls=[];
 await setRecording(recording,2,async(url,options)=>{
  calls.push({url,options});
  if(calls.length===1)return response(session);
  assert.deepEqual(JSON.parse(options.body),{run_id:'execution-a',recording,...(recording?{every:2,max_frames:2000}:{})});
  return response({ok:true,request:{execution_id:'execution-a',recording}});
 });
 assert.equal(calls.length,2);
 assert.ok(calls[0].url.endsWith('/session/status'));
 assert.ok(calls[1].url.endsWith('/collection/recording'));
}
let stopCalls=0;
await setRecording(false,NaN,async(_,options)=>{
 if(++stopCalls===1)return response(session);
 assert.deepEqual(JSON.parse(options.body),{run_id:'execution-a',recording:false});
 return response({ok:true,request:{execution_id:'execution-a',recording:false}});
});
assert.equal(stopCalls,2,'Invalid sampling draft must not prevent stopping');
for(const state of ['stopped','recovering','preparing']){
 let calls=0;
 await assert.rejects(setRecording(true,1,async()=>{calls++;return response({ok:true,session:{run_id:'a',state}})}),/没有正在运行/);
 assert.equal(calls,1,'No write without running session');
}
for(const failure of ['changed','lost','identity','value']){
 let calls=0;
 await assert.rejects(setRecording(true,1,async()=>{
  calls++;if(calls===1)return response(session);
  if(failure==='changed')return {ok:false,json:async()=>({ok:false,error:'No matching live recording session'})};
  if(failure==='lost')throw Error('response lost');
  return response({ok:true,request:{execution_id:failure==='identity'?'other':'execution-a',recording:failure!=='value'}});
 }));
 assert.equal(calls,2,'Uncertain writes must never retry or retarget');
}
console.log('Recording control: identity, stopped sessions, session change, lost response and no write replay passed');
