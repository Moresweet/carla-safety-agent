"use client";
import {useEffect,useRef,useState} from 'react';
type Job={request_id:string;state:string;recovered_run_id?:string;error?:string};
const bridge='http://127.0.0.1:8765';
export default function CaptureRecovery({runId,onRecovered}:{runId:string;onRecovered:(id:string)=>void}){
 const [confirmed,setConfirmed]=useState(false),[job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
 const active=useRef(false);
 const attempt=useRef<string|null>(null);
 useEffect(()=>{try{const id=sessionStorage.getItem('capture-recovery:'+runId);if(id&&/^[a-f0-9]{32}$/.test(id))setJob({request_id:id,state:'running'})}catch{}},[runId]);
 useEffect(()=>{
  if(!job||job.state!=='running')return;
  let alive=true;
  const poll=async()=>{try{const r=await fetch(`${bridge}/datasets/recovery?request_id=${job.request_id}`),v=await r.json() as Job;if(!r.ok)throw Error(v.error??'恢复状态读取失败');if(alive){setJob(v);setError('')}}catch(e){if(alive)setError(String(e))}};
  void poll();const timer=setInterval(poll,1500);return()=>{alive=false;clearInterval(timer)};
 },[job?.request_id,job?.state]);
 async function start(){
  if(!confirmed||active.current||job?.state==='running')return;
  active.current=true;setPending(true);setError('');
  if(job?.state==='failed')attempt.current=null;
  const request_id=attempt.current??crypto.randomUUID().replaceAll('-','');attempt.current=request_id;
  try{
   sessionStorage.setItem('capture-recovery:'+runId,request_id);
   const r=await fetch(bridge+'/datasets/recovery',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId,request_id,confirmed:true})});
   const v=await r.json() as Job;if(!r.ok){sessionStorage.removeItem('capture-recovery:'+runId);attempt.current=null;throw Error(v.error??'恢复启动失败')}setJob(v);setConfirmed(false);
  }catch(e){setError(String(e))}finally{active.current=false;setPending(false)}
 }
 const busy=pending||job?.state==='running'||job?.state==='needs_attention';
 return <section aria-label="恢复中断录制"><h3>恢复已提交样本</h3>
  <p>创建独立副本并校验六视角、深度、点云和标定；原目录保留。只排除未提交尾帧，不修补损坏数据。要求采集进程已退出且工作台无活动任务。</p>
  <label><input aria-label="确认创建恢复副本" type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>确认占用额外磁盘空间创建副本，并在校验通过后加入回放清单</label>
  <button disabled={!confirmed||busy} onClick={()=>void start()}>创建并校验恢复副本</button>
  {job&&<p role="status">恢复状态：{job.state} · 请求 {job.request_id}</p>}
  {(error||job?.error)&&<p role="alert">{error||job?.error}。不会自动重试；已有副本和原件保留。</p>}
  {job?.state==='recovered'&&job.recovered_run_id&&<button onClick={()=>onRecovered(job.recovered_run_id!)}>打开恢复副本回放</button>}
 </section>;
}
