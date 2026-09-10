"use client";
import {useEffect,useState} from 'react';
type Projection={width:number;height:number;pixels:number[][];visible_count:number;error?:string;depth_consistency?:{states:string[];counts:Record<string,number>}|null};
const colors:Record<string,string>={consistent:'#ffdc48',behind:'#ff6b85',in_front:'#66cfff',unknown:'#a4acb9'};
export default function ProjectionPreview({runId,frame,camera,depthCheck=false}:{runId:string;frame:number;camera:string;depthCheck?:boolean}){
 const [data,setData]=useState<Projection|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setData(null);setError('');
 void fetch(`http://127.0.0.1:8765/datasets/projection?${new URLSearchParams({run_id:runId,frame:String(frame),camera,depth_check:String(depthCheck)})}`,{signal:controller.signal})
 .then(async response=>{const value=await response.json() as Projection;if(!response.ok)throw new Error(value.error??'投影读取失败');return value})
 .then(value=>{if(!controller.signal.aborted)setData(value)})
 .catch(e=>{if(!controller.signal.aborted)setError(String(e))});return()=>controller.abort();
 },[runId,frame,camera,depthCheck]);
 if(error)return <span role="status" style={{position:'absolute',bottom:4,left:4,background:'#09121d',color:'#fff'}}>{error}</span>;
 if(!data)return <span style={{position:'absolute',bottom:4,left:4}}>投影加载中</span>;
 return <><svg aria-label={`点云投影 ${data.visible_count} 点，${data.depth_consistency?'深度交叉检查，非遮挡真值':'未检查遮挡'}`} viewBox={`0 0 ${data.width} ${data.height}`} preserveAspectRatio="xMidYMid meet" style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none'}}>
 {data.pixels.map(([x,y],i)=><circle key={i} cx={x} cy={y} r={Math.max(2,data.width/350)} stroke="#09121d" strokeWidth={Math.max(.5,data.width/1400)} fill={data.depth_consistency?colors[data.depth_consistency.states[i]]??colors.unknown:'#ffdc48'}/>)}
 </svg>
 {data.depth_consistency&&<span style={{position:'absolute',bottom:0,left:0,right:0,background:'#09121ddd',color:'#fff',fontSize:12}}>
 相符 {data.depth_consistency.counts.consistent} · 后方 {data.depth_consistency.counts.behind} · 前方 {data.depth_consistency.counts.in_front} · 未知 {data.depth_consistency.counts.unknown}
 </span>}</>;
}
