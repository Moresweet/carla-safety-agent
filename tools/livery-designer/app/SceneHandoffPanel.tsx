"use client";
import {useEffect,useState} from 'react';
type Review={review_token:string;source_map:string;target_map:string;source_episode:string;target_object_count:number;saved_user_object_count:number};
type Job={state:string;request_id?:string;phase?:string;source_map?:string;target_map?:string;error?:string;backup?:{scene_id:string;version:string}};
const bridge='http://127.0.0.1:8765';
export default function SceneHandoffPanel({sceneId,version,onSelect}:{sceneId:string;version?:string;onSelect:(id:string)=>void}){
 const [review,setReview]=useState<Review|null>(null),[job,setJob]=useState<Job|null>(null);
 const [confirmed,setConfirmed]=useState(false),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [connected,setConnected]=useState(false);
 useEffect(()=>{
  let alive=true;let timer:ReturnType<typeof setTimeout>;
  async function poll(){try{const r=await fetch(bridge+'/scenes/handoff'),v=await r.json() as Job;if(!r.ok)throw Error(v.error??'切图状态不可用');if(alive){setJob(v);setConnected(true)}}catch(e){if(alive){setConnected(false);setError(String(e))}}finally{if(alive)timer=setTimeout(poll,1500)}}
  void poll();return()=>{alive=false;clearTimeout(timer)};
 },[]);
 const blocked=busy||!connected||job?.state==='running'||job?.state==='needs_attention';
 async function call(action:'preview'|'confirm'|'acknowledge'){
  if(busy)return;
  if(action==='confirm'&&(!review||!confirmed))return;
  if(action==='acknowledge'&&(!job?.request_id||!ack))return;
  setBusy(true);setError('');
  const body=action==='preview'?{scene_id:sceneId,version}:action==='confirm'?{review_token:review!.review_token,confirmed:true}:{request_id:job!.request_id,confirmed:true};
  if(action!=='preview'){setReview(null);setConfirmed(false);setAck(false)}
  try{const r=await fetch(bridge+'/scenes/handoff/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await r.json() as Review & Job;if(!r.ok)throw Error(v.error??'跨地图操作未成功');if(action==='preview'){setReview(v);setConfirmed(false)}else setJob(v)}
  catch(e){setError(String(e)+'。请先查看当前切图记录，不要重复确认。')}finally{setBusy(false)}
 }
 return <section className="scene-handoff" aria-label="跨地图场景恢复" style={{border:'1px solid #855b35',padding:16,margin:'16px 0',borderRadius:10}}>
  <h3>跨地图恢复 · 单独确认</h3>
  <p>换图会销毁当前地图的运行时对象。先保存纳管对象、纹理、天气和视角备份，不是完整仿真快照；无关车辆、行人、道具、控制器、传感器或活动任务会阻止操作。同地图请使用上方普通恢复。</p>
  <button disabled={blocked||!sceneId||!version} onClick={()=>void call('preview')}>预检并预览跨地图恢复</button>
  {review&&<div><p>{review.source_map} → {review.target_map} · 来源 episode {review.source_episode}</p><p>备份 {review.saved_user_object_count} 个用户对象，目标恢复 {review.target_object_count} 个对象。确认有效期约 120 秒；目标地图中的材质和生成资产最终兼容性仍须加载后验证。</p>
   <label><input aria-label="确认销毁当前世界并恢复目标地图" type="checkbox" checked={confirmed} disabled={blocked} onChange={e=>setConfirmed(e.target.checked)}/>我确认销毁当前运行世界，先保存纳管状态备份，再换图恢复；失败时保留记录，不自动回切或重试</label>
   <button disabled={blocked||!confirmed} onClick={()=>void call('confirm')}>确认备份、换图并恢复</button>
  </div>}
  {job&&job.state!=='idle'&&<div className="handoff-record"><h4>当前 / 最近一次切图记录（与待确认预览分开）</h4><p role="status">切图状态：{job.state} · {job.phase} · {job.request_id}</p><p>{job.source_map} → {job.target_map}</p>{job.error&&<p role="alert">{job.error}</p>}
   {job.backup&&<><p style={{overflowWrap:'anywhere'}}>备份场景 {job.backup.scene_id} · 版本 {job.backup.version}</p><button disabled={busy} onClick={()=>onSelect(job.backup!.scene_id)}>选择备份场景（不自动恢复）</button></>}
   {job.state==='restored'&&<p>目标纳管场景已恢复，原运行世界已被替换。可刷新运行检查后继续编辑；备份保留。</p>}
   {job.state==='needs_attention'&&<><p>切图结果需要检查，普通编辑和模型启动已阻止。检查原生窗口、错误和备份后，才能接受当前世界并解除阻止；这不会补做恢复或删除对象。</p><label><input aria-label="接受当前世界并解除切图阻止" type="checkbox" checked={ack} disabled={busy||!connected} onChange={e=>setAck(e.target.checked)}/>我已检查当前世界与备份，接受当前状态，保留故障记录并解除本次切图阻止</label><button disabled={busy||!connected||!ack} onClick={()=>void call('acknowledge')}>确认接受当前世界（不等于恢复成功）</button></>}
  </div>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
