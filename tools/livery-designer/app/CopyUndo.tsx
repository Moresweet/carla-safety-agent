"use client";
import {useRef,useState} from 'react';
import {parseCopyReview,type CopyTarget,type CopyReview} from './copyUndo';
export default function CopyUndo({operation,target,onDone}:{operation:string;target:CopyTarget;onDone:()=>void}){
 const [review,setReview]=useState<CopyReview|null>(null),[checked,setChecked]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const lock=useRef(false);
 async function act(commit:boolean){
  if(lock.current)return;
  if(commit&&(!review||!checked))return;
  lock.current=true;setBusy(true);setError('');
  const selected=review;setReview(null);setChecked(false);
  try{
   const path=commit?'/objects/copy-undo':'/objects/transform-history?actor_id='+target.actor_id;
   const response=await fetch('http://127.0.0.1:8765'+path,commit?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation_id:operation,review:selected,confirmed:true}),signal:AbortSignal.timeout(15000)}:{signal:AbortSignal.timeout(10000)});
   const raw=await response.json();
   if(!raw||typeof raw!=='object')throw Error('副本响应无效');
   const value=raw as {ok?:boolean;error?:string;copy_operation_id?:string};
   if(!response.ok||value.ok!==true)throw Error(value.error||'副本操作失败');
   if(commit){if(value.copy_operation_id!==operation)throw Error('撤销响应身份不匹配');onDone()}
   else setReview(parseCopyReview(value,target));
  }catch(e){setError((commit?'撤销未确认，请先刷新历史检查结果，勿直接重复提交。':'')+String(e))}
  finally{lock.current=false;setBusy(false)}
 }
 return <div><p>副本：{target.type_id} · actor {target.actor_id} · 稳定 ID {target.stable_id}</p>
  <button disabled={busy} onClick={()=>void act(false)}>检查副本以撤销</button>
  {review&&<><p>当前副本位置：x={review.location.x.toFixed(2)}，y={review.location.y.toFixed(2)}，z={review.location.z.toFixed(2)}。撤销将删除此副本（包括复制后的修改），删除前保存恢复备份；源对象保留。</p>
   <label><input type="checkbox" checked={checked} disabled={busy} onChange={e=>setChecked(e.target.checked)}/>我确认删除上述副本</label>
   <button disabled={busy||!checked} onClick={()=>void act(true)}>确认撤销复制</button><button disabled={busy} onClick={()=>{setReview(null);setChecked(false)}}>取消</button></>}
  {error&&<p role="alert">{error}</p>}
 </div>
}
