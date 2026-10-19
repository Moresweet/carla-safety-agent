"use client";
import {useEffect,useState} from 'react';
import {usableProjectedTrack,type ProjectedTrack} from './projectedTrack';
type Point={xyz_m:number[];dt_s:number|null};
type NavigationDiagnostic={state:string;position_delta_m?:number;heading_delta_rad?:number};
type Track={frame:number;history:Point[];future:Point[];prediction?:{state:string;points:Point[];reason?:string;map_projected?:ProjectedTrack;reference_warning?:string|null;navigation_diagnostic?:NavigationDiagnostic|null;contract?:{reference:string};reference_history?:Point[];reference_future?:Point[];source_frame?:number;prediction_age_s?:number;reused?:boolean};error?:string};
export default function RecordedTrajectory({runId,frame,onSettled}:{runId:string;frame:number;onSettled?:(runId:string,frame:number,ok:boolean|null)=>void}){
 const [attempt,setAttempt]=useState(0);
 const [track,setTrack]=useState<Track|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setTrack(null);setError('');onSettled?.(runId,frame,null);
 void fetch(`http://127.0.0.1:8765/datasets/trajectory?${new URLSearchParams({run_id:runId,frame:String(frame)})}`,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])})
 .then(async response=>{const value=await response.json() as Track;if(!response.ok)throw new Error(value.error??'轨迹不可用');if(value.frame!==frame||!Array.isArray(value.history)||!Array.isArray(value.future))throw new Error('轨迹响应与当前帧不一致');return value})
 .then(value=>{if(!controller.signal.aborted){setTrack(value);onSettled?.(runId,frame,true)}})
 .catch(e=>{if(!controller.signal.aborted){setError(String(e));onSettled?.(runId,frame,false)}});return()=>controller.abort();
 },[runId,frame,onSettled,attempt]);
 const projected=track?.prediction?.map_projected;
 const mapped=track?.prediction?.state==='available'&&usableProjectedTrack(projected,track.prediction.source_frame)?projected:null;
 const predicted=track?.prediction?.state==='available'?(mapped?.points??track.prediction.points):[];
 const navigation=track?.prediction?.navigation_diagnostic;
 const lidarReference=!!predicted.length&&track?.prediction?.contract?.reference==='virtual_lidar';
 const history=(lidarReference?track?.prediction?.reference_history:track?.history)??[];
 const future=(lidarReference?track?.prediction?.reference_future:track?.future)??[];
 const points=[...history,...future,...predicted];
 const extent=Math.max(10,...points.flatMap(p=>p.xyz_m.slice(0,2).map(Math.abs)))*1.1;
 const plot=(ps:Point[])=>ps.map(p=>`${160+p.xyz_m[1]*140/extent},${160-p.xyz_m[0]*140/extent}`).join(' ');
 const current=history.slice(-1);
 return <section className="trajectory-panel" aria-label="真实轨迹与预测对比" data-frame={track?.frame}><h3>记录轨迹与模型预测 · 真实轨迹前后 5 秒</h3>
 {error?<><p role="alert">轨迹读取失败，播放已暂停：{error}</p><button onClick={()=>setAttempt(v=>v+1)}>重试轨迹读取</button></>:!track?<p role="status">读取真实轨迹…</p>:<>
 <svg viewBox="0 0 320 320" role="img" aria-label="真实历史与未来轨迹，前方朝上，右方朝右">
 <path d="M160 10V310M10 160H310" stroke="#354b60"/>
 <polyline points={plot(history)} fill="none" stroke="#69b8ff" strokeWidth="3"/>
 <polyline points={plot([...current,...future])} fill="none" stroke="#ffdc48" strokeWidth="3" strokeDasharray="6 3"/>
 <polyline points={plot(predicted)} fill="none" stroke="#5de2bc" strokeWidth="2" strokeDasharray="2 5"/>
 {predicted.map((point,i)=><circle key={i} cx={160+point.xyz_m[1]*140/extent} cy={160-point.xyz_m[0]*140/extent} r="3" fill="#5de2bc"/>) }
 <circle cx="160" cy="160" r="4" fill="white"/>
 </svg><p>蓝色实线：历史 {track.history.length} 点 · 黄色虚线：未来 {track.future.length} 点</p>
 <p>当前自车坐标，前方朝上、右方朝右 · 轴范围 ±{extent.toFixed(1)} m</p>
 <p>{lidarReference?'双方轨迹使用 LiDAR 参考点（车体偏移 −0.39, 0, 1.84m），不是车中心轨迹；白点为当前车体原点。':'轨迹参考点为自车原点。'}</p>
 <p>来自录制位姿，不是模型预测；不插值，录制边界不补造轨迹。</p></>}
 {track&&<p>{predicted.length?`绿色点线：模型规划分支预测 ${predicted.length} 点，仅作空间对照，不代表最终控制必然采用。预测点的时间间隔尚未验证，不逐点配对真值，不计算 ADE/FDE。`:`不叠加模型预测：${track.prediction?.reason??'缺少明确的预测坐标约定'}`}</p>}
 {predicted.length>0&&<p>预测生成帧 {track?.prediction?.source_frame} · {track?.prediction?.reused?'复用已有预测':'本帧生成'} · 已过去 {track?.prediction?.prediction_age_s?.toFixed(3)} s；依据生成时位姿变换到当前自车坐标。</p>}
 {mapped&&<p aria-label="归档地图投影">已使用录制归档地图逐点转换预测轨迹；投影后导航原点与真值相差 {mapped.navigation_position_delta_m.toFixed(3)} m。高度采用预测生成时自车高度，不代表道路高程；这不是 ADE/FDE。</p>}
 {predicted.length>0&&projected&&!mapped&&<p role="note">归档地图转换不可用：{projected.reason??'投影结果未通过校验'}。当前绿线仅为原有规则参照，不代表已完成地图投影。</p>}
 {predicted.length>0&&!mapped&&track?.prediction?.reference_warning&&<p role="note">{track.prediction.reference_warning}</p>}
 {predicted.length>0&&!mapped&&navigation&&<p aria-label="导航参考点诊断">{navigation.state==='available'&&Number.isFinite(navigation.position_delta_m)&&Number.isFinite(navigation.heading_delta_rad)
 ?`预测生成时原版导航坐标与真值坐标的数值差为 ${navigation.position_delta_m!.toFixed(3)} m，航向差 ${(navigation.heading_delta_rad!*180/Math.PI).toFixed(3)}°。尚未统一地图投影，不能将此数值差解释为实际定位误差或预测轨迹误差。`
 :'该帧没有有效的导航位姿观测，无法量化参考点偏差；不按零偏差处理。'}</p>}
 </section>;
}
