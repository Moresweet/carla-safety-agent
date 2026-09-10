type Target={id?:number|string;source?:string;kind:string;name:string};
type Route={path:string;scope:string;error?:never}|{error:string;path?:never;scope?:never};

export function textureRoute(target:Target|null|undefined):Route{
 if(!target)return {error:'请先选择一个具体对象。'};
 if(target.source==='environment')return {error:'环境对象请使用组件 / 材质槽编辑器。'};
 if(target.kind==='vehicle'||target.kind==='walker'){
  const id=Number(target.id);
  if(!Number.isSafeInteger(id)||id<=0)return {error:'所选对象缺少有效 Actor ID，请重新选择。'};
  if(target.kind==='walker'&&target.name!=='walker.pedestrian.0001')return {error:'此行人尚无已验证的衣物槽；不会改用其他行人。'};
  return {path:`${target.kind==='vehicle'?'apply':'apply/pedestrian'}?actor_id=${id}`,scope:`仅 Actor ${id}${target.kind==='walker'?' · 裤装材质槽 14':''}`};
 }
 if(target.kind==='road'&&target.name.startsWith('Road_Road_'))return {path:`apply/road?scope=${encodeURIComponent(target.name)}`,scope:`仅 ${target.name}`};
 if(target.kind==='building'&&target.id===undefined&&/^BP_House16(?:_.*)?$/.test(target.name))return {path:`apply/building?target=${encodeURIComponent(target.name)}`,scope:`仅 ${target.name} 的已验证墙面`};
 if(target.kind==='road')return {error:'此条目是道路集合，不是单一道路。请在 World Objects 中选择具体道路及材质槽。'};
 return {error:'此对象尚无可验证的直接贴图入口；不会转而修改建筑或其他对象。请使用资产工坊处理其源资产。'};
}
