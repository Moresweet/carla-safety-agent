"use client";
import {useEffect,useRef,useState} from 'react';
type Job={request_id:string;source_run_id:string;state:'running'|'archived'|'failed'|'needs_attention';error?:string;archive_bytes?:number};
const endpoint='http://127.0.0.1:8765/datasets/archive';
export default function CaptureArchive({runId}:{runId:string}){
 const [confirmed,setConfirmed]=useState(false),[job,setJob]=useState<Job|null>(null),[requestId,setRequestId]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const active=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;try{const saved=sessionStorage.getItem('capture-archive:'+runId);if(saved&&/^[a-f0-9]{32}$/.test(saved))setRequestId(saved)}catch{}return()=>{alive.current=false}},[runId]);
 async function checked(response:Response,id:string){
  const value=await response.json() as Job&{ok?:boolean};
  if(!response.ok||value.ok!==true)throw Error(value.error??`归档请求失败 HTTP ${response.status}`);
  if(value.request_id!==id||value.source_run_id!==runId||!['running','archived','failed','needs_attention'].includes(value.state))throw Error('归档任务身份或状态不匹配');
  return value;
 }
 async function read(id=requestId){
  if(!id||active.current)return;
  active.current=true;setBusy(true);
  try{const value=await checked(await fetch(endpoint+'?request_id='+id,{signal:AbortSignal.timeout(15000)}),id);if(alive.current){setJob(value);setError('')}}
  catch(e){if(alive.current)setError(String(e)+'；请查询原任务，不会自动重新归档。')}
  finally{active.current=false;if(alive.current)setBusy(false)}
 }
 useEffect(()=>{if(requestId)void read(requestId)},[requestId]);
 useEffect(()=>{if(job?.state!=='running'||error)return;const timer=setTimeout(()=>void read(),1500);return()=>clearTimeout(timer)},[job,error]);
 async function start(){
  if(!confirmed||active.current||job)return;
  active.current=true;setBusy(true);setError('');
  const id=requestId||crypto.randomUUID().replaceAll('-','');
  setConfirmed(false); // Every submission, including uncertain retry, needs a new confirmation.
  try{
   sessionStorage.setItem('capture-archive:'+runId,id);setRequestId(id);
   const value=await checked(await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(15000),body:JSON.stringify({run_id:runId,request_id:id,confirmed:true})}),id);
   if(alive.current){setJob(value);setConfirmed(false)}
  }catch(e){if(alive.current)setError(String(e)+'；结果可能不明确，请查询原请求。')}
  finally{active.current=false;if(alive.current)setBusy(false)}
 }
 return <section aria-label="录制归档"><h3>归档原始录制</h3>
  <p>创建并校验独立 ZIP，原目录保留，不会释放原录制空间。要求工作台空闲；归档不证明数据质量或驾驶成功。</p>
  <label><input type="checkbox" checked={confirmed} disabled={busy||!!job} onChange={e=>setConfirmed(e.target.checked)}/>确认占用额外空间创建归档，不删除原件</label>
  <button disabled={!confirmed||busy||!!job} onClick={()=>void start()}>{requestId?'使用原请求 ID 重新提交':'创建并校验归档'}</button>
  {requestId&&!job&&<p>请先查询原任务；若仍无法确认，可重新勾选后使用同一个 ID 提交，服务器已有任务不会重复创建。</p>}
  {requestId&&<><p>请求 ID：{requestId} · 状态：{job?.state??'尚未确认'}</p><button disabled={busy} onClick={()=>void read()}>查询原归档任务</button></>}
  {(error||job?.error)&&<p role="alert">{error||job?.error}</p>}
  {job?.state==='archived'&&<a href={endpoint+'/download?request_id='+job.request_id} download>下载已校验归档 ZIP</a>}
  {job?.state==='failed'&&<button disabled={busy} onClick={()=>{try{sessionStorage.removeItem('capture-archive:'+runId);setRequestId('');setJob(null);setConfirmed(false);setError('')}catch(e){setError(String(e))}}}>准备新请求（保留失败产物）</button>}
 </section>;
}
