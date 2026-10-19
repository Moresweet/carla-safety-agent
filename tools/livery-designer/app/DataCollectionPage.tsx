"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {serialPoll} from './serialPoll';
import {searchDatasets,datasetModelLabel} from './datasetSearch';
import SensorWorkbench,{CaptureFrame} from "./SensorWorkbench";
import SensorRigControls from "./SensorRigControls";
import ReplayEvents from "./ReplayEvents";
import ReplayQuality, {type TemporalQuality} from './ReplayQuality';
import CaptureQuality from './CaptureQuality';
import CaptureRecovery from './CaptureRecovery';
import CaptureRetention from './CaptureRetention';
import CaptureExcerpt from './CaptureExcerpt';
import {readWithRetry} from './readWithRetry';
import {captureOutcome,captureQuotaSummary} from './captureOutcome';
import CaptureStorage from './CaptureStorage';
import RuntimeStorage from './RuntimeStorage';
import SplitRegistration from './SplitRegistration';
import {executionSummaryText} from './executionSummary';
import CaptureArchive from './CaptureArchive';
import {setRecording} from './recordingControl';
const bridge="http://127.0.0.1:8765";
type Dataset={run_id:string;model?:unknown;family?:unknown;scenario_id:string;status:string;map:string;frame_count:number;execution_summary?:unknown;error?:unknown;stop_reason?:unknown;capture_quota_policy?:unknown;replay?:boolean;skipped_frames?:number;manifest_path:string;excerpt?:{source_run_id:string};recovery?:{source_run_id:string;omitted_uncommitted_tail:string[]}};
type Entry={frame:number;timestamp:number};
export default function DataCollectionPage(){
 const [query,setQuery]=useState('');
 const [storageRevision,setStorageRevision]=useState(0);
 const [trajectoryReady,setTrajectoryReady]=useState<{runId:string;frame:number;ok:boolean|null}|null>(null);
 const onTrajectorySettled=useCallback((runId:string,frame:number,ok:boolean|null)=>{setTrajectoryReady({runId,frame,ok});if(ok===false)setPlaying(false)},[]);
 const [quality,setQuality]=useState<{runId:string;value:TemporalQuality}|null>(null);
 const [frameOwner,setFrameOwner]=useState('');
 const [reload,setReload]=useState(0),[readStatus,setReadStatus]=useState(''),[readFailed,setReadFailed]=useState(false);
 const [datasets,setDatasets]=useState<Dataset[]>([]),[selected,setSelected]=useState(""),[index,setIndex]=useState<Entry[]>([]),[position,setPosition]=useState(0),[frame,setFrame]=useState<CaptureFrame|null>(null),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(1),[every,setEvery]=useState(5),[status,setStatus]=useState(""),[pending,setPending]=useState(false);
 const datasetPoll=useRef<ReturnType<typeof serialPoll>|null>(null);
 const recordingLock=useRef(false);
 const [datasetReadError,setDatasetReadError]=useState('');
 const refresh=useCallback(()=>datasetPoll.current?.refresh(),[]);
 useEffect(()=>{
  const poll=serialPoll(async signal=>{
   try{
    const value=await readWithRetry<{datasets:Dataset[]}>(bridge+'/datasets',{signal,attempts:1});
    if(!Array.isArray(value.datasets))throw Error('清单响应不完整');
    if(!signal.aborted){setDatasets(value.datasets);setDatasetReadError('');}
   }catch(error){if(!signal.aborted)setDatasetReadError('无法读取数据集：'+String(error))}
  },3000);
  datasetPoll.current=poll;void poll.refresh();
  return()=>{poll.stop();if(datasetPoll.current===poll)datasetPoll.current=null};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();
  setPlaying(false);setTrajectoryReady(null);setIndex([]);setPosition(0);setFrame(null);setQuality(null);setReadFailed(false);setReadStatus('');
  if(!selected)return;
  setReadStatus('正在读取回放索引…');
  void readWithRetry<{frames:Entry[];message?:string;temporal_quality?:TemporalQuality}>(bridge+'/datasets/index?run_id='+encodeURIComponent(selected),{
   signal:controller.signal,onRetry:n=>setReadStatus(`索引连接暂不可用，正在重试 ${n}/3…`)
  }).then(v=>{if(!controller.signal.aborted){
   if(!v.temporal_quality?.temporal_order_valid||!Array.isArray(v.frames))throw Error('索引缺失或异常，不能安全回放');
   setQuality({runId:selected,value:v.temporal_quality});setIndex(v.frames);setReadStatus(v.message??'');
  }}).catch(e=>{if(!controller.signal.aborted){setReadFailed(true);setReadStatus('回放索引读取失败，已停止自动重试：'+String(e))}});
  return()=>controller.abort();
 },[selected,reload]);
 useEffect(()=>{
  setFrame(null);setFrameOwner('');const entry=index[position];
  if(!selected||!entry||quality?.runId!==selected)return;
  const controller=new AbortController();setReadFailed(false);setReadStatus('正在读取回放帧…');
  void readWithRetry<CaptureFrame>(bridge+'/datasets/frame?run_id='+encodeURIComponent(selected)+'&frame='+entry.frame,{
   signal:controller.signal,onRetry:n=>setReadStatus(`帧数据连接暂不可用，正在重试 ${n}/3…`)
  }).then(v=>{if(!controller.signal.aborted){
   if(v.frame!==entry.frame||v.error)throw Error(v.error||'回放帧身份不匹配');
   setFrame(v);setFrameOwner(selected);setReadStatus('');
  }}).catch(e=>{if(!controller.signal.aborted){setPlaying(false);setReadFailed(true);setReadStatus('回放帧读取失败，已暂停：'+String(e))}});
  return()=>controller.abort();
 },[selected,index,position,quality]);
 useEffect(()=>{if(!playing||!index.length||frameOwner!==selected||frame?.frame!==index[position]?.frame||!trajectoryReady?.ok||trajectoryReady.runId!==selected||trajectoryReady.frame!==frame?.frame)return;if(position>=index.length-1){setPlaying(false);return}const delay=Math.max(40,1000*(index[position+1].timestamp-index[position].timestamp)/speed);const timer=setTimeout(()=>setPosition(v=>v+1),delay);return()=>clearTimeout(timer)},[playing,index,position,speed,frame,frameOwner,selected,trajectoryReady]);
 async function control(recording:boolean){if(recordingLock.current)return;recordingLock.current=true;setPending(true);try{await setRecording(recording,every);setStatus(recording?"采集请求已提交；等待采集进程在帧边界开始保存":"停止请求已提交；将在下一帧保存，或在评测退出时完成");setSelected("");void refresh()}catch(e){setStatus(String(e))}finally{recordingLock.current=false;setPending(false)}}
 const dataset=datasets.find(d=>d.run_id===selected);
 const visibleFrame=quality?.runId===selected&&frameOwner===selected&&frame?.frame===index[position]?.frame?frame:null;
 const search=searchDatasets(datasets,query,selected);
 return <section className="collection-workspace"><SensorRigControls every={every}/><header className="collection-controls"><div><h2>数据采集与回放</h2><p>保存独立传感器或模型原始输入、标定、深度米值、XYZI 点云、BEV 与自车状态。模型预测仅在模型提供时记录。</p></div><label>每 N 帧保存<input aria-label="采样间隔" type="number" min={1} max={100} value={every} onChange={e=>setEvery(+e.target.value)}/></label><button disabled={pending} onClick={()=>control(true)}>开始录制</button><button disabled={pending} onClick={()=>control(false)}>停止并保存</button></header><p role="status">{status}</p><div className="collection-selection"><label>搜索录制<input aria-label="搜索录制" value={query} onChange={e=>setQuery(e.target.value)} placeholder="名称、模型、运行 ID、状态、地图"/></label><span role="status">匹配 {search.matches.length} / {datasets.length} 份{search.retained?"；当前回放不匹配，仍保留选中":""}</span><label>查看模式 / 数据集<select aria-label="数据集" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">实时传感器</option>{search.options.map(d=><option key={d.run_id} value={d.run_id}>{d.scenario_id} · {datasetModelLabel(d)} · {d.frame_count} 帧 · {d.status} · {d.run_id}</option>)}</select></label><button onClick={()=>void refresh()}>刷新清单</button></div>
 {selected&&<section className="replay-controls"><button disabled={!index.length||quality?.runId!==selected} onClick={()=>{if(position>=index.length-1)setPosition(0);setPlaying(v=>!v)}}>{playing?"暂停":"播放"}</button><button disabled={!position} onClick={()=>{setPlaying(false);setPosition(v=>v-1)}}>上一帧</button><button disabled={position>=index.length-1} onClick={()=>{setPlaying(false);setPosition(v=>v+1)}}>下一帧</button><input aria-label="回放时间轴" type="range" min={0} max={Math.max(0,index.length-1)} value={position} onChange={e=>{setPlaying(false);setPosition(+e.target.value)}}/><select aria-label="播放速度" value={speed} onChange={e=>setSpeed(+e.target.value)}>{[.25,.5,1,2,4].map(s=><option key={s} value={s}>{s}×</option>)}</select><span>{index.length?position+1:0} / {index.length} 帧</span><p>{dataset?.manifest_path} · 跳过不同步帧 {dataset?.skipped_frames??0}</p>{visibleFrame&&<a href={bridge+"/datasets/file?run_id="+encodeURIComponent(selected)+"&frame="+visibleFrame.frame+"&name="+encodeURIComponent(visibleFrame.input_archive??"model_input.npz")} download>下载当前帧原始输入 NPZ</a>}</section>}
 {dataset&&captureOutcome(dataset)&&<p role="alert" aria-label="录制完成状态提示">{captureOutcome(dataset)}</p>}
 {dataset&&<p aria-label="对应执行记录">{executionSummaryText(dataset.execution_summary)}</p>}
 {dataset&&<p aria-label="录制配额策略">{captureQuotaSummary(dataset.capture_quota_policy)}</p>}
 {dataset?.recovery&&<p role="note" aria-label="中断采集恢复提示">这是中断采集的恢复副本，不是完整录制。来源：{dataset.recovery.source_run_id}；排除 {dataset.recovery.omitted_uncommitted_tail.length} 个未提交尾帧目录，原始目录保留。可回放已验证样本，不能据此认定任务正常完成；暂不允许自动加入训练划分。</p>}
 {selected&&<div aria-label="回放连接状态"><p role={readFailed?'alert':'status'}>{readStatus}</p>{readFailed&&<button onClick={()=>{setPlaying(false);setReload(v=>v+1)}}>重新读取回放</button>}</div>}
 {datasetReadError&&<p role="alert">{datasetReadError}</p>}
 {selected&&<p>自动播放等待当前帧轨迹读取完成；读取失败会暂停。实际速度可能低于所选倍速，不跳过未显示的轨迹。</p>}
 <SensorWorkbench recorded={visibleFrame} runId={selected||undefined} onTrajectorySettled={onTrajectorySettled}/>
 <details className="collection-management"><summary>数据管理与诊断 · 存储、归档、质量检查、训练划分</summary>
 <SplitRegistration onWriteAttempt={()=>setStorageRevision(value=>value+1)}/>
 <CaptureStorage key={storageRevision} invalidated={storageRevision>0} onOpen={id=>{setPlaying(false);setSelected(id)}}/>
 <RuntimeStorage/>
 {selected&&<ReplayQuality quality={quality?.runId===selected?quality.value:null}/>}
 {selected&&<CaptureQuality key={'quality:'+selected} runId={selected}/>}
 {selected&&<CaptureRetention key={'retention:'+selected} runId={selected} onWriteAttempt={()=>setStorageRevision(value=>value+1)}/>}
 {selected&&<CaptureArchive key={'archive:'+selected} runId={selected}/>}
 {dataset?.excerpt&&<p role="note" aria-label="诊断片段提示">这是诊断片段，不是完整录制或自动批准的训练数据。来源：{dataset.excerpt.source_run_id}。原任务的时间及跳帧计数保留，不代表本片段的统计。</p>}
 {dataset&&['saved','saved_limit','saved_recovered'].includes(dataset.status)&&<CaptureExcerpt key={'excerpt:'+selected} runId={selected} frame={visibleFrame?.frame??null} onOpen={id=>{setPlaying(false);void refresh();setSelected(id)}}/>}
 {dataset&&['recording','saved_cleanup_error','saved_capture_error'].includes(dataset.status)&&<CaptureRecovery key={'recovery:'+selected} runId={selected} onRecovered={id=>{void refresh();setSelected(id)}}/>}
 {selected&&<ReplayEvents key={'events:'+selected} runId={selected} onSeek={target=>{
  const next=index.findIndex(entry=>entry.frame===target);
  if(next<0){setStatus('该片段不在当前回放索引中，请重新选择数据集');return}
  setPlaying(false);if(next!==position)setFrame(null);setPosition(next);
 }}/>}
 </details>
 </section>
}
