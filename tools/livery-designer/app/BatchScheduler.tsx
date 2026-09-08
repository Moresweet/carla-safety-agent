"use client";
import {useEffect,useRef,useState} from 'react';

type Scheduler={state:string;batch_id?:string;scheduler_id?:string;cancel_requested?:boolean;error?:string;last_step?:{action?:string}};
type Capabilities={models:{id:string;name:string;dependencies_available:boolean|null}[];max_jobs:number};
const endpoint='http://127.0.0.1:8765/batches/';
async function request<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch(endpoint+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const value=await response.json() as T & {ok?:boolean;error?:string};
 if(!response.ok||value.ok===false)throw new Error(value.error||`HTTP ${response.status}`);
 return value;
}
export default function BatchScheduler({batchId,paused,onSelect}:{batchId:string;paused:boolean;onSelect:(id:string)=>void}){
 const [scheduler,setScheduler]=useState<Scheduler|null>(null),[capabilities,setCapabilities]=useState<Capabilities|null>(null);
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[readError,setReadError]=useState('');
 const locked=useRef(false),revision=useRef(0);
 useEffect(()=>{setConfirmed(false)},[batchId]);
 useEffect(()=>{
  let disposed=false;let timer:ReturnType<typeof setTimeout>;
  async function poll(){
   const version=revision.current;
   try{const value=await request<{scheduler:Scheduler}>('scheduler');if(!disposed&&!locked.current&&version===revision.current){setScheduler(value.scheduler);setReadError('')}}
   catch(e){if(!disposed)setReadError(String(e))}
   if(!disposed)timer=setTimeout(poll,2000);
  }
  void poll();
  request<Capabilities>('capabilities').then(value=>{if(!disposed)setCapabilities(value)}).catch(e=>{if(!disposed)setReadError(String(e))});
  return()=>{disposed=true;clearTimeout(timer)};
 },[]);
 async function control(action:'start'|'cancel'){
  if(locked.current)return;
  locked.current=true;revision.current++;setBusy(true);setError('');setConfirmed(false);
  try{
   const value=await request<{scheduler:Scheduler}>('scheduler',{batch_id:batchId,action,...(action==='cancel'?{scheduler_id:scheduler?.scheduler_id}:{})});
   setScheduler(value.scheduler);
  }catch(e){setError(`${String(e)}。请等待状态刷新并核对调度记录，不要重复启动。`)}
  finally{revision.current++;locked.current=false;setBusy(false)}
 }
 const active=scheduler?.state==='running';
 return <section aria-label="后台批量调度" style={{padding:'16px 0',fontSize:'1rem'}}>
  <p>{capabilities?`执行适配器：${capabilities.models.map(model=>model.name+(model.dependencies_available===false?'（依赖未就绪）':'')).join('、')}。每批最多 ${capabilities.max_jobs} 项。`:'正在读取模型能力…'}</p>
  <p>纹理配置目前必须为空。启动前仍需环境预检；后台串行执行，失败后等待处理，不自动重试。</p>
  <p>后台调度：{scheduler?.state||'读取中'}{scheduler?.cancel_requested?' · 正在取消后续调度':''}{scheduler?.last_step?.action?` · ${scheduler.last_step.action}`:''}</p>
  {scheduler?.batch_id&&<p style={{overflowWrap:'anywhere'}}>批次：{scheduler.batch_id} <button onClick={()=>onSelect(scheduler.batch_id!)}>查看调度批次</button></p>}
  <label><input type="checkbox" checked={confirmed} disabled={busy||active||!batchId||paused} onChange={e=>setConfirmed(e.target.checked)}/>我允许后台依次启动所选批次中的真实评测任务</label>
  <div style={{display:'flex',gap:'12px',flexWrap:'wrap',marginTop:'12px'}}>
   <button disabled={busy||!scheduler||!!readError||active||!confirmed||paused||!batchId} onClick={()=>void control('start')}>开始后台串行测试</button>
   <button disabled={busy||!!readError||!active||scheduler?.batch_id!==batchId||!scheduler?.scheduler_id||scheduler.cancel_requested} onClick={()=>void control('cancel')}>取消后续调度</button>
  </div>
  <p>关闭或刷新页面不会停止后台调度；取消不终止当前仿真。暂停排队后，需要恢复排队并重新启动已退出的调度。</p>
  {(error||readError||scheduler?.error)&&<p role="alert">{error||readError||scheduler?.error}</p>}
 </section>;
}
