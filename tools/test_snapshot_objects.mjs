import assert from 'node:assert/strict';
import {snapshotObjects,restoredObjectId} from './livery-designer/app/snapshotObjects.ts';
assert.equal(restoredObjectId({ok:true,mode:'restore_missing_object',bindings:{one:128}},'one'),128);
for(const raw of [null,{ok:true},{ok:true,mode:'merge',bindings:{one:128}},{ok:true,mode:'restore_missing_object',bindings:{other:128}},{ok:true,mode:'restore_missing_object',bindings:{one:0}},{ok:true,mode:'restore_missing_object',bindings:{one:'128'}}])assert.throws(()=>restoredObjectId(raw,'one'));
const object={stable_id:'one',blueprint_id:'static.prop.advertisement'};
assert.deepEqual(snapshotObjects({document:{objects:[object]}}),[object]);
assert.deepEqual(snapshotObjects({document:{objects:[]}}),[]);
for(const value of [null,{}, {document:{objects:[object,object]}},{document:{objects:[{...object,stable_id:'../bad'}]}},{document:{objects:Array(2001).fill(object)}}])assert.throws(()=>snapshotObjects(value));
console.log('Snapshot object selection contracts passed');
