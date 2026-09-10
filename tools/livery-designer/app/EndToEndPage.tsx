"use client";
import {useEffect,useRef,useState} from "react";
import SensorWorkbench from "./SensorWorkbench";
import BatchPanel from "./BatchPanel";
import {supportsGeneratedScene} from './generatedModels';

const bridge="http://127.0.0.1:8765";
type Algorithm={id:string;name:string;framework:string;checkpoint:string;sensors:string;enabled:boolean;status:string};
type Route={name:string;path:string;relative:string;count:number};
type PresetRoute={id:string;town:string;scenarios:string[]};
type Collection={id:string;name:string;path:string;route_count:number;routes:PresetRoute[]};
type Report={algorithm:string;routes:number;driving_score:number;route_completion:number;infractions:Record<string,number>};
type Telemetry={frame:number;model:string;inputs:{camera_ids:string[];speed_mps:number;gps:number[];acceleration_mps2:number[];angular_velocity_radps:number[];route_command:number;synchronized:boolean};outputs:{trajectory_ego_m:number[][];controller:{steer:number;throttle:number;brake:number;desired_speed_mps:number;aim_point_ego_m:number[];route_target_ego_m:number[]}}};
type Status={algorithms:Algorithm[];job:{state:string;kind:string|null;returncode:number|null;algorithm?:string;collection?:string;route_id?:string;route?:string};session?:{run_id:string|null;state:string};routes:Route[];log:string};

