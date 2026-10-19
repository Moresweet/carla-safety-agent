export type SnapshotObject={stable_id:string;blueprint_id:string};
export function restoredObjectId(value:unknown,stableId:string):number{
 const result=value as {ok?:unknown;mode?:unknown;bindings?:Record<string,unknown>}|null;
 const actor=result?.bindings?.[stableId];
 if(result?.ok!==true||result.mode!=='restore_missing_object'||typeof actor!=='number'||!Number.isSafeInteger(actor)||actor<=0)
  throw Error('恢复响应未确认所选对象的运行时身份');
 return actor;
}
export function snapshotObjects(value:unknown):SnapshotObject[]{
 const rows=(value as {document?:{objects?:unknown}}|null)?.document?.objects;
 if(!Array.isArray(rows)||rows.length>2000)throw Error('快照对象清单格式异常');
 const seen=new Set<string>();
 return rows.map(row=>{
  if(!row||typeof row!=='object'||typeof row.stable_id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(row.stable_id)||typeof row.blueprint_id!=='string'||!row.blueprint_id||seen.has(row.stable_id))throw Error('快照对象身份异常');
  seen.add(row.stable_id);return {stable_id:row.stable_id,blueprint_id:row.blueprint_id};
 });
}
