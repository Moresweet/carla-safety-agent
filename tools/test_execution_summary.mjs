import assert from 'node:assert/strict';
import {executionSummaryText} from './livery-designer/app/executionSummary.ts';
const valid={available:true,state:'failed',execution_id:'execution-one',error:'RPC timeout'};
assert.match(executionSummaryText(valid),/失败.*RPC timeout/);
assert.match(executionSummaryText({...valid,state:'completed',error:null}),/已完成.*不是驾驶质量评分/);
assert.match(executionSummaryText({...valid,state:'running'}),/不是当前进程存活证明/);
for(const raw of [null,[],{}, {...valid,available:false},{...valid,state:'passed'},
 {...valid,state:'toString'},{...valid,execution_id:'../other'},{...valid,error:{}}])
 assert.match(executionSummaryText(raw),/不可用/);
console.log('Execution summary display contracts passed');
