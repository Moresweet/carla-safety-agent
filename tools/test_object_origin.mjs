import assert from 'node:assert/strict';
import {objectOriginLabel} from './livery-designer/app/objectOrigin.ts';
assert.equal(objectOriginLabel('user'),'用户新增');
assert.equal(objectOriginLabel('evaluation'),'评测生成');
assert.equal(objectOriginLabel('existing'),'场景原有');
for (const value of ['unknown',undefined,null,'', 'future-origin', {}, 1]) {
  assert.equal(objectOriginLabel(value),'来源未知');
}
console.log('PASS: unknown origins never claim historical provenance');
