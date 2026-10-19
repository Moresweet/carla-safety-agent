import assert from 'node:assert/strict';
import {readWithRetry,ReadHttpError} from './livery-designer/app/readWithRetry.ts';
const options=()=>({signal:new AbortController().signal,delayMs:0,timeoutMs:50});
let calls=0;const retries=[];
const value=await readWithRetry('http://local/read',{...options(),onRetry:n=>retries.push(n),fetcher:async(url,init)=>{assert.equal(init.method,'GET');calls++;if(calls===1)throw new TypeError('offline');if(calls===2)return new Response('',{status:503});return Response.json({frame:7})}});
assert.deepEqual(value,{frame:7});assert.equal(calls,3);assert.deepEqual(retries,[2,3]);
for(const status of [400,401,403,404,409,422]){calls=0;await assert.rejects(readWithRetry('x',{...options(),fetcher:async()=>{calls++;return new Response('',{status})}}),ReadHttpError);assert.equal(calls,1)}
calls=0;await assert.rejects(readWithRetry('x',{...options(),fetcher:async()=>{calls++;return new Response('broken-json')}}),SyntaxError);assert.equal(calls,1);
calls=0;await assert.rejects(readWithRetry('x',{...options(),fetcher:async()=>{calls++;throw new TypeError('offline')}}),TypeError);assert.equal(calls,3);
calls=0;await assert.rejects(readWithRetry('x',{...options(),timeoutMs:2,fetcher:async(_,init)=>{calls++;return new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(init.signal.reason),{once:true}))}}),{name:'TimeoutError'});assert.equal(calls,3);
const cancel=new AbortController();calls=0;
await assert.rejects(readWithRetry('x',{...options(),signal:cancel.signal,onRetry:()=>cancel.abort(),fetcher:async()=>{calls++;throw new TypeError('offline')}}),{name:'AbortError'});assert.equal(calls,1);
const old=new AbortController();calls=0;old.abort();await assert.rejects(readWithRetry('x',{...options(),signal:old.signal,fetcher:async()=>{calls++;return Response.json({})}}),{name:'AbortError'});assert.equal(calls,0);
for(const attempts of [0,4,Infinity,1.5])await assert.rejects(readWithRetry('x',{...options(),attempts}),/Invalid/);
console.log('PASS: bounded GET retry, HTTP classification, body errors, timeout, cancellation and no mutation replay');
