"use client";
import {useEffect, useState} from 'react';

type Event = {kind:string;start_frame:number;end_frame:number;start_timestamp:number;sample_count:number;peak_brake:number};

export default function ReplayEvents({runId,onSeek}:{runId:string;onSeek:(frame:number)=>void}) {
 const [events,setEvents]=useState<Event[]|null>(null);
 const [error,setError]=useState('');
 const [retry,setRetry]=useState(0);
 useEffect(()=>{
  const abort=new AbortController();setEvents(null);setError('');
  void fetch(`http://127.0.0.1:8765/datasets/events?run_id=${encodeURIComponent(runId)}`,{signal:abort.signal})
   .then(async response=>{
    const value=await response.json() as {ok?:boolean;error?:string;events?:Event[]};
    if(!response.ok||!value.ok)throw new Error(value.error??'无法读取制动片段');
    if(!Array.isArray(value.events)||!value.events.every((event:Event)=>event&&event.kind==='brake_segment'&&
      Number.isInteger(event.start_frame)&&Number.isInteger(event.end_frame)&&
      event.start_frame>=0&&event.end_frame>=event.start_frame&&Number.isFinite(event.start_timestamp)&&
      Number.isInteger(event.sample_count)&&event.sample_count>0&&Number.isFinite(event.peak_brake)))
      throw new Error('制动片段数据格式异常');
    if(!abort.signal.aborted)setEvents(value.events);
   }).catch(reason=>{if(!abort.signal.aborted)setError(String(reason))});
  return()=>abort.abort();
 },[runId,retry]);
 return <section aria-label="回放事件定位" style={{margin:'16px 0',fontSize:'14px'}}>
  <h3>制动片段定位</h3>
  <p>记录制动值 ≥ 0.5；包含驻车制动，不代表碰撞或危险事件。选择后暂停播放并跳转。</p>
  {error?<p role="alert">{error} <button onClick={()=>setRetry(value=>value+1)}>重试片段索引</button></p>:
   events===null?<p role="status">正在读取制动片段…</p>:
   events.length===0?<p>没有符合阈值的已记录制动片段。</p>:
   <label>定位片段 <select aria-label="制动片段" value="" onChange={event=>{
    const selected=events[Number(event.target.value)];if(selected)onSeek(selected.start_frame);
   }}><option value="" disabled>选择片段（共 {events.length} 段）</option>
    {events.map((event,index)=><option key={event.start_frame} value={index}>
     {event.start_timestamp.toFixed(2)} s · 帧 {event.start_frame}–{event.end_frame} · {event.sample_count} 样本 · 峰值 {event.peak_brake.toFixed(2)}
    </option>)}
   </select></label>}
 </section>;
}
