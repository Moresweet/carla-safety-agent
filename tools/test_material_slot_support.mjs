import assert from 'node:assert/strict';
import {slotSupported,slotSupportLabel} from './livery-designer/app/materialSlotSupport.ts';
const slot={slot:0,name:'wall',status:'uv0_ready',mesh_file:'wall.json',original_material:null};
assert.equal(slotSupported(slot),true);
for(const patch of [{mesh_file:undefined},{mesh_file:''},{status:'no_exported_uv_triangles'},{status:'fbx_exported'}])assert.equal(slotSupported({...slot,...patch}),false);
assert.match(slotSupportLabel({...slot,mesh_file:undefined}),/缺少网格/);
assert.match(slotSupportLabel({...slot,status:'no_exported_uv_triangles'}),/UV 三角面/);
assert.match(slotSupportLabel({...slot,status:'unknown'}),/unknown/);
console.log('Material slot support labels passed');
