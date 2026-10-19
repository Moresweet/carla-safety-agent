"use client";
import {useRef,useState} from 'react';
import {parseStorageReview,filterStorageRows,type Review} from './storageReview';
const gib=(bytes:number)=>(bytes/1024**3).toFixed(2)+' GiB';
export default function CaptureStorage({onOpen,invalidated=false}:{onOpen:(id:string)=>void;invalidated?:boolean}){
 const [result,setResult]=useState<Review|null>(null),[pending,setPending]=useState(false),[error,setError]=useState('');
 const active=useRef(false);
 const [query,setQuery]=useState(''),[status,setStatus]=useState(''),[keptOnly,setKeptOnly]=useState(false);
 const rows=filterStorageRows(result?.recordings??[],query,status,keptOnly);
 async function scan(){
  if(active.current)return;active.current=true;setPending(true);setError('');setResult(null);
  try{
   const response=await fetch('http://127.0.0.1:8765/datasets/storage',{signal:AbortSignal.timeout(60000)});
   const value=await response.json();
   if(!response.ok)throw Error(response.status===409?'已有盘点正在运行，请稍后手动重试':`盘点请求失败（HTTP ${response.status}）`);
   setResult(parseStorageReview(value));
  }catch(e){setError(String(e))}finally{active.current=false;setPending(false)}
 }
 return <section aria-label="录制空间盘点"><h3>录制空间</h3>
  <p>手动只读盘点，按占用排序。检查本地有效项目包及已登记数据划分的引用；损坏或未完成文件会标记盘点不完整。未标记或未发现引用不代表可以删除；未登记的外部划分和其他外部文件不在检查范围内。</p>
  <button disabled={pending} onClick={()=>void scan()}>{pending?'正在盘点…':'盘点录制占用'}</button>
  {invalidated&&!result&&<p role="status">已发起保留标记或划分登记操作，旧盘点已清除；请确认操作结果后重新盘点。</p>}
  {error&&<p role="alert">{error}。未自动重试。</p>}
  {result&&<><p role="status">{result.complete?'本次范围内扫描完成':'扫描不完整，请勿据此清理'} · {result.recordings.length} 个目录 · 占用 {gib(result.allocated_bytes)} · 磁盘可用 {gib(result.free_bytes)}（扫描时值）</p>
   {result.warnings.map((warning,i)=><p key={i} role="alert">{warning}</p>)}
   <label>录制 ID 搜索<input aria-label="空间盘点搜索" value={query} onChange={e=>setQuery(e.target.value)}/></label>
   <label>状态<select aria-label="空间盘点状态" value={status} onChange={e=>setStatus(e.target.value)}><option value="">全部状态</option>{[...new Set(result.recordings.map(row=>row.status??'unknown'))].sort().map(value=><option key={value} value={value}>{value}</option>)}</select></label>
   <label><input type="checkbox" checked={keptOnly} onChange={e=>setKeptOnly(e.target.checked)}/>仅看显式保留</label>
   <p>筛选显示 {rows.length} / {result.recordings.length} 个目录；筛选不改变保留状态或删除权限。</p>
   <div style={{maxHeight:360,overflow:'auto'}}><table style={{width:'100%',borderCollapse:'separate',borderSpacing:'12px 8px',textAlign:'left'}}><thead><tr><th>录制</th><th>占用</th><th>状态</th><th>保留/引用</th></tr></thead><tbody>{rows.map(row=><tr key={row.directory}>
    <td><button title={row.directory} onClick={()=>onOpen(row.directory)}>{row.directory}</button></td><td style={{whiteSpace:'nowrap'}}>{gib(row.allocated_bytes)}</td><td>{row.status??'未知'}</td><td>{row.keep_reason??'未显式保留'} · 衍生引用 {row.derived_referenced_by.length} · 队列引用 {row.queue_referenced_by.length} · 项目引用 {row.project_referenced_by.length} · 已登记划分引用 {row.split_referenced_by.length}</td>
   </tr>)}</tbody></table></div></>}
 </section>;
}
