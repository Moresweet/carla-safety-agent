import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(specifier,context,next){
 if(context.parentURL?.endsWith('/restoreObjectRequest.ts')&&['./deletionResult','./snapshotObjects'].includes(specifier))return next(specifier+'.ts',context);
 return next(specifier,context);
}});
const {restoreObjectRequest}=await import('./livery-designer/app/restoreObjectRequest.ts');
const selection={scene_id:'s',version:'v',stable_id:'a'};
let count=0;
const send=async(url,options)=>{count++;assert.match(url,/restore-missing$/);assert.equal(options.method,'POST');assert.ok(options.signal);assert.deepEqual(JSON.parse(options.body),{...selection,confirmed:true});return new Response(JSON.stringify({ok:true,mode:'restore_missing_object',bindings:{a:123}}))};
assert.equal(await restoreObjectRequest(selection,true,send),123);assert.equal(count,1);
await assert.rejects(restoreObjectRequest(selection,false,send),/必须确认/);assert.equal(count,1);
for(const outcome of ['lost','malformed','wrong-object','rejected']){
 let attempts=0;
 await assert.rejects(restoreObjectRequest(selection,true,async()=>{
  attempts++;
  if(outcome==='lost')throw Error('Response lost after server applied operation');
  if(outcome==='malformed')return new Response('not JSON');
  if(outcome==='rejected')return new Response(JSON.stringify({ok:false,error:'already exists'}),{status:400});
  return new Response(JSON.stringify({ok:true,mode:'restore_missing_object',bindings:{b:123}}));
 }),/连接错误不证明操作未执行/);
 assert.equal(attempts,1,'Never automatically retry a mutation');
}
console.log('Restore request uncertainty and no-retry contracts passed');
