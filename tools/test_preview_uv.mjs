import assert from 'node:assert/strict';
import {textureUploadFlipY,sourceUVPixel,fittedProjectionFrame} from './livery-designer/app/uvConvention.ts';

assert.equal(textureUploadFlipY(true),false);
assert.equal(textureUploadFlipY(false),true,'Legacy Tesla path remains unchanged');
assert.deepEqual(sourceUVPixel(.2,.1,100,200),[20,20]);
assert.deepEqual(sourceUVPixel(.2,.9,100,200),[20,180]);
assert.deepEqual(sourceUVPixel(2,-1,100,200),[200,-200],'Repeating UVs are not clamped');
for(const aspect of [.2,.5,1,2,5]){
 const frame=fittedProjectionFrame(aspect,1024);
 assert.ok(frame.x>=0&&frame.y>=0&&frame.x+frame.w<=1024&&frame.y+frame.h<=1024);
 assert.ok(Math.abs(frame.w/frame.h-aspect)<1e-9);
}
console.log('PASS: top-left source UV convention and portrait/landscape projection fitting');
