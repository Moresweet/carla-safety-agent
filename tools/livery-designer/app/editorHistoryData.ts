import {copyTarget,type CopyTarget} from './copyUndo';
import {objectRestoreSelection,type ObjectRestoreSelection} from './deletionResult';
type Entry={kind:string;state:string;operation_id:string;created_at:number|null;actor_id:number|string;type_id:string;stable_id:string;target?:CopyTarget;recovery?:ObjectRestoreSelection;deletion_id?:string;actorMaterial?:{component:string;slot:number;before:string|null;after:string|null;revision:string;transitionSupported:boolean};material?:{component:string;slot:number;before:string|null;after:string|null;revision:string}};
export type EditorHistoryData={entries:Entry[];total:number;complete:boolean;truncated:boolean;warnings:{source:string;error:string}[]};
function object(value:unknown):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))throw Error('编辑历史结构无效');return value as Record<string,unknown>}
function text(value:unknown):string{if(typeof value!=='string'||!value)throw Error('编辑历史标识缺失');return value}
export function parseEditorHistory(raw:unknown):EditorHistoryData{
 const value=object(raw);
 const capabilities=value.capabilities===undefined?{}:object(value.capabilities);
 if(capabilities.actor_material_transition!==undefined&&typeof capabilities.actor_material_transition!=='boolean')throw Error('编辑历史能力声明无效');
 if(value.ok!==true||!Array.isArray(value.entries)||value.entries.length>200||typeof value.complete!=='boolean'||typeof value.truncated!=='boolean'||!Number.isSafeInteger(value.total)||Number(value.total)<value.entries.length||!Array.isArray(value.warnings))throw Error('编辑历史响应无效');
 const ids=new Set<string>();
 const entries=value.entries.map(raw=>{
  const row=object(raw),kind=text(row.kind),operation_id=text(row.operation_id);let state=text(row.state);
  const allowed:Record<string,string[]>={transform:['applied','undone'],'transform-intent':['attempting','needs_attention'],delete:['attempting','confirmed','needs_attention'],copy:['attempting','confirmed','needs_attention'],material:['attempting','confirmed','needs_attention'],'actor-material':['attempting','confirmed','needs_attention']};
  if(!allowed[kind]?.includes(state)||ids.has(kind+':'+operation_id))throw Error('编辑历史状态无效');ids.add(kind+':'+operation_id);
  let recovery:ObjectRestoreSelection|undefined;
  let deletion_id:string|undefined;
  if(kind==='copy'&&row.undo!==undefined){
   const undo=object(row.undo);
   if(state!=='confirmed'||!['attempting','confirmed','needs_attention'].includes(text(undo.state)))throw Error('复制撤销状态无效');
   state=undo.state==='confirmed'?'undone':undo.state==='attempting'?'undo_attempting':'undo_needs_attention';
   if(undo.state==='confirmed'){
    const deletion=object(undo.deletion),target=copyTarget(row.target);
    const selection=objectRestoreSelection(deletion.backup);
    if(deletion.ok!==true||deletion.actor_id!==target.actor_id||!selection||selection.stable_id!==target.stable_id)throw Error('复制撤销恢复备份身份不匹配');
    recovery=selection;
    deletion_id=text(deletion.operation_id);
   }
  }
  if(kind==='copy'&&row.redo!==undefined){
   const redo=object(row.redo);
   if(state!=='undone'||!['attempting','needs_attention'].includes(text(redo.state)))throw Error('复制重做状态无效');
   state=redo.state==='attempting'?'redo_attempting':'redo_needs_attention';recovery=undefined;deletion_id=undefined;
  }
  if(row.created_at===null?kind!=='transform-intent':typeof row.created_at!=='number'||!Number.isFinite(row.created_at)||row.created_at<0)throw Error('编辑历史时间无效');
  if(kind==='actor-material'){
   if(row.pending!==undefined&&row.pending!==null){
    const pending=object(row.pending);
    if(!['attempting','needs_attention'].includes(text(pending.state)))throw Error('车辆行人材质待检查状态无效');
    state=text(pending.state);
   }else if(row.applied===false)state='undone';
   else if(row.applied!==undefined&&row.applied!==true)throw Error('车辆行人材质应用状态无效');
   const identity=object(row.identity),model=text(identity.blueprint_id),component=text(identity.component);
   const layouts:Record<string,[string,number]>={'vehicle.audi.a2':['VehicleMesh',4],'walker.pedestrian.0001':['CharacterMesh0',14]};
   if(row.undo_supported!==false||!layouts[model]||component!==layouts[model][0]||identity.slot!==layouts[model][1]||!Number.isSafeInteger(identity.actor_id)||Number(identity.actor_id)<=0||Number(identity.actor_id)>=2**32||!/^\d+$/.test(text(identity.episode)))throw Error('车辆行人材质身份无效');
   for(const digest of [row.before,row.after])if(digest!==null&&(typeof digest!=='string'||!/^[a-f0-9]{64}$/.test(digest)))throw Error('材质历史纹理引用无效');
   return {kind,state,operation_id,created_at:row.created_at as number,actor_id:Number(identity.actor_id),type_id:model,stable_id:text(identity.stable_id),actorMaterial:{component,slot:Number(identity.slot),before:row.before as string|null,after:row.after as string|null,revision:row.revision===undefined?operation_id:text(row.revision),transitionSupported:capabilities.actor_material_transition===true}};
  }
  if(kind==='material'){
   if(row.pending!==undefined&&row.pending!==null){
    const pending=object(row.pending);
    if(!['attempting','needs_attention'].includes(text(pending.state)))throw Error('材质历史待检查状态无效');
    state=text(pending.state);
   }else if(row.applied===false)state='undone';
   else if(row.applied!==undefined&&row.applied!==true)throw Error('材质历史应用状态无效');
   const identity=object(row.identity),actor_id=text(identity.object_id),component=text(identity.component);
   if(!/^\d+$/.test(actor_id)||!Number.isSafeInteger(identity.slot)||Number(identity.slot)<0||component.includes('|'))throw Error('环境材质身份无效');
   for(const digest of [row.before,row.after])if(digest!==null&&(typeof digest!=='string'||!/^[a-f0-9]{64}$/.test(digest)))throw Error('材质历史纹理引用无效');
   return {kind,state,operation_id,created_at:row.created_at as number,actor_id,type_id:text(identity.target),stable_id:text(identity.episode),material:{component,slot:Number(identity.slot),before:row.before as string|null,after:row.after as string|null,revision:row.revision===undefined?operation_id:text(row.revision)}};
  }
  const identity=kind==='delete'?row:object(row.identity),stable=kind==='delete'?object(row.backup).stable_id:identity.stable_id;
  if(!Number.isSafeInteger(identity.actor_id)||Number(identity.actor_id)<=0)throw Error('编辑历史对象无效');
  return {kind,state,operation_id,created_at:row.created_at as number|null,actor_id:Number(identity.actor_id),type_id:text(identity.type_id),stable_id:kind==='copy'&&stable===null?'源对象未纳管':text(stable),...(kind==='copy'&&row.target?{target:copyTarget(row.target)}:{}),...(recovery?{recovery,deletion_id}:{})};
 });
 const warnings=value.warnings.map(raw=>{const warning=object(raw);return {source:text(warning.source),error:text(warning.error)}});
 if(value.complete!==(warnings.length===0)||value.truncated!==(Number(value.total)>entries.length))throw Error('编辑历史完整性标记不一致');
 return {entries,total:Number(value.total),complete:value.complete,truncated:value.truncated,warnings};
}
