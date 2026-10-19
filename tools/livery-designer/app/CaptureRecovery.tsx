"use client";
import {useEffect,useRef,useState} from 'react';
import {serialPoll} from './serialPoll';
import {readWithRetry} from './readWithRetry';
import {requestCaptureRecovery} from './captureRecoveryRequest';
import {parseRecoveryJob,candidateLocation,recoverySubmissionId,type RecoveryJob as Job} from './captureRecoveryJob';
const bridge='http://127.0.0.1:8765';
export default function CaptureRecovery({runId,onRecovered}:{runId:string;onRecovered:(id:string)=>void}){
 const [confirmed,setConfirmed]=useState(false),[job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
 const active=useRef(false);
 const attempt=useRef<string|null>(null);
 const lifetime=useRef<AbortController|null>(null);
 useEffect(()=>{const controller=new AbortController();lifetime.current=controller;active.current=false;setPending(false);return()=>controller.abort()},[runId]);
 useEffect(()=>{setJob(null);setConfirmed(false);setError('');attempt.current=null;try{const id=sessionStorage.getItem('capture-recovery:'+runId);if(id&&/^[a-f0-9]{32}$/.test(id)){attempt.current=id;setJob({request_id:id,state:'checking'})}}catch{}},[runId]);
 useEffect(()=>{
  if(pending||!job||!['running','checking'].includes(job.state))return;
  const id=job.request_id;
  const poll=serialPoll(async signal=>{try{
   const v=parseRecoveryJob(await readWithRetry<unknown>(`${bridge}/datasets/recovery?request_id=${id}`,{signal,attempts:1}),id,runId);
   if(!signal.aborted){setJob(v);setError('')}
  }catch(e){if(!signal.aborted)setError(String(e))}},1500);
  void poll.refresh();return()=>poll.stop();
 },[job?.request_id,job?.state,runId,pending]);
 async function start(){
  if(!confirmed||active.current||(job&&['running','needs_attention','recovered'].includes(job.state)))return;
  let request_id:string;
  try{request_id=recoverySubmissionId(job,attempt.current,()=>crypto.randomUUID().replaceAll('-',''))}catch(e){setError(String(e));return}
  active.current=true;setPending(true);setError('');
  attempt.current=request_id;
  const signal=lifetime.current?.signal;
  if(!signal||signal.aborted){active.current=false;setPending(false);return}
  try{
   sessionStorage.setItem('capture-recovery:'+runId,request_id);
   const v=await requestCaptureRecovery(runId,request_id,signal);
   if(!signal.aborted){setJob(v);setConfirmed(false)}
  }catch(e){if(!signal.aborted){setJob({request_id,state:'checking'});setConfirmed(false);setError(String(e)+'；保留请求 ID 并只读查询，不自动再次创建副本。')}}finally{if(!signal.aborted){active.current=false;setPending(false)}}
 }
 const busy=pending||job?.state==='running'||job?.state==='needs_attention'||job?.state==='recovered';
 return <section aria-label="恢复中断录制"><h3>恢复已提交样本</h3>
  <p>创建独立副本并校验六视角、深度、点云和标定；原目录保留。只排除未提交尾帧，不修补损坏数据。要求采集进程已退出且工作台无活动任务。</p>
  <label><input aria-label="确认创建恢复副本" type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>确认占用额外磁盘空间创建副本，并在校验通过后加入回放清单</label>
  {job?.state==='checking'&&<p>启动结果未知。可明确确认后重交同一请求 ID：服务若已接收，仅返回原任务；若未接收，才启动本次恢复。不会改用新 ID 创建第二份副本。</p>}
  <button disabled={!confirmed||busy} onClick={()=>void start()}>{job?.state==='checking'?'使用原请求 ID 继续恢复':'创建并校验恢复副本'}</button>
  {job&&<p role="status">恢复状态：{job.state} · 请求 {job.request_id}</p>}
  {job?.candidate_presence&&<p role="status">{candidateLocation(job.candidate_presence)}。仅检查目录存在性，没有重新校验原始数据，不会据此将中断任务标为成功。</p>}
  {job?.staging_directory&&<p>本请求暂存位置：{job.staging_directory}<br/>处理阶段：{job.phase??'未知'}{job.candidate_run_id&&<> · 候选副本：{job.candidate_run_id}</>}。暂存位置和候选 ID 不证明发布成功；中断后请检查，勿手动删除原件。</p>}
  {(error||job?.error)&&<p role="alert">{error||job?.error}。不会自动重试；已有副本和原件保留。</p>}
  {job?.state==='recovered'&&job.recovered_run_id&&<button onClick={()=>onRecovered(job.recovered_run_id!)}>打开恢复副本回放</button>}
 </section>;
}
