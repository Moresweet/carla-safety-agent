export type MaterialSlot = {slot:number;name:string;status:string;mesh_file?:string;original_material:string|null};
export function slotSupported(slot:MaterialSlot):boolean {
 return slot.status==='uv0_ready' && typeof slot.mesh_file==='string' && slot.mesh_file.length>0;
}
export function slotSupportLabel(slot:MaterialSlot):string {
 if(slotSupported(slot))return '可编辑 · 已导出真实 UV0 网格';
 if(slot.status==='uv0_ready')return '缺少网格文件，暂不能编辑';
 if(slot.status==='no_exported_uv_triangles')return '未导出有效 UV 三角面，需重新导出资产';
 return `尚未就绪（${slot.status || '未导出'}），需先导出真实网格与 UV`;
}
