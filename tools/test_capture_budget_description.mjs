import assert from 'node:assert/strict';
import {captureBudgetDescription} from './livery-designer/app/captureBudgetDescription.ts';
assert.match(captureBudgetDescription(30,5),/约 120 个/);
assert.doesNotMatch(captureBudgetDescription(100,1),/后段/);
assert.match(captureBudgetDescription(101,1),/后段不保证保存/);
assert.match(captureBudgetDescription(5000,100),/约 1000 个/);
for(const [seconds,every] of [[0,1],[5001,1],[1,0],[1,101],[NaN,1],[1,1.5]])
 assert.match(captureBudgetDescription(seconds,every),/无效/);
console.log('Capture budget: duration, sampling interval, frame cap and invalid inputs passed');
