"use client";
import {useRef,useState} from 'react';
import {type ObjectRestoreSelection} from './deletionResult';
import {parseDeletionHistory,type DeletionEntry as Entry} from './deletionHistoryData';
export default function DeletionHistory({onSelect}:{onSelect:(selection:ObjectRestoreSelection)=>void}){
 const [rows,setRows]=useState<Entry[]>([]),[status,setStatus]=useState(''),[busy,setBusy]=useState(false);
 const pending=useRef(false);
 async function inspect(row:Entry){
  if(pending.current)return;pending.current=true;setBusy(true);
  setStatus('正在核对 '+row.operation_id);
  try{
   const response=await fetch('http://127.0.0.1:8765/objects/deletion-inspection?operation_id='+encodeURIComponent(row.operation_id),{signal:AbortSignal.timeout(15000)});
   const raw=await response.json();
   if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('核对响应无效');
   const value=raw as Record<string,unknown>;
   if(!response.ok||value.ok!==true)throw Error(typeof value.error==='string'?value.error:'核对失败');
   if(value.operation_id!==row.operation_id||typeof value.same_episode!=='boolean'||!['present','missing','different_map'].includes(String(value.observation)))throw Error('核对身份或状态无效');
   if(value.observation==='present'&&(typeof value.actor_id!=='number'||!Number.isSafeInteger(value.actor_id)||value.actor_id<=0))throw Error('核对对象ID无效');
   const message=value.observation==='present'?'对象当前存在，Actor '+value.actor_id:value.observation==='missing'?'当前未找到此稳定ID的对象；恢复仍需独立确认':'当前地图不同，不能直接恢复';
   setStatus(row.operation_id+'：'+message+(value.same_episode?'':'；仿真世界已变化')+'。这是即时观察，不修改历史状态。');
  }catch(error){setStatus(String(error))}finally{pending.current=false;setBusy(false)}
 }
 async function refresh(){
  if(pending.current)return;pending.current=true;setBusy(true);setRows([]);
  try{
   const response=await fetch('http://127.0.0.1:8765/objects/deletion-history?limit=50',{signal:AbortSignal.timeout(10000)});
   if(!response.ok)throw Error('删除历史读取失败：HTTP '+response.status);
   const value=parseDeletionHistory(await response.json());
   setRows(value.entries);setStatus((value.complete?'读取成功':'部分记录损坏，列表不完整')+(value.truncated?'；仅显示最近50条':''));
  }catch(error){setStatus(String(error))}finally{pending.current=false;setBusy(false)}
 }
 return <details className="deletion-history"><summary>删除操作历史</summary>
  <p>历史确认不代表对象当前仍不存在。选择备份后，请在单对象恢复区核对对象并明确确认；不会自动恢复。</p>
  <button disabled={busy} onClick={()=>void refresh()}>读取删除历史</button><p role="status">{status}</p>
  {rows.map(row=><div className="deletion-history-entry" key={row.operation_id}>
   <span>{row.type_id} #{row.actor_id} · {row.state==='confirmed'?'删除已确认':'结果待检查'} · {row.operation_id}</span>
   <button disabled={busy} onClick={()=>void inspect(row)}>核对当前对象</button>
   <button disabled={busy} onClick={()=>onSelect(row.backup)}>选择此备份版本</button>
  </div>)}
 </details>;
}
