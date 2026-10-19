"use client";
import {useEffect,useRef,useState} from 'react';
import {parseMaterialInspection,materialInspectionFailure,type MaterialInspection as Result} from './materialInspection';
import MaterialRecovery from './MaterialRecovery';
export default function MaterialInspection({operation,onRecoveryPending,actor=false}:{operation:string;onRecoveryPending:(operation:string,pending:boolean)=>void;actor?:boolean}){
 const [result,setResult]=useState<Result|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const active=useRef<AbortController|null>(null);
 const recovering=useRef(false);
 const [recoveryBusy,setRecoveryBusy]=useState(false);
 function recoveryPending(pending:boolean){recovering.current=pending;setRecoveryBusy(pending);onRecoveryPending(operation,pending)}
 useEffect(()=>()=>{active.current?.abort();active.current=null},[]);
 async function inspect(){
  if(active.current||recovering.current)return;
  const controller=new AbortController();active.current=controller;setBusy(true);setError('');setResult(null);
  const timer=setTimeout(()=>controller.abort(),15000);
  try{
   const response=await fetch('http://127.0.0.1:8765/materials/'+(actor?'actor-history-inspection':'history-inspection')+'?operation_id='+encodeURIComponent(operation),{signal:controller.signal});
   if(!response.ok){
    let failure:unknown=null;
    try{failure=await response.json()}catch{/* Non-JSON errors keep the HTTP status. */}
    throw Error(materialInspectionFailure(response.status,failure));
   }
   const parsed=parseMaterialInspection(await response.json(),operation,actor);
   if(active.current===controller&&!controller.signal.aborted)setResult(parsed);
  }catch(e){if(active.current===controller)setError(controller.signal.aborted?'检查超时，请重试':String(e))}
  finally{clearTimeout(timer);if(active.current===controller){active.current=null;setBusy(false)}}
 }
 const labels={source:'登记引用与操作起点一致',target:'登记引用与操作目标一致',both:'起点与目标相同，登记引用与二者一致',neither:'登记引用与起点、目标都不一致'};
 return <div><button disabled={busy||recoveryBusy} onClick={()=>void inspect()}>{recoveryBusy?'恢复请求处理中，请等待结果':busy?'检查中…':'只读检查当前材质登记'}</button>
  {error&&<p role="alert">{error}</p>}{result&&<div role="status"><p>{labels[result.matches]}</p><p>当前登记：{result.registered??'无工作台覆盖'}</p><p>操作起点：{result.source??'无工作台覆盖'}<br/>操作目标：{result.target??'无工作台覆盖'}</p><p>仅核对登记引用，未验证原生/GPU 实景状态。本检查不改写历史、不解除待检查状态，也不自动重试修改。</p></div>}
  {result?.recoverable&&<MaterialRecovery actor={actor} key={result.token} operation={operation} inspection={result} onPending={recoveryPending}/>}
  {result?.recovery&&<div role="status"><p>{result.recovery.state==='confirmed'?'后续恢复写入已确认，原操作失败记录仍保留。':result.recovery.state==='attempting'?'恢复请求已记录，结果尚未确认。':'后续恢复也未确认成功，需要检查；禁止直接重复提交。'}</p><p>恢复选择：{result.recovery.choice==='source'?'操作起点':'操作目标'}；恢复纹理：{result.recovery.desired??'原材质（移除工作台覆盖）'}</p><p>{result.registered===result.recovery.desired?'当前登记与恢复目标一致；仍需核对实景。':'当前登记已与恢复目标不同，不能将旧恢复回执视为当前材质状态。'}</p></div>}
 </div>
}
