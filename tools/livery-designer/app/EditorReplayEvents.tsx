"use client";
import {useEffect,useState} from 'react';
type Event={command_id:string;action:string|null;boundary_frame:number;seek_frame:number|null;outcome:string};
type Archive={ok:boolean;available:boolean;events:Event[];error?:string};
export default function EditorReplayEvents({runId,onSeek}:{runId:string;onSeek:(frame:number)=>void}){
 const [data,setData]=useState<Archive|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0),[selected,setSelected]=useState('');
 useEffect(()=>{const abort=new AbortController();setData(null);setError('');setSelected('');
  void fetch('http://127.0.0.1:8765/datasets/editor-events?run_id='+encodeURIComponent(runId),{signal:abort.signal})
   .then(async r=>{const v=await r.json() as Archive;if(!r.ok||!v.ok)throw new Error(v.error||'无法读取编辑事件');
    if(typeof v.available!=='boolean'||!Array.isArray(v.events)||!v.events.every(e=>e&&typeof e.command_id==='string'&&
      (e.action===null||typeof e.action==='string')&&Number.isInteger(e.boundary_frame)&&
      (e.seek_frame===null||Number.isInteger(e.seek_frame))&&['acknowledged','uncertain'].includes(e.outcome)))throw new Error('编辑事件格式异常');
    if(!abort.signal.aborted)setData(v)}).catch(e=>{if(!abort.signal.aborted)setError(String(e))});
  return()=>abort.abort();
 },[runId,retry]);
 const event=data?.events.find(e=>e.command_id===selected);
 return <section aria-label="编辑命令回放" style={{fontSize:'14px',margin:'16px 0'}}><h3>编辑命令记录</h3>
  <p>包含目录查询等只读操作。定位到命令之后的首个保存帧，不代表修改已正确渲染；不确定记录仅供检查。</p>
  {error?<p role="alert">{error} <button onClick={()=>setRetry(v=>v+1)}>重试编辑事件</button></p>:!data?<p role="status">正在读取编辑记录…</p>:!data.available?<p>此录制没有归档编辑事件。</p>:!data.events.length?<p>归档中没有命令。</p>:<>
   <label>选择命令 <select aria-label="编辑命令" value={selected} onChange={e=>{setSelected(e.target.value);const item=data.events.find(v=>v.command_id===e.target.value);if(item?.seek_frame!=null)onSeek(item.seek_frame)}}>
    <option value="" disabled>选择命令（共 {data.events.length} 条）</option>
    {data.events.map(e=><option key={e.command_id} value={e.command_id}>{e.action??'未解析命令'} · 边界帧 {e.boundary_frame} · {e.outcome==='uncertain'?'结果不确定':e.seek_frame===null?'录制范围外':'可定位'}</option>)}
   </select></label>
   {event&&<p role="status">命令 {event.command_id}；回放帧 {event.seek_frame??'不可定位'}。</p>}
  </>}
 </section>
}
