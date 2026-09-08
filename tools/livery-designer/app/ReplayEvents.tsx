"use client";
import {useEffect, useState} from 'react';

type Event = {kind:string;start_frame:number;end_frame:number;start_timestamp:number;sample_count:number;peak_brake:number};
type Collision={frame:number;timestamp:number;other_actor_id:number;other_actor_type:string;
 replay_frame:number|null;exact_saved_frame:boolean;replay_time_offset_s:number|null};
type Collisions={available:boolean;events:Collision[];buffer_dropped_since_sensor_start?:number;invalid_observations_since_sensor_start?:number};

export default function ReplayEvents({runId,onSeek}:{runId:string;onSeek:(frame:number)=>void}) {
 const [events,setEvents]=useState<Event[]|null>(null);
 const [error,setError]=useState('');
 const [retry,setRetry]=useState(0);
 const [collisions,setCollisions]=useState<Collisions|null>(null);
 const [collisionSelection,setCollisionSelection]=useState<number|null>(null);
 useEffect(()=>{
  const abort=new AbortController();setEvents(null);setError('');setCollisions(null);setCollisionSelection(null);
  void fetch(`http://127.0.0.1:8765/datasets/events?run_id=${encodeURIComponent(runId)}`,{signal:abort.signal})
   .then(async response=>{
    const value=await response.json() as {ok?:boolean;error?:string;events?:Event[];collisions?:Collisions};
    if(!response.ok||!value.ok)throw new Error(value.error??'无法读取制动片段');
    if(!Array.isArray(value.events)||!value.events.every((event:Event)=>event&&event.kind==='brake_segment'&&
      Number.isInteger(event.start_frame)&&Number.isInteger(event.end_frame)&&
      event.start_frame>=0&&event.end_frame>=event.start_frame&&Number.isFinite(event.start_timestamp)&&
      Number.isInteger(event.sample_count)&&event.sample_count>0&&Number.isFinite(event.peak_brake)))
      throw new Error('制动片段数据格式异常');
    if(value.collisions&&(!Array.isArray(value.collisions.events)||typeof value.collisions.available!=='boolean'||
      !value.collisions.events.every(event=>event&&Number.isInteger(event.frame)&&Number.isFinite(event.timestamp)&&
       Number.isInteger(event.other_actor_id)&&typeof event.other_actor_type==='string'&&
       typeof event.exact_saved_frame==='boolean'&&(event.replay_frame===null||Number.isInteger(event.replay_frame))&&
       (event.replay_time_offset_s===null||Number.isFinite(event.replay_time_offset_s)))))
      throw new Error('碰撞记录格式异常');
    if(!abort.signal.aborted){setEvents(value.events);setCollisions(value.collisions??null)}
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
  {!error&&events!==null&&<div style={{marginTop:'16px'}}>
   <h3>原生碰撞记录</h3>
   {!collisions?<p>当前服务未提供碰撞记录接口。</p>:!collisions.available?<p>该录制没有原生碰撞记录，不能据此判断没有碰撞。</p>:<>
    <p>由 CARLA 碰撞传感器记录；迟到回调可能缺失。传感器运行期间缓存丢弃 {collisions.buffer_dropped_since_sensor_start??0} 条，非法观察 {collisions.invalid_observations_since_sensor_start??0} 条。</p>
    {collisions.events.length===0?<p>未收到碰撞事件。</p>:<label>定位碰撞 <select aria-label="碰撞事件" value={collisionSelection??''} onChange={event=>{
     const index=Number(event.target.value),selected=collisions.events[index];
     if(selected){setCollisionSelection(index);if(selected.replay_frame!==null)onSeek(selected.replay_frame)}
    }}><option value="" disabled>选择碰撞（共 {collisions.events.length} 条）</option>
     {collisions.events.map((event,index)=><option key={index} value={index} disabled={event.replay_frame===null}>
      {event.timestamp.toFixed(2)} s · 碰撞帧 {event.frame} · {event.other_actor_type} #{event.other_actor_id}
     </option>)}
    </select></label>}
    {collisionSelection!==null&&collisions.events[collisionSelection]&&<p role="status">
     碰撞发生帧 {collisions.events[collisionSelection].frame}；回放帧 {collisions.events[collisionSelection].replay_frame??'不可用'}。
     {collisions.events[collisionSelection].exact_saved_frame?'已保存同帧图像。':`附近保存帧，不是碰撞瞬间；时间偏差 ${collisions.events[collisionSelection].replay_time_offset_s?.toFixed(3)??'未知'} s。`}
    </p>}
   </>}
  </div>}
 </section>;
}
