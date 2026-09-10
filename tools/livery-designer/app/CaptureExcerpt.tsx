"use client";
import {useEffect,useRef,useState} from 'react';
type Selection={run_id:string;frame:number;before_s:number;after_s:number};
type Job={request_id:string;state:string;selection?:Selection;excerpt_run_id?:string;error?:string;window?:{frame_count:number;clipped_before:boolean;clipped_after:boolean}};
const bridge='http://127.0.0.1:8765';
export default function CaptureExcerpt({runId,frame,onOpen}:{runId:string;frame:number|null;onOpen:(id:string)=>void}){
 const [before,setBefore]=useState(2),[after,setAfter]=useState(2),[confirmed,setConfirmed]=useState(false);
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
 const active=useRef(false),attempt=useRef<{id:string;selection:Selection}|null>(null);
 const storage='capture-excerpt:'+runId;
 useEffect(()=>{try{const id=sessionStorage.getItem(storage);if(id&&/^[a-f0-9]{32}$/.test(id))setJob({request_id:id,state:'running'})}catch{}},[storage]);
 useEffect(()=>setConfirmed(false),[runId,frame,before,after]);
 useEffect(()=>{
  if(job?.state!=='running')return;
  let alive=true;
  const poll=async()=>{try{const r=await fetch(`${bridge}/datasets/excerpt?request_id=${job.request_id}`),v=await r.json() as Job;if(!r.ok)throw Error(v.error??'片段状态读取失败');if(alive){setJob(v);setError('')}}catch(e){if(alive)setError(String(e))}};
  void poll();const timer=setInterval(poll,1500);return()=>{alive=false;clearInterval(timer)};
 },[job?.request_id,job?.state]);
 const busy=pending||job?.state==='running'||job?.state==='needs_attention';
 async function start(){
  if(!confirmed||busy||active.current||frame===null)return;
  active.current=true;setPending(true);setError('');
  const selection={run_id:runId,frame,before_s:before,after_s:after};
  if(!attempt.current)attempt.current={id:crypto.randomUUID().replaceAll('-',''),selection};
  const request=attempt.current;
  try{
   // An uncertain response must reuse the original selection and request ID.
   sessionStorage.setItem(storage,request.id);
   const r=await fetch(bridge+'/datasets/excerpt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...request.selection,request_id:request.id,confirmed:true})});
   const v=await r.json() as Job;
   if(!r.ok){sessionStorage.removeItem(storage);attempt.current=null;throw Error(v.error??'归档启动失败')}
   setJob(v);setConfirmed(false);attempt.current=null;
  }catch(e){setError(String(e))}finally{active.current=false;setPending(false)}
 }
 return <section aria-label="诊断片段归档"><h3>保存诊断片段并导出 ZIP</h3>
  <p>中心为当前录制帧 {frame??'加载中'}，按原时间戳截取，不插帧。最多 256 帧 / 4 GiB，需要副本与 ZIP 的额外空间；原录制不改动。要求工作台无活动任务。</p>
  <label>向前秒数<input aria-label="片段向前秒数" type="number" min={0} max={10} step={0.1} value={before} disabled={busy} onChange={e=>setBefore(+e.target.value)}/></label>
  <label>向后秒数<input aria-label="片段向后秒数" type="number" min={0} max={10} step={0.1} value={after} disabled={busy} onChange={e=>setAfter(+e.target.value)}/></label>
  <label><input aria-label="确认保存诊断片段" type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>确认复制原始多传感器数据、标定及窗口内事件，校验通过后保存为独立回放片段</label>
  <button disabled={!confirmed||busy||frame===null||![before,after].every(v=>Number.isFinite(v)&&v>=0&&v<=10)} onClick={()=>void start()}>保存当前诊断片段并导出 ZIP</button>
  {job&&<p role="status">片段状态：{job.state} · 请求 {job.request_id}{job.selection&&` · 已提交中心帧 ${job.selection.frame}`}</p>}
  {job?.window&&<p>选中 {job.window.frame_count} 帧{(job.window.clipped_before||job.window.clipped_after)&&'；请求范围超出录制边界，已截至现有样本'}</p>}
  {(error||job?.error)&&<p role="alert">{error||job?.error}。不会自动重新导出；已有副本保留。响应不确定时再次点击会复用原请求及其选中范围。</p>}
  {job?.state==='ready'&&job.excerpt_run_id&&<><a href={`${bridge}/datasets/excerpt/download?request_id=${job.request_id}`} download>下载诊断片段 ZIP</a><button onClick={()=>onOpen(job.excerpt_run_id!)}>打开诊断片段回放</button></>}
 </section>;
}
