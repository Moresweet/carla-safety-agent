import assert from 'node:assert/strict';
import {deletionResultText,objectRestoreSelection} from './livery-designer/app/deletionResult.ts';
assert.deepEqual(objectRestoreSelection({scene_id:'s',version:'v',stable_id:'object-one',extra:1}),{scene_id:'s',version:'v',stable_id:'object-one'});
for(const raw of [null,[],{}, {scene_id:'s',version:'v'}, {scene_id:'s',version:'v',stable_id:'../wrong'}])assert.equal(objectRestoreSelection(raw),null);
assert.match(deletionResultText({scene_id:'scene-one',version:'version-one'}),/scene-one.*version-one.*不是单对象撤销/);
for(const raw of [null,undefined,[],false])assert.match(deletionResultText(raw),/不能承诺撤销/);
for(const raw of [{},{scene_id:'../other',version:'v'},{scene_id:'s',version:1}])assert.match(deletionResultText(raw),/格式异常/);
console.log('Deletion backup feedback contracts passed');
