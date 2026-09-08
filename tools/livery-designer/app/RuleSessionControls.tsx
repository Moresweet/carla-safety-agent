"use client";
import {useEffect,useState} from "react";
const bridge="http://127.0.0.1:8765";
type Session={run_id?:string;kind?:string;state:string;error?:string};
const active=(s?:Session|null)=>!!s&&['preparing','running','stopping','recovering'].includes(s.state);
export default function RuleSessionControls({plan,capture,disabled}:{plan:Record<string,unknown>|null;capture:boolean;disabled:boolean}){
 const [session,setSession]=useState<Session|null>(null),[pending,setPending]=useState(false),[error,setError]=useState(''),[connected,setConnected]=useState(false);
 useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>;
  async function poll(){try{const r=await fetch(bridge+'/session/status');if(!r.ok)throw new Error('无法读取会话');const v=await r.json() as {session:Session};if(alive){setSession(v.session);setConnected(true)}}catch{if(alive)setConnected(false)}finally{if(alive)timer=setTimeout(poll,1000)}}
  void poll();return()=>{alive=false;clearTimeout(timer)};
 },[]);
 async function request(stop:boolean){setPending(true);setError('');try{
  const payload=stop?{run_id:session?.run_id}:{action:'rule-run',route:plan?.scenario_path,scenario_sha256:plan?.scenario_sha256,unified_capture:capture};
  const r=await fetch(bridge+(stop?'/scenario/stop':'/e2e/start'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const v=await r.json() as {error?:string};if(!r.ok)throw new Error(v.error||'请求失败');
  const current=await fetch(bridge+'/session/status');if(!current.ok)throw new Error('已提交请求，暂时无法读取状态，请勿重复启动');setSession((await current.json() as {session:Session}).session);
 }catch(e){setError(String(e));setConnected(false)}finally{setPending(false)}}
 return <section aria-label="规则场景任务" style={{fontSize:'14px'}}>
  <p>编译并检查右侧计划后启动规则驾驶；不调用端到端模型。</p>
  <button disabled={disabled||pending||!connected||active(session)||!plan?.scenario_path||!plan?.scenario_sha256} onClick={()=>void request(false)}>确认计划并启动规则场景</button>
  <button disabled={pending||!connected||session?.kind!=='rule-run'||!active(session)||session.state==='stopping'||session.state==='recovering'} onClick={()=>void request(true)}>停止规则场景并保存</button>
  <p role="status">{connected?(session?.kind==='rule-run'?`规则任务 ${session.run_id} · ${session.state}`:`当前会话：${session?.state}`):'正在连接会话；启动暂不可用'}</p>
  {(error||session?.error)&&<p role="alert">{error||session?.error}</p>}
 </section>
}
