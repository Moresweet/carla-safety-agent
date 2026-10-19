"use client";
import {useEffect, useRef, useState} from 'react';
import {captureQualityMessage} from './captureQualityMessage';
import {parseQualityReport,type QualityReport as Report} from './qualityReport';

const bridge = 'http://127.0.0.1:8765';
const labels:Record<string,string> = {not_checked:'尚未检查',running:'正在检查原始文件',passed:'本次检查通过',failed:'检查发现异常',incomplete:'检查未完成'};

export default function CaptureQuality({runId}:{runId:string}) {
 const [report,setReport] = useState<Report|null>(null);
 const [error,setError] = useState('');
 const [pending,setPending] = useState(false);
 const [reload,setReload] = useState(0);
 const inFlight=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
 useEffect(()=>{
  let active=true;
  const controller=new AbortController();
  let timer:ReturnType<typeof setTimeout>|undefined;
  async function refresh(){
   if(inFlight.current){timer=setTimeout(()=>void refresh(),2000);return}
   inFlight.current=true;setPending(true);
   let success=false;
   try {
    const response=await fetch(`${bridge}/datasets/quality?run_id=${encodeURIComponent(runId)}`,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(10000)])});
    const value=parseQualityReport(await response.json(),runId,response.ok);
    if(active){setReport(value);setError('');success=true}
   } catch(e){if(active){setReport(null);setError(String(e)+'；自动读取已停止，请手动重新查询。')}}
   finally{inFlight.current=false;if(active){setPending(false);if(success)timer=setTimeout(()=>void refresh(),2000)}}
  }
  void refresh();
  return()=>{active=false;controller.abort();clearInterval(timer)};
 },[runId,reload]);
 async function start(){
  if(inFlight.current||!report||report.state==='running'||error)return;
  inFlight.current=true;
  setPending(true);setError('');
  try {
   const response=await fetch(`${bridge}/datasets/quality`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId}),signal:AbortSignal.timeout(10000)});
   const value=parseQualityReport(await response.json(),runId,response.ok);
   if(alive.current){setReport(value);setReload(value=>value+1)}
  } catch(e){if(alive.current){setReport(null);setError(String(e)+'；提交结果可能不明确，请重新查询，不会自动重新提交。')}} finally {inFlight.current=false;if(alive.current)setPending(false)}
 }
 return <section className="replay-controls" aria-label="原始数据质量检查">
  <h3>原始数据质量检查</h3>
  <p role="status">{report?labels[report.state]??report.state:'读取检查状态…'}{report?.finished_at_unix?` · ${new Date(report.finished_at_unix*1000).toLocaleString()}`:''}</p>
  <button disabled={pending||!report||report.state==='running'} onClick={()=>void start()}>检查六视角、深度、点云与原始输入</button>
  <button disabled={pending} onClick={()=>setReload(value=>value+1)}>重新查询质量任务</button>
  <p>检查保存文件的一致性，不代表驾驶安全或真值标注准确。历史报告不会自动证明当前文件未被修改；修改后请重新检查。</p>
  {report?.manifest_freshness==='changed'&&<p role="alert">录制清单已在检查后变化。上方是历史结果，不能代表当前数据质量，请重新检查。此处只比较清单，不覆盖原始传感器文件变化。</p>}
  {report&&captureQualityMessage(report)&&<p role="alert">{captureQualityMessage(report)}</p>}
  {error&&<p role="alert">{error}</p>}
  {report?.detail&&<details><summary>查看校验日志</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{report.detail}</pre></details>}
 </section>;
}
