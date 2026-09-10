"use client";
import {useEffect,useRef,useState} from 'react';
type Revision=Record<string,unknown>&{scenario_path:string;scenario_sha256:string;parent_sha256:string;changes:{path:string;before:unknown;after:unknown}[]};
export default function PlanRevisionPanel({plan,disabled,onPending,onAdopt}:{plan:Record<string,unknown>|null;disabled:boolean;onPending:(value:boolean)=>void;onAdopt:(value:Record<string,unknown>)=>void}){
 const [text,setText]=useState('自车速度改为8 m/s；雨量改为30%；其余保持不变'),[candidate,setCandidate]=useState<Revision|null>(null),[busy,setBusy]=useState(false),[reviewing,setReviewing]=useState(false),[error,setError]=useState('');
 const request=useRef<AbortController|null>(null);
 useEffect(()=>()=>request.current?.abort(),[]);
 if(typeof plan?.scenario_path!=='string'||typeof plan?.scenario_sha256!=='string')return null;
 async function preview(){
  if(busy||disabled)return;
  request.current?.abort();const active=new AbortController();request.current=active;
  setBusy(true);setReviewing(true);onPending(true);setError('');setCandidate(null);
  try{const r=await fetch('http://127.0.0.1:8765/scenario/revise',{method:'POST',headers:{'Content-Type':'application/json'},signal:active.signal,body:JSON.stringify({scenario_path:plan!.scenario_path,scenario_sha256:plan!.scenario_sha256,instruction:text})});const v=await r.json() as Revision;
   if(!r.ok)throw Error(String(v.error??'计划修订失败'));
   if(!Array.isArray(v.changes)||v.parent_sha256!==plan!.scenario_sha256)throw Error('修订响应与父计划不一致');
   if(request.current===active)setCandidate(v);
  }catch(e){if(!active.signal.aborted)setError(String(e))}finally{if(request.current===active)setBusy(false)}
 }
 function cancel(){request.current?.abort();request.current=null;setBusy(false);setReviewing(false);setCandidate(null);setError('');onPending(false)}
 return <section className="plan-revision" aria-label="自然语言局部修改计划">
  <h3>局部修改已编译计划</h3><p>只修改明确列出的字段，原计划保留，不操作当前世界。预览后先采纳新版，再单独确认运行。</p>
  <textarea aria-label="计划局部修改指令" value={text} maxLength={1000} rows={3} disabled={disabled||busy} onChange={e=>{setText(e.target.value);setCandidate(null)}}/>
  <p>支持：自车/对手速度（m/s、km/h）、触发距离（米）、运行时长（秒）、雨量、雾浓度、晴天/大雨/小雨、白天/夜间、Town地图、随机种子、已有金属管组数量。请用逗号或分号分隔；未识别的整句会拒绝。</p>
  <button disabled={disabled||busy||!text.trim()} onClick={()=>void preview()}>预览局部修改</button>
  <button disabled={disabled||!reviewing} onClick={cancel}>取消修订，保留原计划</button>
  {reviewing&&<p role="status">{busy?'正在创建独立修订预览…':'执行入口暂时锁定：请采纳修订或取消。'}</p>}
  {error&&<p role="alert">{error} 原计划未替换。</p>}
  {candidate&&<><table><thead><tr><th>字段</th><th>原值</th><th>新值</th></tr></thead><tbody>{candidate.changes.map(change=><tr key={change.path}><td>{change.path}</td><td>{JSON.stringify(change.before)}</td><td>{JSON.stringify(change.after)}</td></tr>)}</tbody></table>
   <p>父计划 {candidate.parent_sha256.slice(0,12)} → 新计划 {candidate.scenario_sha256.slice(0,12)}。原始描述仅用于溯源，执行以新JSON为准；地图安装与模型兼容性仍需启动检查。</p>
   <button disabled={disabled||busy} onClick={()=>{onPending(false);onAdopt(candidate)}}>采纳修订计划（不运行）</button>
  </>}
 </section>;
}
