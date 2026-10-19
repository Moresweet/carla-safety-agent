import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(specifier,context,next){
 if(context.parentURL?.endsWith('/deletionHistoryData.ts')&&specifier==='./deletionResult')return next(specifier+'.ts',context);
 return next(specifier,context);
}});
const {parseDeletionHistory}=await import('./livery-designer/app/deletionHistoryData.ts');
const entry={operation_id:'op',state:'attempting',type_id:'prop',actor_id:1,backup:{scene_id:'s',version:'v',stable_id:'a'}};
const payload={ok:true,entries:[entry],complete:true,truncated:false};
assert.equal(parseDeletionHistory(payload).entries[0].state,'attempting');
assert.equal(parseDeletionHistory({...payload,complete:false}).complete,false);
for(const value of [null,[],{}, {...payload,entries:[entry,entry]}, {...payload,entries:[{...entry,actor_id:-1}]}, {...payload,entries:[{...entry,state:'restored'}]}, {...payload,entries:[{...entry,backup:{...entry.backup,version:'../bad'}}]}])assert.throws(()=>parseDeletionHistory(value));
console.log('Deletion history parser contracts passed');
