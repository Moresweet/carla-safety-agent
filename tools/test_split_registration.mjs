import assert from 'node:assert/strict';
import {parseSplitRegistration,splitFileError} from './livery-designer/app/splitRegistration.ts';
for(const size of [0,-1,NaN,Infinity,1.5,8*1024**2+1])assert.ok(splitFileError(size));
for(const size of [1,8*1024**2])assert.equal(splitFileError(size),'');
const valid={ok:true,created:true,sha256:'a'.repeat(64),run_count:3,verification:'finalized_manifest_and_temporal_index',raw_sensor_files_verified:false};
assert.equal(parseSplitRegistration(valid,200).created,true);
assert.equal(parseSplitRegistration({...valid,created:false},200).created,false);
for(const status of [400,409,413,500])assert.throws(()=>parseSplitRegistration(valid,status));
for(const raw of [null,[],{}, {...valid,ok:'true'}, {...valid,sha256:'bad'}, {...valid,created:1},
 {...valid,run_count:0},{...valid,run_count:1.5},{...valid,run_count:Infinity},
 {...valid,run_count:Number.MAX_SAFE_INTEGER+1},{...valid,verification:'raw_data_verified'},
 {...valid,raw_sensor_files_verified:true},{...valid,raw_sensor_files_verified:undefined}])
 assert.throws(()=>parseSplitRegistration(raw,200));
assert.throws(()=>parseSplitRegistration({ok:false,error:'busy'},409),/busy/);
console.log('Split registration response contracts passed');
