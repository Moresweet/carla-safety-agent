import assert from 'node:assert/strict';
import {searchDatasets,datasetModelLabel} from './livery-designer/app/datasetSearch.ts';
const rows=[{run_id:'capture-a',scenario_id:'VAD route',status:'saved',map:'Town04'},
 {run_id:'capture-b',scenario_id:'TCP route',status:'saved_capture_error',map:'Town03'}];
assert.equal(searchDatasets(rows,' vad TOWN04 ','').matches.length,1);
assert.equal(searchDatasets(rows,'saved_capture_error','').matches[0].run_id,'capture-b');
const result=searchDatasets(rows,'missing','capture-a');
assert.equal(result.matches.length,0);assert.equal(result.retained,true);
assert.deepEqual(result.options,[rows[0]]);
assert.equal(searchDatasets(rows,'','capture-a').options.length,2);
assert.equal(searchDatasets(rows,'missing','deleted').options.length,0);
assert.equal(rows.length,2);
console.log('Dataset search preserves selected replay and filters conjunctive terms');
const sameScenario=[{run_id:'a',scenario_id:'same',model:'vad',map:'Town04'},
 {run_id:'b',scenario_id:'same',model:'driveadapter-experimental',map:'Town04'}];
assert.equal(searchDatasets(sameScenario,'driveadapter Town04','').matches[0].run_id,'b');
assert.equal(datasetModelLabel({run_id:'a',model:null,family:'sensor-rig'}),'独立采集（无模型）');
assert.equal(datasetModelLabel({run_id:'a',model:null}),'模型未记录');
assert.equal(datasetModelLabel({run_id:'a',model:{}}),'模型未记录');
