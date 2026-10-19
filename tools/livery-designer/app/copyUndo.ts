export type CopyTarget={episode:string;actor_id:number;type_id:string;stable_id:string};
export type CopyReview={episode:string;actor_id:number;type_id:string;location:{x:number;y:number;z:number};yaw:number};
export function copyTarget(raw:unknown):CopyTarget{
 if(!raw||typeof raw!=='object')throw Error('副本身份缺失');
 const r=raw as CopyTarget;
 if(typeof r.episode!=='string'||!/^\d+$/.test(r.episode)||!Number.isSafeInteger(r.actor_id)||r.actor_id<=0||typeof r.type_id!=='string'||!r.type_id||typeof r.stable_id!=='string'||!r.stable_id)throw Error('副本身份无效');
 return {episode:r.episode,actor_id:r.actor_id,type_id:r.type_id,stable_id:r.stable_id};
}
export function parseCopyReview(raw:unknown,target:CopyTarget):CopyReview{
 if(!raw||typeof raw!=='object')throw Error('副本检查响应无效');
 const r=raw as {ok?:boolean;eligible?:boolean;identity?:unknown;observed?:CopyReview;reason?:string};
 if(r.ok!==true||r.eligible!==true)throw Error(r.reason||'副本不可撤销');
 const identity=copyTarget(r.identity);
 if(Object.keys(target).some(key=>target[key as keyof CopyTarget]!==identity[key as keyof CopyTarget]))throw Error('副本身份已变化，请重新选择');
 const o=r.observed;
 if(!o||o.episode!==target.episode||o.actor_id!==target.actor_id||o.type_id!==target.type_id||!o.location||![o.location.x,o.location.y,o.location.z,o.yaw].every(v=>typeof v==='number'&&Number.isFinite(v)))throw Error('副本当前位姿无效');
 return {episode:o.episode,actor_id:o.actor_id,type_id:o.type_id,location:{...o.location},yaw:o.yaw};
}
