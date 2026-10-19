"use client";
import {useEffect,useRef,useState} from 'react';
import {readWithRetry,ReadHttpError} from './readWithRetry';
import {parseRuntimeStorage,formatRuntimeBytes as gib,type RuntimeStorage as Report} from './runtimeStorage';
export default function RuntimeStorage(){
 const [report,setReport]=useState<Report|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false),[at,setAt]=useState('');
 const active=useRef<AbortController|null>(null);
 useEffect(()=>()=>{active.current?.abort();active.current=null},[]);
 async function scan(){
  if(active.current)return;
  const controller=new AbortController();active.current=controller;
  setPending(true);setReport(null);setError('');
  try{
   const value=await readWithRetry<unknown>('http://127.0.0.1:8765/system/runtime-storage',{signal:controller.signal,timeoutMs:60000,attempts:1});
   if(controller.signal.aborted)return;
   setReport(parseRuntimeStorage(value));setAt(new Date().toLocaleString());
  }catch(e){if(!controller.signal.aborted)setError(e instanceof ReadHttpError&&e.status===409?'已有运行目录盘点正在进行，请结束后手动重试':String(e))}
  finally{if(active.current===controller){active.current=null;setPending(false)}}
 }
 return <section aria-label="全部运行目录空间"><h3>全部运行目录空间</h3>
  <p>包含录制、预览、中间产物和日志。只读盘点，不自动删除；无引用或占用较大不代表可以清理。</p>
  <button disabled={pending} onClick={()=>void scan()}>{pending?'正在盘点运行目录…':'盘点全部 runtime'}</button>
  {error&&<p role="alert">{error}。未自动重试。</p>}
  {report&&<><p role="status">{report.complete?'本次范围内扫描完成':'存在排除项或读取失败，统计不完整'} · {gib(report.allocated_bytes)} · {report.categories.length} 个分类 · {at}</p>
   <p>仅统计普通文件分配块，硬链接只计一次；不计目录元数据，不追踪符号链接。这是扫描时快照，不是硬配额或删除批准。</p>
   <details><summary>查看排除项与警告（{report.warnings.length}）</summary>{report.warnings.map((w,i)=><p key={i}>{w}</p>)}</details>
   <div style={{maxHeight:360,overflow:'auto'}}><table style={{width:'100%',textAlign:'left',borderSpacing:'12px 8px'}}><thead><tr><th>目录 / 文件</th><th>分配占用</th><th>文件数</th><th>排除链接</th></tr></thead>
    <tbody>{report.categories.map(row=><tr key={row.name}><td>{row.name}</td><td style={{whiteSpace:'nowrap'}}>{gib(row.allocated_bytes)}</td><td>{row.files}</td><td>{row.links_skipped}</td></tr>)}</tbody></table></div>
  </>}
 </section>;
}
