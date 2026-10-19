import {objectRestoreSelection,type ObjectRestoreSelection} from './deletionResult';
export type DeletionEntry={operation_id:string;state:string;type_id:string;actor_id:number;backup:ObjectRestoreSelection};
export function parseDeletionHistory(raw:unknown){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('删除历史响应无效');
 const value=raw as Record<string,unknown>;
 if(value.ok!==true||!Array.isArray(value.entries)||value.entries.length>200||typeof value.complete!=='boolean'||typeof value.truncated!=='boolean')throw Error('删除历史响应无效');
 const ids=new Set<string>();
 const entries:DeletionEntry[]=value.entries.map((raw:unknown)=>{
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('删除历史记录无效');
  const row=raw as Record<string,unknown>,backup=objectRestoreSelection(row.backup);
  if(typeof row.operation_id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(row.operation_id)||ids.has(row.operation_id)||typeof row.state!=='string'||!['attempting','confirmed','needs_attention'].includes(row.state)||typeof row.type_id!=='string'||!row.type_id||typeof row.actor_id!=='number'||!Number.isSafeInteger(row.actor_id)||row.actor_id<=0||!backup)throw Error('删除历史记录无效');
  ids.add(row.operation_id);
  return {operation_id:row.operation_id,state:row.state,type_id:row.type_id,actor_id:row.actor_id,backup};
 });
 return {entries,complete:value.complete,truncated:value.truncated};
}
