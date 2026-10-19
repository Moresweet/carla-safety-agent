import assert from 'node:assert/strict';
import {parseRecoveryJob,candidateLocation,recoverySubmissionId} from './livery-designer/app/captureRecoveryJob.ts';
const id='a'.repeat(32),source='capture-source',run='recovered-'+'b'.repeat(32);
const base={ok:true,request_id:id,source_run_id:source,state:'running'};
let created=0;const create=()=>{created++;return 'c'.repeat(32)};
assert.equal(recoverySubmissionId({request_id:id,state:'checking'},id,create),id);
assert.equal(created,0);
for(const attempt of [null,'d'.repeat(32)])assert.throws(()=>recoverySubmissionId({request_id:id,state:'checking'},attempt,create));
for(const state of ['running','needs_attention','recovered','unknown'])assert.throws(()=>recoverySubmissionId({request_id:id,state},id,create));
assert.equal(created,0);
assert.equal(recoverySubmissionId(null,id,create),id);
assert.equal(recoverySubmissionId({request_id:id,state:'failed'},id,create),'c'.repeat(32));
assert.equal(created,1);
for(const state of ['running','failed','needs_attention'])assert.equal(parseRecoveryJob({...base,state},id,source).state,state);
assert.equal(parseRecoveryJob({...base,state:'recovered',recovered_run_id:run,candidate_run_id:run},id,source).recovered_run_id,run);
for(const patch of [{ok:false},{request_id:'other'},{source_run_id:'other'},{state:'unknown'},{state:'recovered'},{error:{}},{phase:[]},{staging_directory:2},{candidate_run_id:'../path'},{recovered_run_id:run},{state:'recovered',recovered_run_id:run,candidate_run_id:'recovered-'+'c'.repeat(32)}])assert.throws(()=>parseRecoveryJob({...base,...patch},id,source));
for(const value of [null,[],false,'bad'])assert.throws(()=>parseRecoveryJob(value,id,source));
console.log('Recovery jobs: request/source identity, state, published/candidate consistency and safe display fields passed');
const labels=new Set();
for(const staged of [false,true])for(const published of [false,true]){
 const presence={staged,published,raw_data_verified:false};
 const job=parseRecoveryJob({...base,state:'needs_attention',candidate_run_id:run,candidate_presence:presence},id,source);
 assert.equal(job.state,'needs_attention');assert.deepEqual(job.candidate_presence,presence);
 labels.add(candidateLocation(presence));
}
assert.equal(labels.size,4);
for(const presence of [null,[],{}, {staged:'false',published:false,raw_data_verified:false},{staged:true,published:false,raw_data_verified:true}])assert.throws(()=>parseRecoveryJob({...base,candidate_run_id:run,candidate_presence:presence},id,source));
assert.throws(()=>parseRecoveryJob({...base,candidate_presence:{staged:true,published:false,raw_data_verified:false}},id,source));
