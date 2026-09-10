"use client";
import {useEffect,useRef,useState} from 'react';
type Job={request_id:string;state:string;output_bundle_id?:string;error?:string};
const bridge='http://127.0.0.1:8765';
export default function BundleRegistrationPanel({bundleId,count,disabled,onBusy,onRegistered}:{bundleId:string;count:number;disabled:boolean;onBusy:(busy:boolean)=>void;onRegistered:(id:string)=>void}){
 const [confirmed,setConfirmed]=useState(false),[job,setJob]=useState<Job|null>(null),[error,setError]=useState('');
 const active=useRef(false),attempt=useRef<string|null>(null);
 useEffect(()=>{try{const id=sessionStorage.getItem('bundle-registration:'+bundleId);if(id&&/^[a-f0-9]{32}$/.test(id))setJob({request_id:id,state:'running'})}catch{}},[bundleId]);
 useEffect(()=>{onBusy(job?.state==='running');return()=>onBusy(false)},[job?.state,onBusy]);
 useEffect(()=>{
  if(!job||job.state!=='running')return;let alive=true;
  const poll=async()=>{try{const r=await fetch(`${bridge}/projects/bundle/registration?request_id=${job.request_id}`),v=await r.json() as Job;if(!r.ok)throw Error(v.error??'注册状态不可用');if(alive){setJob(v);setError('')}}catch(e){if(alive)setError(String(e))}};
  void poll();const timer=setInterval(poll,1500);return()=>{alive=false;clearInterval(timer)};
 },[job?.request_id,job?.state]);
 async function start(){
  if(active.current||disabled||!confirmed||count<1||count>8)return;
  active.current=true;onBusy(true);setError('');
  const request_id=attempt.current??crypto.randomUUID().replaceAll('-','');attempt.current=request_id;
  try{
   sessionStorage.setItem('bundle-registration:'+bundleId,request_id);
   const r=await fetch(bridge+'/projects/bundle/registration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bundle_id:bundleId,request_id,confirmed:true})});
   const v=await r.json() as Job;
   if(!r.ok){attempt.current=null;sessionStorage.removeItem('bundle-registration:'+bundleId);throw Error(v.error??'注册未启动')}
   setJob(v);setConfirmed(false);
  }catch(e){setError(String(e));onBusy(false)}finally{active.current=false}
 }
 return <section aria-label="项目包源资产注册"><h3>可选：注册源资产到本机 Unreal</h3>
  <p>包含 {count} 个源资产。将以唯一名称创建本机 Unreal 资产，可能耗时数分钟；生成新的引用重映射项目包，不覆盖原包、不生成场景对象、不自动恢复实景。失败保留任务和资产供检查，不自动删除或重试。</p>
  {count>8&&<p>网页最多处理8个源资产，更大项目包请使用命令行。</p>}
  <label><input aria-label="确认注册项目包源资产" type="checkbox" checked={confirmed} disabled={disabled||job?.state==='needs_attention'} onChange={e=>setConfirmed(e.target.checked)}/>确认在本机 Unreal 创建这些资产；完成后再单独确认场景恢复</label>
  <button disabled={disabled||!confirmed||count<1||count>8||job?.state==='needs_attention'} onClick={()=>void start()}>注册源资产并生成新项目包</button>
  {job&&<p role="status">注册状态：{job.state} · 请求 {job.request_id}</p>}
  {(error||job?.error)&&<p role="alert">{error||job?.error}</p>}
  {job?.state==='registered'&&job.output_bundle_id&&<button disabled={disabled} onClick={()=>onRegistered(job.output_bundle_id!)}>打开已注册的新项目包</button>}
 </section>;
}
