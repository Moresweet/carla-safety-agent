"use client";
import {useEffect,useRef,useState} from 'react';
import BatchScheduler from './BatchScheduler';
import BatchComparison from './BatchComparison';

const bridge='http://127.0.0.1:8765';
type Batch={batch_id:string;job_count?:number;paused?:boolean;error?:string};
type Row={job_id:string;execution_state:string;attempt_count:number;seed:number;variants:Record<string,string>;execution_id?:string;benchmark_passed:boolean|null;metrics?:Record<string,unknown>;metrics_error?:string;error?:string};
type Report={paused:boolean;job_count:number;rows:Row[];state_counts:Record<string,number>};
async function api<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch(bridge+path,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
 const value=await response.json() as T & {ok?:boolean;error?:string};if(!response.ok||value.ok===false)throw new Error(value.error||'请求失败');return value;
}
export default function BatchPanel(){
 const [items,setItems]=useState<Batch[]>([]),[cursor,setCursor]=useState<string|null>(null),[selected,setSelected]=useState(''),[report,setReport]=useState<Report|null>(null);
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[confirmed,setConfirmed]=useState(false);
 const lock=useRef(false),revision=useRef(0);
 const [pollError,setPollError]=useState('');
 async function perform(work:()=>Promise<void>){if(lock.current)return;revision.current++;lock.current=true;setBusy(true);setError('');try{await work()}catch(e){setError(String(e))}finally{revision.current++;lock.current=false;setBusy(false)}}
 async function list(after?:string){const value=await api<{batches:Batch[];next_cursor:string|null}>('/batches'+(after?'?after='+encodeURIComponent(after):''));setItems(old=>after?[...old,...value.batches]:value.batches);setCursor(value.next_cursor)}
 async function read(id:string){setReport(null);setConfirmed(false);setSelected(id);const value=await api<{report:Report}>('/batches/report?batch_id='+encodeURIComponent(id));setReport(value.report)}
 useEffect(()=>{void perform(()=>list())},[]);
 useEffect(()=>{
  if(!selected)return;
  let disposed=false;let timer:ReturnType<typeof setTimeout>;
  setPollError('');
  async function poll(){
   const version=revision.current;
   if(!lock.current){try{const value=await api<{report:Report}>('/batches/report?batch_id='+encodeURIComponent(selected));if(!disposed&&!lock.current&&version===revision.current){setReport(old=>JSON.stringify(old)===JSON.stringify(value.report)?old:value.report);setPollError('')}}catch(e){if(!disposed&&version===revision.current)setPollError(`自动刷新失败：${String(e)}`)}}
   if(!disposed)timer=setTimeout(poll,2000);
  }
  timer=setTimeout(poll,2000);return()=>{disposed=true;clearTimeout(timer)};
 },[selected]);
 async function control(action:string,job_id?:string){await perform(async()=>{
  const value=await api<{action?:string}>('/batches/control',{batch_id:selected,action,...(job_id?{job_id}:{})});
  setMessage(action==='advance'?`推进结果：${value.action}。请刷新核对状态；若后台调度仍在运行，它会继续处理队列。`:'操作已保存。暂停与恢复不终止当前仿真；正在运行的后台调度可能继续处理恢复后的队列。');
  await read(selected);await list();
 })}
 return <section className="batch-panel" aria-label="批量实验" style={{padding:'20px',border:'1px solid #334155',borderRadius:'8px',marginTop:'20px'}}>
  <h2>批量实验</h2>
  <p>导入五维矩阵 JSON 创建待执行队列。读取和刷新不会启动仿真。</p>
  <BatchScheduler batchId={selected} paused={!report||report.paused} onSelect={id=>void perform(()=>read(id))}/>
  <div style={{display:'flex',gap:'12px',flexWrap:'wrap',alignItems:'center'}}>
   <label>导入矩阵 <input aria-label="导入批次矩阵 JSON" type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;void perform(async()=>{if(file.size>8*1024*1024)throw new Error('矩阵文件超过 8 MiB');const document=JSON.parse(await file.text());const value=await api<{batch_id:string}>('/batches/create',document.dimensions??document);setMessage('队列已创建，尚未启动任何任务。');await list();await read(value.batch_id)})}}/></label>
   <button disabled={busy} onClick={()=>void perform(()=>list())}>刷新批次列表</button>
   <select aria-label="选择批次" disabled={busy} value={selected} onChange={e=>{const id=e.target.value;if(id)void perform(()=>read(id))}}><option value="">选择已保存批次</option>{items.map(item=><option key={item.batch_id} value={item.batch_id}>{item.batch_id} · {item.error?'记录损坏':`${item.job_count} 项${item.paused?' · 已暂停':''}`}</option>)}</select>
   {cursor&&<button disabled={busy} onClick={()=>void perform(()=>list(cursor))}>加载更多批次</button>}
  </div>
  {selected&&<button disabled={busy} onClick={()=>void perform(()=>read(selected))}>刷新所选批次状态</button>}
  {pollError&&<p role="alert">{pollError}。当前显示的是上次读取的报告。</p>}
  {report&&<>
   <p>共 {report.job_count} 项 · {report.paused?'已暂停排队':'允许新任务'} · {Object.entries(report.state_counts).map(([state,count])=>`${state}: ${count}`).join(' / ')}</p>
   <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>我已检查批次，允许本次推进启动一个真实评测任务</label>
   <div style={{display:'flex',gap:'12px',flexWrap:'wrap',margin:'12px 0'}}>
    <button disabled={busy||!confirmed} onClick={()=>void control('advance')}>推进一步 / 核对执行结果</button>
    <button disabled={busy} onClick={()=>void control(report.paused?'resume':'pause')}>{report.paused?'恢复排队':'暂停排队'}</button>
   </div>
   <div style={{overflowX:'auto'}}><table style={{width:'100%',textAlign:'left'}}><thead><tr>{['模型 / 场景','天气 / 纹理 / 种子','执行状态','驾驶结论','尝试','操作'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{report.rows.map(row=><tr key={row.job_id}>
    <td>{row.variants.models} / {row.variants.scenes}</td><td>{row.variants.weather} / {row.variants.textures} / {row.seed}</td><td>{row.execution_state}<small style={{display:'block',overflowWrap:'anywhere'}}>{row.execution_id}</small></td><td>{row.benchmark_passed===null?'未核验':row.benchmark_passed?'通过':'未通过'}{(row.metrics_error||row.error)&&<p role="alert">{row.metrics_error||row.error}</p>}</td><td>{row.attempt_count}</td><td><button disabled={busy||!['failed','stopped'].includes(row.execution_state)} onClick={()=>void control('retry',row.job_id)}>重新排队</button>{row.metrics&&<details><summary>查看指标</summary><pre>{JSON.stringify(row.metrics,null,2)}</pre></details>}</td>
   </tr>)}</tbody></table></div>
   <p>执行完成不等于驾驶通过；数据质量尚未自动核验。报告每两秒自动刷新。重新排队保留历史；活跃后台调度会处理待执行项。</p>
   <BatchComparison key={selected} batchId={selected} rows={report.rows}/>
  </>}
  <p role="status">{busy?'正在读取或保存，请勿重复操作…':message}</p>{error&&<p role="alert">{error}。若推进请求失败，请先刷新并核对执行记录，不要重新创建相同任务。</p>}
 </section>
}
