import assert from 'node:assert/strict';
import {textureRoute} from './livery-designer/app/textureTarget.ts';

assert.equal(textureRoute({id:42,kind:'vehicle',name:'vehicle.a'}).path,'apply?actor_id=42');
assert.equal(textureRoute({id:'43',kind:'walker',name:'walker.pedestrian.0001'}).path,'apply/pedestrian?actor_id=43');
assert.equal(textureRoute({kind:'road',name:'Road_Road_Town04_320'}).path,'apply/road?scope=Road_Road_Town04_320');
for(const target of [null,{kind:'road',name:'Town04 roads'},{id:42,kind:'prop',name:'static.prop.mesh'},
 {id:42,kind:'walker',name:'walker.pedestrian.0002'},{kind:'vehicle',name:'vehicle.a'},
 {id:42,kind:'building',name:'BP_House16'},{source:'environment',kind:'road',name:'Road_Road_1'}]){
 assert.ok(textureRoute(target).error,JSON.stringify(target));
 assert.equal(textureRoute(target).path,undefined);
}
console.log('PASS: exact texture routing and unsupported-target rejection');
