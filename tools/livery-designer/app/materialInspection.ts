export type RecoveryReceipt={state:'attempting'|'confirmed'|'needs_attention';choice:'source'|'target';desired:string|null};
export function materialInspectionFailure(status:number,raw:unknown):string{
 const value=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw as Record<string,unknown>:null;
 const detail=value?.ok===false&&typeof value.error==='string'?value.error.trim().slice(0,500):'';
 return '材质检查失败：HTTP '+status+(detail?' · '+detail:'');
}
export type MaterialInspection={registered:string|null;source:string|null;target:string|null;matches:'source'|'target'|'both'|'neither';token:string|null;recoverable:boolean;recovery:RecoveryReceipt|null};
function digest(value:unknown):string|null{
 if(value===null)return null;
 if(typeof value!=='string'||!/^[a-f0-9]{64}$/.test(value))throw Error('材质检查纹理引用无效');
 return value;
}
export function parseMaterialInspection(raw:unknown,operation:string,actor=false):MaterialInspection{
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('材质检查响应无效');
 const value=raw as Record<string,unknown>;
 if(value.ok!==true||value.operation_id!==operation||value.native_verified!==false||value.automatic_retry_allowed!==false)throw Error('材质检查身份或验证范围无效');
 if(actor){
  const identity=value.identity as Record<string,unknown>|undefined;
  const layouts:Record<string,[string,number]>={'vehicle.audi.a2':['VehicleMesh',4],'walker.pedestrian.0001':['CharacterMesh0',14]};
  const layout=identity&&typeof identity.blueprint_id==='string'?layouts[identity.blueprint_id]:undefined;
  if(!identity||!layout||identity.component!==layout[0]||identity.slot!==layout[1]||typeof identity.stable_id!=='string'||!identity.stable_id||typeof identity.episode!=='string'||!/^\d+$/.test(identity.episode)||!Number.isSafeInteger(identity.actor_id)||Number(identity.actor_id)<=0||Number(identity.actor_id)>=2**32)throw Error('车辆行人检查身份无效');
  if(value.actor_recovery_supported!==undefined&&typeof value.actor_recovery_supported!=='boolean')throw Error('车辆行人恢复能力无效');
 }
 const registered=digest(value.registered_texture),source=digest(value.source),target=digest(value.target);
 const matches=registered===source&&registered===target?'both':registered===target?'target':registered===source?'source':'neither';
 if(value.registry_matches!==matches)throw Error('材质检查比较结果不一致');
 const token=value.inspection_token===undefined?null:value.inspection_token;
 if(token!==null&&(typeof token!=='string'||!/^[a-f0-9]{64}$/.test(token)))throw Error('材质检查凭据无效');
 const state=value.state;
 let recovery:RecoveryReceipt|null=null;
 if(value.recovery!==undefined&&value.recovery!==null){
  if(typeof value.recovery!=='object'||Array.isArray(value.recovery))throw Error('材质恢复回执无效');
  const receipt=value.recovery as Record<string,unknown>;
  if(!['attempting','confirmed','needs_attention'].includes(String(receipt.state))||!['source','target'].includes(String(receipt.choice)))throw Error('材质恢复回执状态无效');
  recovery={state:receipt.state as RecoveryReceipt['state'],choice:receipt.choice as RecoveryReceipt['choice'],desired:digest(receipt.desired)};
  if(recovery.desired!==(recovery.choice==='source'?source:target))throw Error('材质恢复回执目标不一致');
 }
 const pending=value.pending as {state?:unknown}|null|undefined;
 if(pending!==undefined&&pending!==null&&(typeof pending!=='object'||!['attempting','needs_attention'].includes(String(pending.state))))throw Error('材质待检查记录无效');
 const recoverable=(!actor||value.actor_recovery_supported===true)&&token!==null&&value.recovery===null&&(state==='attempting'||state==='needs_attention'||state==='confirmed'&&pending!=null);
 return {registered,source,target,matches,token:token as string|null,recoverable,recovery};
}
