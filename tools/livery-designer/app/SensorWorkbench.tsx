"use client";
import {useEffect,useState} from "react";
import ProjectionPreview from './ProjectionPreview';
import BoxProjectionPreview from './BoxProjectionPreview';
import RecordedTrajectory from './RecordedTrajectory';

const bridge="http://127.0.0.1:8765";
const cameras=[['CAM_FRONT_LEFT','左前'],['CAM_FRONT','正前'],['CAM_FRONT_RIGHT','右前'],['CAM_BACK_LEFT','左后'],['CAM_BACK','正后'],['CAM_BACK_RIGHT','右后']];
export type CaptureFrame={frame:number;timestamp:number;model:string|null;source?:string;input_archive?:string;available:string[];missing:string[];synchronized:boolean;actual_model_inputs:string[];trajectory_ego_m?:number[][];control?:{steer:number;throttle:number;brake:number};recording:boolean;recorded_frames:number;run_id?:string;updated_at:number;error?:string};
export default function SensorWorkbench({recorded,runId}:{recorded?:CaptureFrame|null;runId?:string}){
 const [live,setLive]=useState<CaptureFrame|null>(null),[depth,setDepth]=useState(false),[focus,setFocus]=useState<string|null>(null),[error,setError]=useState("");
 useEffect(()=>{if(runId)return;let active=true;const load=async()=>{try{const r=await fetch(`${bridge}/capture/status`);const v=await r.json() as {capture:CaptureFrame|null};if(active){setLive(v.capture);setError("")}}catch{if(active)setError("传感器服务连接中断")}};void load();const timer=setInterval(load,1000);return()=>{active=false;clearInterval(timer)}},[runId]);
 const frame=runId?recorded:live;
 const [projection,setProjection]=useState(false),[boxes,setBoxes]=useState(false);
 useEffect(()=>{if(!focus)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape')setFocus(null)};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[focus]);
 const image=(id:string)=>runId?`${bridge}/datasets/file?run_id=${encodeURIComponent(runId)}&frame=${frame?.frame}&name=${id}.png`:`${bridge}/capture/media?id=${id}&frame=${frame?.frame}`;
 const has=(id:string)=>!!frame?.available?.includes(id);
 const plot=(frame?.trajectory_ego_m??[]).filter(p=>Array.isArray(p)&&p.length>=2).map(p=>`${160+p[0]*4},${230-p[1]*4}`).join(' ');
 return <section className="sensor-workbench"><header><div><h2>{runId?"多模态回放":"传感器工作台"}</h2><span>{frame?`${frame.source==='sensor-rig'?'独立采集':frame.model??'模型采集'} · 帧 ${frame.frame} · ${frame.timestamp?.toFixed(2)} s`:"启动独立采集或闭环测试后显示真实传感器"}</span></div><div className="sensor-toolbar"><button aria-pressed={!depth} onClick={()=>setDepth(false)}>六视角 RGB</button><button aria-pressed={depth} onClick={()=>setDepth(true)}>六视角深度</button></div></header>
 {runId&&<label><input type="checkbox" checked={projection} onChange={e=>setProjection(e.target.checked)}/> RGB 叠加点云投影（黄色 · 未检查遮挡，最多 5000 点/相机）</label>}
 {runId&&<label><input type="checkbox" checked={boxes} onChange={e=>setBoxes(e.target.checked)}/> RGB 叠加物体框（绿色 · 几何投影，未检查遮挡）</label>}
 {(projection||boxes)&&runId&&!depth&&frame&&<div className="surround-grid">{cameras.map(([name,label])=><div key={`${runId}:${frame.frame}:${name}`}><b>{label} · 对齐诊断</b><div style={{position:'relative',aspectRatio:'16 / 9'}}><img src={image(name)} alt={`${label}对齐诊断底图`} style={{width:'100%',height:'100%',objectFit:'contain'}}/>{projection&&<ProjectionPreview runId={runId} frame={frame.frame} camera={name}/>} {boxes&&<BoxProjectionPreview runId={runId} frame={frame.frame} camera={name}/>}</div></div>)}</div>}
 {error&&<p role="alert">{error}</p>}{frame?.error&&<p role="alert">{frame.error}</p>}
 {!runId&&<p>{frame?.recording?'正在录制':'未在录制'} · 已保存 {frame?.recorded_frames??0} 帧。无损数据体积较大，每次录制上限 20 GiB / 2000 帧，磁盘保留至少 1 GiB。</p>}
 <div className="sensor-health">{frame?.synchronized?"同帧 RGB / 深度 / 点云":"等待同帧数据"} · {runId?"已保存数据":frame?.updated_at&&Date.now()/1000-frame.updated_at>5?"数据暂未更新":"实时"}{frame?.missing?.length?` · 缺失：${frame.missing.join(', ')}`:""}</div>
 <div className="surround-grid">{cameras.map(([name,label])=>{const id=depth?'DEPTH_'+name:name;return <button className="sensor-tile" key={name} onClick={()=>setFocus(id)} disabled={!has(id)}><div className="sensor-image">{has(id)?<img src={image(id)} alt={`${label}${depth?'深度':'摄像头'}`}/>:<span>等待 {label}{depth?'深度':'图像'}</span>}</div><span><b>{label}</b><small>{depth?'辅助深度 · 0–80m 显示范围':frame?.actual_model_inputs?.includes(name)?'模型实际输入':frame?.source==='sensor-rig'?'独立采集摄像头':'辅助摄像头（非模型输入）'}</small></span></button>})}</div>
 <div className="sensor-analysis">{[['BEV_POINTS','BEV 点云 · 前方朝上 · ±60m'],['BEV_RGB','BEV 实景 · 顶视 RGB']].map(([id,label])=><button className="sensor-tile" key={id} onClick={()=>setFocus(id)} disabled={!has(id)}><div className="sensor-image square">{has(id)?<img src={image(id)} alt={label}/>:<span>等待 {label}</span>}</div><span><b>{label}</b></span></button>)}<div className="trajectory-panel"><h3>模型预测轨迹</h3><svg viewBox="0 0 320 260" role="img" aria-label="自车坐标系预测轨迹"><path d="M160 10V250M15 230H305" stroke="#354b60"/><polyline points={plot} fill="none" stroke="#5de2bc" strokeWidth="3"/><path d="M160 220l-6 12h12z" fill="white"/></svg><p>横向 / 前向距离（m），每米 4 像素</p><p>转向 {frame?.control?.steer.toFixed(3)??'—'} · 油门 {frame?.control?.throttle.toFixed(2)??'—'} · 制动 {frame?.control?.brake.toFixed(2)??'—'}</p></div></div>
 {runId&&frame&&<RecordedTrajectory key={`${runId}:${frame.frame}`} runId={runId} frame={frame.frame}/>}
 {focus&&<div className="sensor-modal" role="dialog" aria-modal="true" aria-label="传感器大图" onClick={()=>setFocus(null)}><button autoFocus onClick={()=>setFocus(null)}>关闭大图 ×</button><img src={image(focus)} alt={focus}/><p>点击任意位置关闭 · {focus}</p></div>}
 </section>;
}
