"use client";
import {useEffect,useRef,useState} from 'react';
import {type TransformItem,type TransformReview} from './transformDraft';
type History={eligible:boolean;reason?:string;observed?:TransformReview;identity?:{episode:string;actor_id:number;type_id:string};revision:string|null;undo_count:number;redo_count:number;pending:null|{id:string;state:string;error?:string};entries:{id:string;applied:boolean;before:{location:{x:number;y:number;z:number};rotation:{yaw:number}};after:{location:{x:number;y:number;z:number};rotation:{yaw:number}}}[];error?:string};
export default function PositionHistory({item,busy,onAction}:{item:TransformItem;busy:boolean;onAction:(data:unknown)=>Promise<boolean>}){
 const [history,setHistory]=useState<History|null>(null),[error,setError]=useState(''),[connected,setConnected]=useState(false),[checked,setChecked]=useState(false),[revision,setRevision]=useState(0),[sending,setSending]=useState(false);
 const pending=useRef(false),identity=item.edit_identity;
 useEffect(()=>{if(!identity)return;let alive=true,loading=false;const load=async()=>{if(loading)return;loading=true;try{const r=await fetch('http://127.0.0.1:8765/objects/transform-history?actor_id='+identity.actor_id,{signal:AbortSignal.timeout(10000)});const v=await r.json() as History;if(!r.ok)throw Error(v.error??'位置历史读取失败');if(alive){setHistory(v);setConnected(true);setError('')}}catch(e){if(alive){setConnected(false);setError(String(e))}}finally{loading=false}};void load();const timer=setInterval(()=>void load(),1500);return()=>{alive=false;clearInterval(timer)}},[identity?.episode,identity?.actor_id,identity?.type_id,revision]);
 const matches=identity&&history?.identity&&identity.episode===history.identity.episode&&identity.actor_id===history.identity.actor_id&&identity.type_id===history.identity.type_id;
 const blocked=busy||sending||!connected||!matches||!history?.observed;
 async function act(action:'undo'|'redo'|'acknowledge'){
  const expected=history?.observed;if(blocked||pending.current||!expected||!history)return;
  pending.current=true;setSending(true);
  try{await onAction({action,expected,revision:history.revision,intent_id:history.pending?.id,confirmed:true});setChecked(false);setRevision(v=>v+1)}finally{pending.current=false;setSending(false)}
 }
 return <details className="position-history" aria-label="对象位置历史"><summary>位置撤销 / 重做 · {history?.eligible?`${history.undo_count} / ${history.redo_count}`:'当前对象'}</summary>
  <p>仅记录本工作台纳管对象在空闲世界中的新位置提交；只修改该对象，不恢复其他对象。绑定当前世界与运行时身份，旧内部接口及闭环编辑不自动纳入。</p>
  {history?.eligible?<>{history.pending?<><p role="alert">上次位置操作结果未确认，请检查当前对象与错误。不会自动重试。{history.pending.error}</p><label><input type="checkbox" checked={checked} disabled={blocked} onChange={e=>setChecked(e.target.checked)}/>我已检查当前对象，接受当前状态并归档旧历史；这不等于上次操作成功</label><button disabled={blocked||!checked} onClick={()=>void act('acknowledge')}>确认检查并开始空历史</button></>:<><button disabled={blocked||!history.undo_count} onClick={()=>void act('undo')}>撤销上次位置修改</button><button disabled={blocked||!history.redo_count} onClick={()=>void act('redo')}>重做位置修改</button></>}
   <p>外部位置变化会阻止旧历史重放；之后的新位置提交会另起历史链。撤销后再修改时，旧分支归档保留。下列显示游标附近最多10条。</p><ol>{history.entries.map(entry=><li key={entry.id}>{entry.applied?'已应用':'可重做'} · ({entry.before.location.x.toFixed(2)}, {entry.before.location.y.toFixed(2)}, {entry.before.location.z.toFixed(2)}) → ({entry.after.location.x.toFixed(2)}, {entry.after.location.y.toFixed(2)}, {entry.after.location.z.toFixed(2)}) · Yaw {entry.before.rotation.yaw.toFixed(1)}° → {entry.after.rotation.yaw.toFixed(1)}°</li>)}</ol>
  </>:<p>{history?.reason??'正在检查位置历史…'}</p>}
  {error&&<p role="alert">{error}</p>}
 </details>;
}
