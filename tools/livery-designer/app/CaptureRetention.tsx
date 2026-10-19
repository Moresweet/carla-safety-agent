"use client";
import {useEffect,useRef,useState} from 'react';

type State={schema_version:string;revision:number;records:Record<string,{reason:string}>};
const endpoint='http://127.0.0.1:8765/datasets/retention';
async function checked(response:Response):Promise<State>{
 const raw:unknown=await response.json();
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('保留状态格式异常');
 const value=raw as Record<string,unknown>;
 if(!response.ok||value.ok!==true)throw Error(typeof value.error==='string'?value.error:'无法读取保留状态');
 if(value.schema_version!=='capture-retention/1'||typeof value.revision!=='number'||!Number.isInteger(value.revision)||value.revision<0||
    !value.records||Array.isArray(value.records)||typeof value.records!=='object')throw Error('保留状态格式异常');
 for(const record of Object.values(value.records)){
  if(!record||typeof record!=='object'||typeof (record as {reason?:unknown}).reason!=='string')throw Error('保留原因格式异常');
 }
 return value as State;
}

export default function CaptureRetention({runId,onWriteAttempt}:{runId:string;onWriteAttempt?:()=>void}){
 const [state,setState]=useState<State|null>(null),[reason,setReason]=useState(''),[error,setError]=useState('');
 const [busy,setBusy]=useState(false),[reload,setReload]=useState(0);
 const pending=useRef(false),generation=useRef(0);
 useEffect(()=>{
  const token=++generation.current;const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),10000);
  setState(null);setError('');pending.current=true;setBusy(true);
  void fetch(endpoint,{signal:controller.signal}).then(checked).then(value=>{
   if(token===generation.current)setState(value);
  }).catch(e=>{if(token===generation.current)setError(String(e));}).finally(()=>{
   clearTimeout(timer);if(token===generation.current){pending.current=false;setBusy(false);}
  });
  return()=>{generation.current++;controller.abort();clearTimeout(timer);};
 },[runId,reload]);
 async function change(){
  if(pending.current||!state||!reason.trim())return;
  const token=generation.current;pending.current=true;setBusy(true);setError('');
  onWriteAttempt?.();
  const keep=!Object.hasOwn(state.records,runId);
  try{
   const value=await checked(await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},
    signal:AbortSignal.timeout(10000),body:JSON.stringify({run_id:runId,keep,reason:reason.trim(),expected_revision:state.revision})}));
   if(token===generation.current){setState(value);setReason('');}
  }catch(e){
   if(token===generation.current){setState(null);setError(String(e)+'；结果可能不明确，请重新读取后确认，不会自动重试。');}
  }finally{if(token===generation.current){pending.current=false;setBusy(false);}}
 }
 const marker=state&&Object.hasOwn(state.records,runId)?state.records[runId]:null;
 return <section aria-label="录制保留设置">
  <h3>录制保留</h3><p>{runId}</p>
  <p role="status">{state?(marker?'已标记保留：'+marker.reason:'未设置显式保留（不代表可以删除）'):'保留状态未确认'}</p>
  <p>仅设置保留标记；取消保留不会删除数据。这不是操作系统写保护。</p>
  <label>修改原因<input aria-label="录制保留原因" value={reason} maxLength={500} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
  <button disabled={busy||!state||!reason.trim()} onClick={()=>void change()}>{marker?'取消保留标记':'标记保留'}</button>
  <button disabled={busy} onClick={()=>setReload(v=>v+1)}>重新读取保留状态</button>
  {error&&<p role="alert">{error}</p>}
 </section>;
}
