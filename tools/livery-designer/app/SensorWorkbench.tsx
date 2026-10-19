"use client";
import {useEffect,useState} from "react";
import ProjectionPreview from './ProjectionPreview';
import BoxProjectionPreview from './BoxProjectionPreview';
import RecordedTrajectory from './RecordedTrajectory';
import RecoverableImage from './RecoverableImage';
import {readWithRetry} from './readWithRetry';

const bridge="http://127.0.0.1:8765";
const cameras=[['CAM_FRONT_LEFT','左前'],['CAM_FRONT','正前'],['CAM_FRONT_RIGHT','右前'],['CAM_BACK_LEFT','左后'],['CAM_BACK','正后'],['CAM_BACK_RIGHT','右后']];
export type CaptureFrame={frame:number;timestamp:number;model:string|null;source?:string;input_archive?:string;available:string[];missing:string[];synchronized:boolean;actual_model_inputs:string[];trajectory_ego_m?:number[][];prediction?:{state:string;right_forward_m?:number[][];reason?:string;contract?:{schema_version:string;reference:string}};control?:{steer:number;throttle:number;brake:number};recording:boolean;recorded_frames:number;run_id?:string;updated_at:number;error?:string};
export default function SensorWorkbench({recorded,runId,onTrajectorySettled}:{recorded?:CaptureFrame|null;runId?:string;onTrajectorySettled?:(runId:string,frame:number,ok:boolean|null)=>void}){
 const [live,setLive]=useState<CaptureFrame|null>(null),[depth,setDepth]=useState(false),[focus,setFocus]=useState<string|null>(null),[error,setError]=useState("");
 const [imageReload,setImageReload]=useState(0);
 useEffect(()=>{
  setError('');setLive(null);if(runId)return;
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
  const load=async()=>{
   try{const value=await readWithRetry<{capture:CaptureFrame|null}>(bridge+'/capture/status',{signal:controller.signal,attempts:1});if(!controller.signal.aborted){setLive(value.capture);setError('')}}
   catch{if(!controller.signal.aborted)setError('传感器服务连接中断，等待恢复；保留画面可能不是实时数据')}
   finally{if(!controller.signal.aborted)timer=setTimeout(load,1000)}
  };
  void load();return()=>{controller.abort();clearTimeout(timer)};
 },[runId]);
 const frame=runId?recorded:live;
 const [projection,setProjection]=useState(false),[boxes,setBoxes]=useState(false);
 const [depthCheck,setDepthCheck]=useState(false);
 useEffect(()=>{if(!focus)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape')setFocus(null)};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[focus]);
 const image=(id:string)=>runId?`${bridge}/datasets/file?run_id=${encodeURIComponent(runId)}&frame=${frame?.frame}&name=${id}.png`:`${bridge}/capture/media?id=${id}&frame=${frame?.frame}`;
 const has=(id:string)=>!!frame?.available?.includes(id);
 const modelViews=[['rgb_front','模型正前'],['rgb_left','模型左侧'],['rgb_right','模型右侧'],['rgb_back','模型正后']];
 const hasModelViews=modelViews.every(([id])=>frame?.actual_model_inputs?.includes(id));
 const prediction=(frame?.prediction?.state==='available'&&frame.prediction.contract?.schema_version==='carla-prediction-spatial/2'?frame.prediction.right_forward_m??[]:[]).filter(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite));
 const extent=Math.max(10,...prediction.flatMap(p=>p.map(Math.abs)))*1.1;
 const plot=prediction.map(p=>`${160+p[0]*115/extent},${130-p[1]*115/extent}`).join(' ');
 return <section className="sensor-workbench"><header><div><h2>{runId?"多模态回放":"传感器工作台"}</h2><span>{frame?`${frame.source==='sensor-rig'?'独立采集':frame.model??'模型采集'} · 帧 ${frame.frame} · ${frame.timestamp?.toFixed(2)} s`:"启动独立采集或闭环测试后显示真实传感器"}</span></div><div className="sensor-toolbar"><button aria-pressed={!depth} onClick={()=>setDepth(false)}>六视角 RGB</button><button aria-pressed={depth} onClick={()=>setDepth(true)}>六视角深度</button></div></header>
 <button onClick={()=>setImageReload(v=>v+1)}>重新加载图像</button>
 {hasModelViews&&<section aria-label="模型原始四视角"><h3>模型原始四视角 · RGB</h3><p>与下方辅助六视角分开显示。录制的原始数组保存在 model_input.npz；此处为{runId?'无损 RGB':'压缩实时'}预览。</p><div className="surround-grid" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}>{modelViews.map(([id,label])=><button className="sensor-tile" key={id} disabled={!has(id)} onClick={()=>setFocus(id)}><div className="sensor-image">{has(id)?<RecoverableImage retryKey={imageReload} src={image(id)} alt={label}/>:<span>此帧未保存独立预览，请查看原始 NPZ</span>}</div><span><b>{label}</b><small>{id} · 模型实际输入</small></span></button>)}</div></section>}
 {runId&&<label><input aria-label="RGB点云投影" type="checkbox" checked={projection} onChange={e=>setProjection(e.target.checked)}/> RGB 叠加点云投影（默认黄色，最多 5000 点/相机；几何投影不证明可见性）</label>}
 {runId&&projection&&<label><input aria-label="点云深度交叉检查" type="checkbox" checked={depthCheck} onChange={e=>setDepthCheck(e.target.checked)}/> 深度交叉检查：黄=相符、红=深度表面后方、蓝=前方、灰=未知；容差 max(0.5m, 2%)，非精确遮挡真值</label>}
 {runId&&<label><input type="checkbox" checked={boxes} onChange={e=>setBoxes(e.target.checked)}/> RGB 叠加物体框（绿色 · 几何投影，未检查遮挡）</label>}
 {(projection||boxes)&&runId&&!depth&&frame&&<div className="surround-grid">{cameras.map(([name,label])=><div key={`${runId}:${frame.frame}:${name}`}><b>{label} · 对齐诊断</b><div style={{position:'relative',aspectRatio:'16 / 9'}}><RecoverableImage retryKey={imageReload} src={image(name)} alt={`${label}对齐诊断底图`} style={{width:'100%',height:'100%',objectFit:'contain'}}/>{projection&&<ProjectionPreview runId={runId} frame={frame.frame} camera={name} depthCheck={depthCheck}/>} {boxes&&<BoxProjectionPreview runId={runId} frame={frame.frame} camera={name}/>}</div></div>)}</div>}
 {error&&<p role="alert">{error}</p>}{frame?.error&&<p role="alert">{frame.error}</p>}
 {!runId&&<p>{frame?.recording?'正在录制':'未在录制'} · 已保存 {frame?.recorded_frames??0} 帧。无损数据体积较大，每次录制上限 20 GiB / 2000 帧，磁盘保留至少 1 GiB。</p>}
 <div className="sensor-health">{frame?.synchronized?"同帧 RGB / 深度 / 点云":"等待同帧数据"} · {runId?"已保存数据":frame?.updated_at&&Date.now()/1000-frame.updated_at>5?"数据暂未更新":"实时"}{frame?.missing?.length?` · 缺失：${frame.missing.join(', ')}`:""}</div>
 <div className="surround-grid">{cameras.map(([name,label])=>{const id=depth?'DEPTH_'+name:name;return <button className="sensor-tile" key={name} onClick={()=>setFocus(id)} disabled={!has(id)}><div className="sensor-image">{has(id)?<RecoverableImage retryKey={imageReload} src={image(id)} alt={`${label}${depth?'深度':'摄像头'}`}/>:<span>等待 {label}{depth?'深度':'图像'}</span>}</div><span><b>{label}</b><small>{depth?'辅助深度 · 0–80m 显示范围':frame?.actual_model_inputs?.includes(name)?'模型实际输入':frame?.source==='sensor-rig'?'独立采集摄像头':'辅助摄像头（非模型输入）'}</small></span></button>})}</div>
 <div className="sensor-analysis">{[['BEV_POINTS','BEV 点云 · 前方朝上 · ±60m'],['BEV_RGB','BEV 实景 · 顶视 RGB']].map(([id,label])=><button className="sensor-tile" key={id} onClick={()=>setFocus(id)} disabled={!has(id)}><div className="sensor-image square">{has(id)?<RecoverableImage retryKey={imageReload} src={image(id)} alt={label}/>:<span>等待 {label}</span>}</div><span><b>{label}</b></span></button>)}<div className="trajectory-panel"><h3>模型预测轨迹 · 仅空间</h3><svg viewBox="0 0 320 260" role="img" aria-label="自车坐标系预测轨迹"><path d="M160 10V250M15 130H305" stroke="#354b60"/><polyline points={plot} fill="none" stroke="#5de2bc" strokeWidth="3"/><path d="M160 124l-6 12h12z" fill="white"/></svg><p>{prediction.length?`右向 / 前向距离（m）· 轴范围 ±${extent.toFixed(1)}m；点间时间尚未验证。`:`未绘制预测：${frame?.prediction?.reason??'未记录已校验坐标约定'}`}</p><p>转向 {frame?.control?.steer.toFixed(3)??'—'} · 油门 {frame?.control?.throttle.toFixed(2)??'—'} · 制动 {frame?.control?.brake.toFixed(2)??'—'}</p></div></div>
 {runId&&frame&&<RecordedTrajectory key={`${runId}:${frame.frame}`} runId={runId} frame={frame.frame} onSettled={onTrajectorySettled}/>}
 {prediction.length>0&&<p>规划显示参照：{frame?.prediction?.contract?.reference==='virtual_lidar'?'模型 LiDAR 原点，不是自车中心':'自车航向坐标原点'}。展示控制器保存的规划点，不代表最终控制采用该分支或完整网络预测时域。</p>}
 {focus&&<div className="sensor-modal" role="dialog" aria-modal="true" aria-label="传感器大图" onClick={()=>setFocus(null)}><button autoFocus onClick={()=>setFocus(null)}>关闭大图 ×</button><RecoverableImage retryKey={imageReload} src={image(focus)} alt={focus}/><p>点击任意位置关闭 · {focus}</p></div>}
 </section>;
}
