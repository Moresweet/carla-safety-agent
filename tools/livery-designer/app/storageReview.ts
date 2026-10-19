export type Review={complete:boolean;allocated_bytes:number;free_bytes:number;warnings:string[];recordings:{directory:string;status:string|null;allocated_bytes:number;keep_reason:string|null;derived_referenced_by:unknown[];queue_referenced_by:unknown[];project_referenced_by:unknown[];split_referenced_by:unknown[]}[]};
export function filterStorageRows(rows:Review['recordings'],query:string,status:string,keptOnly:boolean):Review['recordings'] {
 const text=query.trim().toLowerCase();
 return rows.filter(row=>(!text||row.directory.toLowerCase().includes(text))&&(!status||(row.status??'unknown')===status)&&(!keptOnly||row.keep_reason!==null));
}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const bytes=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function parseStorageReview(value:unknown):Review {
 const invalid=()=>{throw Error('盘点响应格式异常，请重新读取；未据此判断数据可删除');};
 if(!object(value))return invalid();
 if(value.ok!==true)throw Error(typeof value.error==='string'?value.error:'盘点失败');
 if(value.schema_version!=='capture-storage-inventory/1'||typeof value.complete!=='boolean'||!bytes(value.allocated_bytes)||!bytes(value.free_bytes)||!Array.isArray(value.warnings)||!value.warnings.every(w=>typeof w==='string')||!Array.isArray(value.recordings))return invalid();
 const seen=new Set<string>();
 for(const row of value.recordings){
  if(!object(row)||typeof row.directory!=='string'||!row.directory||seen.has(row.directory)||!(row.status===null||typeof row.status==='string')||!bytes(row.allocated_bytes)||!(row.keep_reason===null||typeof row.keep_reason==='string')||!Array.isArray(row.derived_referenced_by)||!Array.isArray(row.queue_referenced_by))return invalid();
  seen.add(row.directory);
  if(!Array.isArray(row.project_referenced_by))return invalid();
  if(!Array.isArray(row.split_referenced_by))return invalid();
 }
 return value as unknown as Review;
}
