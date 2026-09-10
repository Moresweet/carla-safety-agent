import assert from 'node:assert/strict';
import {textureUploadFlipY,sourceUVPixel,fittedProjectionFrame} from './livery-designer/app/uvConvention.ts';
import {previewBounds,previewCamera} from './livery-designer/app/previewCamera.ts';

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
const vertices=[10,-2,3,0,0,18,1,3,1,0,12,0,5,0,1];
const bounds=previewBounds(vertices);
for(const aspect of [.2,.5,1,2,5])for(const yaw of [-3,-.7,0,1,3])for(const pitch of [-1,0,.42,1]){
 const m=previewCamera(yaw,pitch,aspect,bounds.center,bounds.radius);
 for(let i=0;i<vertices.length;i+=5)for(let row=0;row<3;row++){
  const value=m[row]*vertices[i]+m[row+4]*vertices[i+1]+m[row+8]*vertices[i+2]+m[row+12];
  assert.ok(Math.abs(value)<=.90001,'Orbit must fit all geometry, including off-center meshes');
 }
}
assert.throws(()=>previewBounds([0,0,0,0,0]));
assert.throws(()=>previewCamera(0,0,0,[0,0,0],1));
console.log('PASS: preview camera fits geometry at all tested aspect ratios and orbit angles');
