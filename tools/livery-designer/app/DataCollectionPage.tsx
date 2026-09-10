"use client";
import {useCallback,useEffect,useState} from "react";
import SensorWorkbench,{CaptureFrame} from "./SensorWorkbench";
import SensorRigControls from "./SensorRigControls";
import ReplayEvents from "./ReplayEvents";
import ReplayQuality, {type TemporalQuality} from './ReplayQuality';
import CaptureQuality from './CaptureQuality';
import CaptureRecovery from './CaptureRecovery';
import CaptureExcerpt from './CaptureExcerpt';
const bridge="http://127.0.0.1:8765";
type Dataset={run_id:string;scenario_id:string;status:string;map:string;frame_count:number;replay?:boolean;skipped_frames?:number;manifest_path:string;excerpt?:{source_run_id:string};recovery?:{source_run_id:string;omitted_uncommitted_tail:string[]}};
type Entry={frame:number;timestamp:number};
export default function DataCollectionPage(){
 const [quality,setQuality]=useState<{runId:string;value:TemporalQuality}|null>(null);
 const [frameOwner,setFrameOwner]=useState('');
 const [datasets,setDatasets]=useState<Dataset[]>([]),[selected,setSelected]=useState(""),[index,setIndex]=useState<Entry[]>([]),[position,setPosition]=useState(0),[frame,setFrame]=useState<CaptureFrame|null>(null),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(1),[every,setEvery]=useState(5),[status,setStatus]=useState(""),[pending,setPending]=useState(false);
 const refresh=useCallback(async()=>{try{const r=await fetch(bridge+"/datasets");const v=await r.json() as {datasets:Dataset[]};setDatasets(v.datasets)}catch{setStatus("无法读取数据集")}},[]);
 useEffect(()=>{void refresh();const timer=setInterval(refresh,3000);return()=>clearInterval(timer)},[refresh]);
 useEffect(()=>{setPlaying(false);setIndex([]);setPosition(0);setFrame(null);setQuality(null);if(!selected)return;let active=true;fetch(bridge+"/datasets/index?run_id="+encodeURIComponent(selected)).then(async r=>{const v=await r.json() as {frames:Entry[];message?:string;error?:string;temporal_quality?:TemporalQuality};if(!r.ok)throw new Error(v.error||'无法读取回放索引');return v}).then(v=>{if(active){setQuality(v.temporal_quality?{runId:selected,value:v.temporal_quality}:null);setIndex(v.temporal_quality?.temporal_order_valid?v.frames:[]);setStatus(v.temporal_quality&&!v.temporal_quality.temporal_order_valid?'索引异常，不能安全回放':v.message??"")}}).catch(e=>{if(active)setStatus(String(e))});return()=>{active=false}},[selected]);
 useEffect(()=>{setFrame(null);setFrameOwner('');const entry=index[position];if(!selected||!entry||quality?.runId!==selected)return;let active=true;fetch(bridge+"/datasets/frame?run_id="+encodeURIComponent(selected)+"&frame="+entry.frame).then(async r=>{const v=await r.json() as CaptureFrame;if(!r.ok||v.frame!==entry.frame)throw new Error(v.error||'回放帧身份不匹配');return v}).then(v=>{if(active){setFrame(v);setFrameOwner(selected)}}).catch(e=>{if(active)setStatus(String(e))});return()=>{active=false}},[selected,index,position,quality]);
 useEffect(()=>{if(!playing||!index.length)return;if(position>=index.length-1){setPlaying(false);return}const delay=Math.max(40,1000*(index[position+1].timestamp-index[position].timestamp)/speed);const timer=setTimeout(()=>setPosition(v=>v+1),delay);return()=>clearTimeout(timer)},[playing,index,position,speed]);
 async function control(recording:boolean){setPending(true);try{const r=await fetch(bridge+"/collection/control",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({recording,every,max_frames:2000})});const v=await r.json() as {ok:boolean;error?:string};if(!r.ok||!v.ok)throw new Error(v.error);setStatus(recording?"采集请求已提交；等待采集进程在帧边界开始保存":"停止请求已提交；将在下一帧保存，或在评测退出时完成");setSelected("");void refresh()}catch(e){setStatus(String(e))}finally{setPending(false)}}
 const dataset=datasets.find(d=>d.run_id===selected);
 const visibleFrame=quality?.runId===selected&&frameOwner===selected&&frame?.frame===index[position]?.frame?frame:null;
 return <section className="collection-workspace"><SensorRigControls every={every}/><header className="collection-controls"><div><h2>数据采集与回放</h2><p>保存独立传感器或模型原始输入、标定、深度米值、XYZI 点云、BEV 与自车状态。模型预测仅在模型提供时记录。</p></div><label>每 N 帧保存<input aria-label="采样间隔" type="number" min={1} max={100} value={every} onChange={e=>setEvery(+e.target.value)}/></label><button disabled={pending} onClick={()=>control(true)}>开始录制</button><button disabled={pending} onClick={()=>control(false)}>停止并保存</button></header><p role="status">{status}</p><div className="collection-selection"><label>查看模式 / 数据集<select aria-label="数据集" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">实时传感器</option>{datasets.map(d=><option key={d.run_id} value={d.run_id}>{d.scenario_id} · {d.frame_count} 帧 · {d.status} · {d.run_id}</option>)}</select></label><button onClick={()=>void refresh()}>刷新清单</button></div>
 {selected&&<section className="replay-controls"><button disabled={!index.length||quality?.runId!==selected} onClick={()=>{if(position>=index.length-1)setPosition(0);setPlaying(v=>!v)}}>{playing?"暂停":"播放"}</button><button disabled={!position} onClick={()=>{setPlaying(false);setPosition(v=>v-1)}}>上一帧</button><button disabled={position>=index.length-1} onClick={()=>{setPlaying(false);setPosition(v=>v+1)}}>下一帧</button><input aria-label="回放时间轴" type="range" min={0} max={Math.max(0,index.length-1)} value={position} onChange={e=>{setPlaying(false);setPosition(+e.target.value)}}/><select aria-label="播放速度" value={speed} onChange={e=>setSpeed(+e.target.value)}>{[.25,.5,1,2,4].map(s=><option key={s} value={s}>{s}×</option>)}</select><span>{index.length?position+1:0} / {index.length} 帧</span><p>{dataset?.manifest_path} · 跳过不同步帧 {dataset?.skipped_frames??0}</p>{visibleFrame&&<a href={bridge+"/datasets/file?run_id="+encodeURIComponent(selected)+"&frame="+visibleFrame.frame+"&name="+encodeURIComponent(visibleFrame.input_archive??"model_input.npz")} download>下载当前帧原始输入 NPZ</a>}</section>}
 {dataset?.recovery&&<p role="note" aria-label="中断采集恢复提示">这是中断采集的恢复副本，不是完整录制。来源：{dataset.recovery.source_run_id}；排除 {dataset.recovery.omitted_uncommitted_tail.length} 个未提交尾帧目录，原始目录保留。可回放已验证样本，不能据此认定任务正常完成；暂不允许自动加入训练划分。</p>}
 {selected&&<ReplayQuality quality={quality?.runId===selected?quality.value:null}/>}
 {selected&&<CaptureQuality key={'quality:'+selected} runId={selected}/>}
 {dataset?.excerpt&&<p role="note" aria-label="诊断片段提示">这是诊断片段，不是完整录制或自动批准的训练数据。来源：{dataset.excerpt.source_run_id}。原任务的时间及跳帧计数保留，不代表本片段的统计。</p>}
 {dataset&&['saved','saved_limit','saved_recovered'].includes(dataset.status)&&<CaptureExcerpt key={'excerpt:'+selected} runId={selected} frame={visibleFrame?.frame??null} onOpen={id=>{setPlaying(false);void refresh();setSelected(id)}}/>}
 {dataset&&['recording','saved_cleanup_error'].includes(dataset.status)&&<CaptureRecovery key={'recovery:'+selected} runId={selected} onRecovered={id=>{void refresh();setSelected(id)}}/>}
 {selected&&<ReplayEvents key={'events:'+selected} runId={selected} onSeek={target=>{
  const next=index.findIndex(entry=>entry.frame===target);
  if(next<0){setStatus('该片段不在当前回放索引中，请重新选择数据集');return}
  setPlaying(false);if(next!==position)setFrame(null);setPosition(next);
 }}/>}
 <SensorWorkbench recorded={visibleFrame} runId={selected||undefined}/>
 </section>
}
