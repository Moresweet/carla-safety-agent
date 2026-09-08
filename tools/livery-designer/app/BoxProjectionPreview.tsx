"use client";
import {useEffect,useState} from 'react';
type Boxes={frame:number;camera:string;width:number;height:number;missing_geometry:number;boxes:{actor_id:number;type:string;segments:number[][]}[]};
export default function BoxProjectionPreview({runId,frame,camera}:{runId:string;frame:number;camera:string}){
 const [data,setData]=useState<Boxes|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();setData(null);setError('');
 void fetch(`http://127.0.0.1:8765/datasets/boxes?${new URLSearchParams({run_id:runId,frame:String(frame),camera})}`,{signal:controller.signal})
 .then(async response=>{const v=await response.json() as Boxes & {ok?:boolean;error?:string};if(!v||!response.ok||!v.ok)throw new Error(v?.error??'物体框读取失败');
 if(v.frame!==frame||v.camera!==camera||!Number.isInteger(v.width)||v.width<=0||!Number.isInteger(v.height)||v.height<=0||!Array.isArray(v.boxes)||!Number.isInteger(v.missing_geometry))throw new Error('物体框数据无效');
 for(const b of v.boxes)if(!Array.isArray(b.segments)||b.segments.some((s:unknown)=>!Array.isArray(s)||s.length!==4||s.some(n=>typeof n!=='number'||!Number.isFinite(n))))throw new Error('物体框线段无效');
 return v as Boxes;})
 .then(v=>{if(!controller.signal.aborted)setData(v)})
 .catch(e=>{if(!controller.signal.aborted)setError(String(e))});return()=>controller.abort();
 },[runId,frame,camera,retry]);
 const statusStyle={position:'absolute' as const,top:4,left:4,background:'#09121de6',color:'#fff',fontSize:'14px'};
 if(error)return <span role="alert" style={statusStyle}>{error} <button onClick={()=>setRetry(v=>v+1)}>重试物体框</button></span>;
 if(!data)return <span role="status" style={statusStyle}>物体框加载中</span>;
 return <><svg aria-label={`物体框 ${data.boxes.length} 个，未检查遮挡`} viewBox={`0 0 ${data.width} ${data.height}`} preserveAspectRatio="xMidYMid meet" style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none'}}>
 {data.boxes.map(b=><g key={b.actor_id}><title>{b.type} · ID {b.actor_id}</title>{b.segments.map(([x1,y1,x2,y2],i)=><line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#5de2bc" strokeWidth={1.5} vectorEffect="non-scaling-stroke"/>)}</g>)}
 </svg><span role="status" style={statusStyle}>{data.boxes.length} 个几何框{data.missing_geometry>0?` · ${data.missing_geometry} 个对象缺少完整几何`:''}</span></>;
}
