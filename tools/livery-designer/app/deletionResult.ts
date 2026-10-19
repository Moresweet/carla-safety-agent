export type ObjectRestoreSelection={scene_id:string;version:string;stable_id:string};
export function objectRestoreSelection(raw:unknown):ObjectRestoreSelection|null{
 if(!raw||typeof raw!=='object'||Array.isArray(raw))return null;
 const value=raw as Record<string,unknown>;
 if(!['scene_id','version','stable_id'].every(k=>typeof value[k]==='string'&&/^[A-Za-z0-9_-]{1,80}$/.test(value[k] as string)))return null;
 return {scene_id:value.scene_id as string,version:value.version as string,stable_id:value.stable_id as string};
}
export function deletionResultText(backup:unknown):string{
 if(!backup||typeof backup!=='object'||Array.isArray(backup))
  return '对象删除已确认；没有确认可用的删除前备份，不能承诺撤销。';
 const value=backup as Record<string,unknown>;
 if(typeof value.scene_id!=='string'||typeof value.version!=='string'||
    !/^[A-Za-z0-9_-]{1,80}$/.test(value.scene_id)||!/^[A-Za-z0-9_-]{1,80}$/.test(value.version))
  return '对象删除已确认，但备份标识格式异常；请在项目与场景版本中核对，勿自动重试删除。';
 return `对象删除已确认。删除前快照：场景 ${value.scene_id}，版本 ${value.version}。可在“项目与场景版本”中核对恢复；这是纳管场景级快照，不是单对象撤销，恢复前请检查对其他对象和材质的影响。`;
}