export default function EndToEndPage(){
 const requestLock=useRef(false);
 const [pending,setPending]=useState(false),[error,setError]=useState("");
 const [status,setStatus]=useState<Status|null>(null),[telemetry,setTelemetry]=useState<Telemetry|null>(null);
 const [collections,setCollections]=useState<Collection[]>([]),[reports,setReports]=useState<Report[]>([]);
 const [algorithm,setAlgorithm]=useState("uniad-tiny"),[route,setRoute]=useState(""),[collection,setCollection]=useState(""),[preset,setPreset]=useState("");
 const refresh=()=>{fetch(`${bridge}/e2e/status`).then(r=>r.json() as Promise<Status>).then(v=>{setStatus(v);setRoute(x=>x||v.routes[0]?.path||"")}).catch(()=>{});fetch(`${bridge}/e2e/telemetry`).then(r=>r.json() as Promise<{telemetry:Telemetry|null}>).then(v=>setTelemetry(v.telemetry)).catch(()=>{})};
 useEffect(()=>{refresh();Promise.all([fetch(`${bridge}/e2e/benchmark/catalog`).then(r=>r.json() as Promise<{routes:{collections:Collection[]}}>),fetch(`${bridge}/e2e/benchmark/report`).then(r=>r.json() as Promise<{report:{reports:Report[]}}>)]).then(([c,r])=>{setCollections(c.routes.collections);setCollection(c.routes.collections[0]?.path||"");setPreset(c.routes.collections[0]?.routes[0]?.id||"");setReports(r.report.reports)}).catch(()=>{});const timer=setInterval(refresh,1000);return()=>clearInterval(timer)},[]);
 const selectedCollection=collections.find(v=>v.path===collection),selectedAlgorithm=status?.algorithms.find(v=>v.id===algorithm),running=pending||["running","stopping"].includes(status?.job.state||"");
 const selectedPreset=selectedCollection?.routes.find(v=>v.id===preset);
 useEffect(()=>{if(status?.job.state==="running"||status?.job.state==="stopping"){
  if(status.job.algorithm)setAlgorithm(status.job.algorithm);
  if(status.job.route)setRoute(status.job.route);
  if(status.job.collection)setCollection(status.job.collection);
  if(status.job.route_id)setPreset(status.job.route_id);
 }},[status?.job.state,status?.job.algorithm,status?.job.collection,status?.job.route_id,status?.job.route]);
 async function request(path:string,payload:Record<string,string>){
  if(requestLock.current)return;
  requestLock.current=true;setPending(true);setError("");
  try{
   const response=await fetch(`${bridge}${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
   const result=await response.json() as {ok?:boolean;error?:string};
   if(!response.ok||!result.ok)throw new Error(result.error||`HTTP ${response.status}`);
   const latest=await fetch(`${bridge}/e2e/status`);
   if(!latest.ok)throw new Error("无法获取评测状态，请检查服务日志");
   setStatus(await latest.json());
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{requestLock.current=false;setPending(false)}
 }
 async function start(action:string){await request("/e2e/start",action==="preset-run"?{action,algorithm,collection,route_id:preset}:{action,algorithm,route})}
 async function stop(){const runId=status?.session?.run_id;if(!runId){setError('缺少执行身份，请刷新状态后停止');return}await request("/e2e/stop",{run_id:runId})}
 return <section className="e2e-page">
  <aside className="e2e-sidebar"><span className="eyebrow">ALGORITHM CATALOG</span><h2>End-to-End Testing</h2><p>Runnable models are selectable. The remaining cards document paper baselines and the exact missing component.</p>{status?.algorithms.map(a=><button key={a.id} title={a.enabled?"Ready to run":a.status.replaceAll("_"," ")} className={`algorithm-card ${algorithm===a.id?"selected":""}`} disabled={running||!a.enabled} onClick={()=>setAlgorithm(a.id)}><div className="algorithm-mark">{a.name[0]}</div><div><strong>{a.name}</strong><small>{a.framework} · {a.sensors}</small></div><span>{a.enabled?"READY":a.status==="missing_checkpoint"?"NEEDS WEIGHT":a.status==="not_released"?"NOT RELEASED":"NOT INSTALLED"}</span></button>)}</aside>
  <div className="e2e-main">
   <BatchPanel/>
   {error&&<p role="alert">启动/停止失败：{error}</p>}
   {pending&&<p role="status">正在提交请求，请勿重复启动…</p>}
   <div className="e2e-summary"><div><span>MODEL</span><strong>{selectedAlgorithm?.name||"Select"}</strong><small>{selectedAlgorithm?.status}</small></div><div><span>INFERENCE</span><strong>{telemetry?`FRAME ${telemetry.frame}`:"WAITING"}</strong><small>{telemetry?`${telemetry.inputs.speed_mps.toFixed(2)} m/s`:"No input"}</small></div><div><span>JOB STATE</span><strong className={`job-${status?.job.state}`}>{status?.job.state||"loading"}</strong><small>{status?.job.kind||"No task"}</small></div></div>
   <div className="e2e-control"><div><label>Generated scenarios</label><select disabled={running} value={route} onChange={e=>setRoute(e.target.value)}>{status?.routes.map(v=><option key={v.path} value={v.path}>{v.relative}</option>)}</select><small>Natural-language ScenarioSpec catalog</small></div><div className="e2e-actions"><button disabled={running||!route||!selectedAlgorithm?.enabled||!supportsGeneratedScene(algorithm)} onClick={()=>start("run")}>Run generated scene</button><button disabled={running} onClick={()=>start("doctor")}>Check UniAD environment</button><button disabled={running||algorithm!=="uniad-tiny"} onClick={()=>start("model-smoke")}>Load UniAD-Tiny</button><button className="danger" disabled={pending||!status?.session?.run_id||!['running','stopping'].includes(status?.job.state||'')||!['run','preset-run','doctor','model-smoke'].includes(status?.job.kind||'')} onClick={stop}>Stop</button></div></div>
   <div className="preset-panel"><div className="stagebar"><span>PRESET SCENARIOS</span><em>BENCH2DRIVE · EXTERNAL READ ONLY</em></div><div><label>Route collection</label><select disabled={running} value={collection} onChange={e=>{const next=e.target.value;setCollection(next);setPreset(collections.find(v=>v.path===next)?.routes[0]?.id||"")}}>{collections.map(v=><option key={v.path} value={v.path}>{v.name} · {v.route_count} routes</option>)}</select></div><div><label>Town · route · scenarios</label><select disabled={running} value={preset} onChange={e=>setPreset(e.target.value)}>{selectedCollection?.routes.map(v=><option key={v.id} value={v.id}>{v.town} · #{v.id} · {v.scenarios.join(", ")}</option>)}</select></div><div className="preset-selection"><b>{selectedPreset?`${selectedPreset.town} · Route #${selectedPreset.id}`:"Select a route"}</b><small>{selectedPreset?.scenarios.join(" · ")||"No scenario selected"}</small></div><button className="primary preset-start" disabled={running||!preset||!selectedAlgorithm?.enabled} onClick={()=>start("preset-run")}>Start preset closed-loop test</button></div>
   <SensorWorkbench/>
   <div className="benchmark-panel"><div className="stagebar"><span>BENCHMARK REPORTS</span><em>PUBLISHED RESULTS</em></div><div className="report-grid">{reports.map(r=><article key={r.algorithm}><h3>{r.algorithm}</h3><b>{r.driving_score.toFixed(2)}</b><small>Driving score</small><dl><div><dt>Routes</dt><dd>{r.routes}</dd></div><div><dt>Completion</dt><dd>{r.route_completion.toFixed(2)}%</dd></div><div><dt>Infractions</dt><dd>{Object.values(r.infractions).reduce((a,b)=>a+b,0)}</dd></div></dl></article>)}</div></div>
   <div className="e2e-console"><div className="stagebar"><span>LIVE LOG</span><em>{status?.job.kind}</em></div><pre>{status?.log||"Ready."}</pre></div>
  </div>
 </section>;
}
