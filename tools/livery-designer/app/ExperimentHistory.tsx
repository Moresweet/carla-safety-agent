"use client";
import {useEffect,useState} from 'react';
const bridge='http://127.0.0.1:8765';
type RecordRow={run_id:string;kind?:string;state?:string;algorithm?:string;started_at?:number;has_starting_scene?:boolean;record_error?:string};
export default function ExperimentHistory({onSaved}:{onSaved:(id:string,name:string)=>void}){
 const [rows,setRows]=useState<RecordRow[]>([]),[cursor,setCursor]=useState<string|null>(null),[selected,setSelected]=useState(''),[busy,setBusy]=useState(false),[status,setStatus]=useState('');
 const current=rows.find(row=>row.run_id===selected);
 async function load(after?:string){
  setBusy(true);setStatus('');
  try{const response=await fetch(bridge+'/experiments?limit=20'+(after?'&after='+encodeURIComponent(after):''));
   const value=await response.json() as {ok:boolean;error?:string;executions:RecordRow[];next_cursor:string|null};
   if(!response.ok||!value.ok||!Array.isArray(value.executions))throw new Error(value.error||'无法读取实验历史');
   if(!value.executions.every((r:RecordRow)=>typeof r.run_id==='string')||(value.next_cursor!==null&&typeof value.next_cursor!=='string'))throw new Error('实验历史格式不正确');
   setRows(previous=>after?[...previous,...value.executions.filter((r:RecordRow)=>!previous.some(p=>p.run_id===r.run_id))]:value.executions);
   setCursor(value.next_cursor);if(!after)setSelected('');
  }catch(error){setStatus(String(error))}finally{setBusy(false)}
 }
 useEffect(()=>{void load()},[]);
 async function save(){
  if(!current?.has_starting_scene||current.record_error)return;
  setBusy(true);setStatus('');
  try{const response=await fetch(bridge+'/scenes/from-experiment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:current.run_id,name:'实验前场景 '+current.run_id.slice(0,8)})});
   const value=await response.json() as {ok:boolean;error?:string;head:{scene_id:string;name:string}};if(!response.ok||!value.ok||typeof value.head?.scene_id!=='string')throw new Error(value.error||'快照保存失败');
   onSaved(value.head.scene_id,value.head.name);setStatus('已保存为独立场景。当前世界未改变；可在上方选择恢复。');
  }catch(error){setStatus(String(error))}finally{setBusy(false)}
 }
 return <section aria-label="实验历史"><h2>实验历史</h2>
  <p>读取本机执行记录。快照是测试前的编辑器状态，不是预设路线生成的场景。列表按执行 ID 排序，不按时间排序。</p>
  <button disabled={busy} onClick={()=>void load()}>刷新实验历史</button>
  <label>历史执行<select disabled={busy} value={selected} onChange={e=>setSelected(e.target.value)}><option value="">选择执行记录（已加载 {rows.length} 条）</option>{rows.map(row=><option key={row.run_id} value={row.run_id}>{row.algorithm||row.kind||'未知类型'} · {row.state||'无法读取'} · {row.run_id.slice(0,8)}{row.has_starting_scene?' · 有快照':''}</option>)}</select></label>
  {cursor&&<button disabled={busy} onClick={()=>void load(cursor)}>加载更多实验</button>}
  {current&&<div><p>执行 ID：{current.run_id}</p>{typeof current.started_at==='number'&&<p>开始时间：{new Date(current.started_at*1000).toLocaleString()}</p>}{current.record_error?<p role="alert">记录读取失败：{current.record_error}</p>:<p>{current.has_starting_scene?'已记录测试前场景':'此记录没有启动前快照，不能据此恢复'}</p>}</div>}
  <button disabled={busy||!current?.has_starting_scene||!!current.record_error} onClick={()=>void save()}>快照保存为场景</button>
  {busy&&<p role="status">正在处理…</p>}<p role="status">{status}</p>
 </section>
}
