"use client";
import {useEffect,useState} from 'react';
type Point={xyz_m:number[];dt_s:number};
type Track={frame:number;history:Point[];future:Point[];error?:string};
export default function RecordedTrajectory({runId,frame}:{runId:string;frame:number}){
 const [track,setTrack]=useState<Track|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setTrack(null);setError('');
 void fetch(`http://127.0.0.1:8765/datasets/trajectory?${new URLSearchParams({run_id:runId,frame:String(frame)})}`,{signal:controller.signal})
 .then(async response=>{const value=await response.json() as Track;if(!response.ok)throw new Error(value.error??'轨迹不可用');return value})
 .then(value=>{if(!controller.signal.aborted)setTrack(value)})
 .catch(e=>{if(!controller.signal.aborted)setError(String(e))});return()=>controller.abort();
 },[runId,frame]);
 const points=[...(track?.history??[]),...(track?.future??[])];
 const extent=Math.max(10,...points.flatMap(p=>p.xyz_m.slice(0,2).map(Math.abs)))*1.1;
 const plot=(ps:Point[])=>ps.map(p=>`${160+p.xyz_m[1]*140/extent},${160-p.xyz_m[0]*140/extent}`).join(' ');
 const current=track?.history.slice(-1)??[];
 return <section className="trajectory-panel"><h3>已录制自车轨迹 · 前后 5 秒</h3>
 {error?<p role="alert">{error}</p>:!track?<p role="status">读取真实轨迹…</p>:<>
 <svg viewBox="0 0 320 320" role="img" aria-label="真实历史与未来轨迹，前方朝上，右方朝右">
 <path d="M160 10V310M10 160H310" stroke="#354b60"/>
 <polyline points={plot(track.history)} fill="none" stroke="#69b8ff" strokeWidth="3"/>
 <polyline points={plot([...current,...track.future])} fill="none" stroke="#ffdc48" strokeWidth="3" strokeDasharray="6 3"/>
 <circle cx="160" cy="160" r="4" fill="white"/>
 </svg><p>蓝色实线：历史 {track.history.length} 点 · 黄色虚线：未来 {track.future.length} 点</p>
 <p>当前自车坐标，前方朝上、右方朝右 · 轴范围 ±{extent.toFixed(1)} m</p>
 <p>来自录制位姿，不是模型预测；不插值，录制边界不补造轨迹。</p></>}
 </section>;
}
