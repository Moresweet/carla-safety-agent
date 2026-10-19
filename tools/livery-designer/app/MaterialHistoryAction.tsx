"use client";
import {useRef,useState} from 'react';
export default function MaterialHistoryAction({operation,revision,direction,texture,onDone,actor=false}:{operation:string;revision:string;direction:'undo'|'redo';texture:string|null;onDone:()=>void;actor?:boolean}){
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[uncertain,setUncertain]=useState(false);
 const lock=useRef(false),label=direction==='undo'?'撤销':'重做';
 async function execute(){
  if(lock.current||!confirmed||uncertain)return;
  lock.current=true;setBusy(true);setConfirmed(false);setError('');
  try{
   const response=await fetch('http://127.0.0.1:8765/materials/'+(actor?'actor-history':'history'),{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(30000),body:JSON.stringify({operation_id:operation,revision,direction,confirmed:true})});
   const raw=await response.json();
   if(!raw||typeof raw!=='object')throw Error('材质历史响应无效');
   const value=raw as {ok?:boolean;error?:string;operation_id?:string;revision?:string;applied?:boolean};
   if(!response.ok||value.ok!==true)throw Error(value.error||'材质操作未确认');
   if(value.operation_id!==operation||typeof value.revision!=='string'||!value.revision||value.revision===revision||value.applied!==(direction==='redo'))throw Error('材质历史响应与请求不匹配');
   onDone();
  }catch(e){setUncertain(true);setError(String(e)+'；请刷新历史并检查实景，勿直接重复提交。')}
  finally{lock.current=false;setBusy(false)}
 }
 return <div><p>{label}将设置为：{texture??'原材质（移除工作台覆盖）'}。仅作用于本条记录的组件与槽；后台会拒绝当前登记纹理不匹配的操作。</p>
  <label><input type="checkbox" checked={confirmed} disabled={busy||uncertain} onChange={e=>setConfirmed(e.target.checked)}/>确认{label}此材质修改</label>
  <button disabled={busy||uncertain||!confirmed} onClick={()=>void execute()}>{busy?'执行中…':label+'材质修改'}</button>
  {error&&<p role="alert">{error}</p>}
 </div>
}
