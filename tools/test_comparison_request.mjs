import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(specifier,context,next){
 return next(specifier==='./comparisonData'&&context.parentURL?.endsWith('/comparisonRequest.ts')?specifier+'.ts':specifier,context);
}});
const {readComparison}=await import('./livery-designer/app/comparisonRequest.ts');
const selection={batch_id:'test',axis:'weather',baseline:'clear',candidate:'rain'};
const body={ok:true,comparison:{...selection,comparable_count:0,pairs:[]}};
const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function start(transport,timeout=1000){
 const events=[];
 const cancel=readComparison(selection,v=>events.push(['value',v]),e=>events.push(['error',e]),()=>events.push(['finish']),transport,timeout);
 return {events,cancel};
}
const success=()=>Promise.resolve({ok:true,json:async()=>body});
let run=start(success);await flush();assert.deepEqual(run.events.map(e=>e[0]),['value','finish']);run.cancel();
for(const transport of [async()=>{throw Error('network')},async()=>({ok:false,status:503}),async()=>({ok:true,json:async()=>{throw Error('invalid JSON')}})]){
 run=start(transport);await flush();assert.deepEqual(run.events.map(e=>e[0]),['error','finish']);run.cancel();
}
let resolveBody,signal;
run=start(async(_,options)=>{signal=options.signal;return {ok:true,json:()=>new Promise(resolve=>resolveBody=resolve)}},10);
await delay(30);assert.equal(signal.aborted,true);assert.match(run.events[0][1],/超时/);assert.equal(run.events.length,2);
resolveBody(body);await flush();assert.equal(run.events.length,2,'Late JSON after timeout must not publish or finish twice');
run=start(success);await flush();assert.equal(run.events[0][0],'value','Independent retry succeeds');run.cancel();
let resolveOld;
const old=start(()=>new Promise(resolve=>resolveOld=resolve));old.cancel();
const newer=start(success);await flush();resolveOld({ok:true,json:async()=>body});await flush();
assert.deepEqual(old.events,[],'Cancelled selection cannot overwrite newer result');
assert.deepEqual(newer.events.map(e=>e[0]),['value','finish']);newer.cancel();
const unmounted=start(()=>new Promise(()=>{}),10);unmounted.cancel();await delay(30);assert.deepEqual(unmounted.events,[]);
console.log('Comparison request: success, network/HTTP/JSON errors, body timeout, retry, stale response and disposal passed');
