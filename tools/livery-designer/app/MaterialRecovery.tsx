"use client";
import {useRef,useState} from 'react';
import type {MaterialInspection} from './materialInspection';
import {requestMaterialRecovery} from './materialRecoveryRequest';
export default function MaterialRecovery({operation,inspection,onPending,actor=false}:{operation:string;inspection:MaterialInspection;onPending:(pending:boolean)=>void;actor?:boolean}){
 const [choice,setChoice]=useState<''|'source'|'target'>(''),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[used,setUsed]=useState(false);
 const lock=useRef(false);
 async function recover(){
  if(lock.current||used||!choice||!confirmed||!inspection.recoverable||!inspection.token)return;
  lock.current=true;setBusy(true);setConfirmed(false);setUsed(true);onPending(true);
  try{
   await requestMaterialRecovery(operation,inspection,choice,fetch,30000,actor);
   setMessage('明确恢复写入已确认，原失败记录保留；请核对实景并重新检查。');
  }catch(e){setMessage(String(e)+'；结果未确认，请重新检查历史与实景，不要重复提交。')}
  finally{lock.current=false;setBusy(false);onPending(false)}
 }
 return <div><p>失败恢复会重新写入所选纹理，不是把旧操作标记成功。</p>
  <label>恢复目标<select value={choice} disabled={busy||used} onChange={e=>{setChoice(e.target.value as ''|'source'|'target');setConfirmed(false)}}><option value="">请选择恢复目标</option><option value="source">操作起点</option><option value="target">操作目标</option></select></label>
  {choice&&<p>将设置：{inspection[choice]??'原材质（移除工作台覆盖）'}</p>}
  <label><input type="checkbox" disabled={busy||used||!choice} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>确认重新写入所选材质，保留原失败记录</label>
  <button disabled={busy||used||!choice||!confirmed} onClick={()=>void recover()}>执行明确恢复</button><p role="status">{message}</p>
 </div>
}
