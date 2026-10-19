import assert from 'node:assert/strict';
import {parseQualityReport} from './livery-designer/app/qualityReport.ts';
const row={ok:true,run_id:'capture-a',state:'failed',detail:'No samples',reason_code:'no_samples',finished_at_unix:123};
assert.deepEqual(parseQualityReport(row,'capture-a',true),row);
assert.throws(()=>parseQualityReport(row,'capture-b',true));
assert.throws(()=>parseQualityReport(row,'capture-a',false));
for(const value of [null,[],{}, {...row,ok:false},{...row,state:'other'},{...row,detail:{}},{...row,error:[]},{...row,reason_code:3},{...row,finished_at_unix:Infinity},{...row,finished_at_unix:-1}])assert.throws(()=>parseQualityReport(value,'capture-a',true));
assert.doesNotThrow(()=>parseQualityReport({ok:true,run_id:'capture-a',state:'not_checked'},'capture-a',true));
console.log('Quality report parsing checks passed');
for(const problem_frame of [true,-1,1.5,'42',Infinity,NaN,Number.MAX_SAFE_INTEGER+1])
 assert.throws(()=>parseQualityReport({...row,problem_frame},'capture-a',true));
for(const problem_frame of [undefined,null,0,42,Number.MAX_SAFE_INTEGER])
 assert.doesNotThrow(()=>parseQualityReport({...row,problem_frame},'capture-a',true));
