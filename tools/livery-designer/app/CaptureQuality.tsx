"use client";
import {useEffect, useState} from 'react';

const bridge = 'http://127.0.0.1:8765';
type Report = {run_id:string;state:string;detail?:string;finished_at_unix?:number;error?:string};
const labels:Record<string,string> = {not_checked:'尚未检查',running:'正在检查原始文件',passed:'本次检查通过',failed:'检查发现异常',incomplete:'检查未完成'};

export default function CaptureQuality({runId}:{runId:string}) {
 const [report,setReport] = useState<Report|null>(null);
 const [error,setError] = useState('');
 const [pending,setPending] = useState(false);
 useEffect(()=>{
  let active=true;
  const controller=new AbortController();
  async function refresh(){
   try {
    const response=await fetch(`${bridge}/datasets/quality?run_id=${encodeURIComponent(runId)}`,{signal:controller.signal});
    const value=await response.json() as Report;
    if(!response.ok)throw new Error(value.error||'无法读取校验报告');
    if(value.run_id!==runId)throw new Error('校验报告身份不匹配');
    if(active){setReport(value);setError('')}
   } catch(e){if(active)setError(String(e))}
  }
  void refresh(); const timer=setInterval(()=>void refresh(),2000);
  return()=>{active=false;controller.abort();clearInterval(timer)};
 },[runId]);
 async function start(){
  setPending(true);setError('');
  try {
   const response=await fetch(`${bridge}/datasets/quality`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId}),signal:AbortSignal.timeout(10000)});
   const value=await response.json() as Report;
   if(!response.ok)throw new Error(value.error||'无法开始校验');
   if(value.run_id!==runId)throw new Error('校验任务身份不匹配');
   setReport(value);
  } catch(e){setError(String(e))} finally {setPending(false)}
 }
 return <section className="replay-controls" aria-label="原始数据质量检查">
  <h3>原始数据质量检查</h3>
  <p role="status">{report?labels[report.state]??report.state:'读取检查状态…'}{report?.finished_at_unix?` · ${new Date(report.finished_at_unix*1000).toLocaleString()}`:''}</p>
  <button disabled={pending||!report||report.state==='running'} onClick={()=>void start()}>检查六视角、深度、点云与原始输入</button>
  <p>检查保存文件的一致性，不代表驾驶安全或真值标注准确。历史报告不会自动证明当前文件未被修改；修改后请重新检查。</p>
  {error&&<p role="alert">{error}</p>}
  {report?.detail&&<details><summary>查看校验日志</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{report.detail}</pre></details>}
 </section>;
}
