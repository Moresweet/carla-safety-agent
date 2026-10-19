"use client";
import {useRef,useState} from 'react';
import {copyTarget,type CopyTarget} from './copyUndo';
import type {ObjectRestoreSelection} from './deletionResult';
export default function CopyRedo({operation,deletion,target,backup,onDone}:{operation:string;deletion:string;target:CopyTarget;backup:ObjectRestoreSelection;onDone:()=>void}){
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[uncertain,setUncertain]=useState(false);
 const lock=useRef(false);
 async function redo(){
  if(lock.current||!confirmed||uncertain)return;
  lock.current=true;setBusy(true);setConfirmed(false);setError('');
  try{
   const response=await fetch('http://127.0.0.1:8765/objects/copy-redo',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(30000),body:JSON.stringify({operation_id:operation,deletion_id:deletion,confirmed:true})});
   const raw=await response.json();
   if(!raw||typeof raw!=='object')throw Error('重做响应无效');
   const value=raw as {ok?:boolean;error?:string;copy_operation_id?:string;target?:unknown};
   if(!response.ok||value.ok!==true)throw Error(value.error||'重做未确认');
   const restored=copyTarget(value.target);
   if(value.copy_operation_id!==operation||restored.stable_id!==target.stable_id||restored.episode!==target.episode||restored.type_id!==target.type_id||restored.actor_id===target.actor_id)throw Error('重做返回对象身份不匹配');
   onDone();
  }catch(e){setUncertain(true);setError(String(e)+'；请刷新历史并检查场景，勿直接重复提交。')}
  finally{lock.current=false;setBusy(false)}
 }
 return <div><p>重做副本：{target.type_id} · 稳定 ID {target.stable_id}。从场景 {backup.scene_id} 的版本 {backup.version} 恢复撤销前状态，不重新复制源对象。对象已存在或世界已变化时拒绝。</p>
  <label><input type="checkbox" checked={confirmed} disabled={busy||uncertain} onChange={e=>setConfirmed(e.target.checked)}/>确认从上述备份重做副本</label>
  <button disabled={busy||uncertain||!confirmed} onClick={()=>void redo()}>{busy?'重做中…':'确认重做复制'}</button>
  {error&&<p role="alert">{error}</p>}
 </div>
}
