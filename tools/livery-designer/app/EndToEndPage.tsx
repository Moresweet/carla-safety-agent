"use client";
import {useEffect,useMemo,useState} from "react";

const bridge="http://127.0.0.1:8765";
type Algorithm={id:string;name:string;framework:string;checkpoint:string;sensors:string;enabled:boolean;status:string};
type Route={name:string;path:string;relative:string;count:number};
type PresetRoute={id:string;town:string;scenarios:string[]};
type Collection={id:string;name:string;path:string;route_count:number;routes:PresetRoute[]};
type Report={algorithm:string;routes:number;driving_score:number;route_completion:number;infractions:Record<string,number>};
type Telemetry={frame:number;elapsed_s:number;inputs:{camera_ids:string[];speed_mps:number;gps:number[];synchronized:boolean};outputs:{steer:number;throttle:number;brake:number;plan:number[][]}};
type Status={algorithms:Algorithm[];job:{state:string;kind:string|null;returncode:number|null};routes:Route[];log:string};

function Plan({points}:{points:number[][]}){
 const value=useMemo(()=>points?.map((p,i)=>`${30+p[0]*4},${180-i*25}`).join(" ")||"",[points]);
 return <svg className="plan-view" viewBox="0 0 200 200"><path d="M100 190 90 170 110 170Z"/><polyline points={value}/></svg>;
}

export default function EndToEndPage(){
 const [status,setStatus]=useState<Status|null>(null),[telemetry,setTelemetry]=useState<Telemetry|null>(null);
 const [collections,setCollections]=useState<Collection[]>([]),[reports,setReports]=useState<Report[]>([]);
 const [algorithm,setAlgorithm]=useState("uniad-tiny"),[route,setRoute]=useState(""),[collection,setCollection]=useState(""),[preset,setPreset]=useState("");
 const refresh=()=>{fetch(`${bridge}/e2e/status`).then(r=>r.json()).then(v=>{setStatus(v);setRoute(x=>x||v.routes[0]?.path||"")});fetch(`${bridge}/e2e/telemetry`).then(r=>r.json()).then(v=>setTelemetry(v.telemetry)).catch(()=>{})};
 useEffect(()=>{refresh();Promise.all([fetch(`${bridge}/e2e/benchmark/catalog`).then(r=>r.json()),fetch(`${bridge}/e2e/benchmark/report`).then(r=>r.json())]).then(([c,r])=>{setCollections(c.routes.collections);setCollection(c.routes.collections[0]?.path||"");setPreset(c.routes.collections[0]?.routes[0]?.id||"");setReports(r.report.reports)});const timer=setInterval(refresh,1000);return()=>clearInterval(timer)},[]);
 const selectedCollection=collections.find(v=>v.path===collection),selectedAlgorithm=status?.algorithms.find(v=>v.id===algorithm),running=["running","stopping"].includes(status?.job.state||"");
 const selectedPreset=selectedCollection?.routes.find(v=>v.id===preset);
 async function start(action:string){await fetch(`${bridge}/e2e/start`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(action==="preset-run"?{action,algorithm,collection,route_id:preset}:{action,algorithm,route})});refresh()}
 async function stop(){await fetch(`${bridge}/e2e/stop`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});refresh()}
 return <section className="e2e-page">
  <aside className="e2e-sidebar"><span className="eyebrow">ALGORITHM CATALOG</span><h2>End-to-End Testing</h2><p>Runnable models are selectable. The remaining cards document paper baselines and the exact missing component.</p>{status?.algorithms.map(a=><button key={a.id} title={a.enabled?"Ready to run":a.status.replaceAll("_"," ")} className={`algorithm-card ${algorithm===a.id?"selected":""}`} disabled={!a.enabled} onClick={()=>setAlgorithm(a.id)}><div className="algorithm-mark">{a.name[0]}</div><div><strong>{a.name}</strong><small>{a.framework} · {a.sensors}</small></div><span>{a.enabled?"READY":a.status==="missing_checkpoint"?"NEEDS WEIGHT":"NOT INSTALLED"}</span></button>)}</aside>
  <div className="e2e-main">
   <div className="e2e-summary"><div><span>MODEL</span><strong>{selectedAlgorithm?.name||"Select"}</strong><small>{selectedAlgorithm?.status}</small></div><div><span>INFERENCE</span><strong>{telemetry?`FRAME ${telemetry.frame}`:"WAITING"}</strong><small>{telemetry?`${telemetry.inputs.speed_mps.toFixed(2)} m/s`:"No input"}</small></div><div><span>JOB STATE</span><strong className={`job-${status?.job.state}`}>{status?.job.state||"loading"}</strong><small>{status?.job.kind||"No task"}</small></div></div>
   <div className="e2e-control"><div><label>Generated scenarios</label><select value={route} onChange={e=>setRoute(e.target.value)}>{status?.routes.map(v=><option key={v.path} value={v.path}>{v.relative}</option>)}</select><small>Natural-language ScenarioSpec catalog</small></div><div className="e2e-actions"><button disabled={running||!route} onClick={()=>start("run")}>Run generated scene</button><button disabled={running} onClick={()=>start("doctor")}>Check environment</button><button disabled={running} onClick={()=>start("model-smoke")}>Load model</button><button className="danger" disabled={!running} onClick={stop}>Stop</button></div></div>
   <div className="preset-panel"><div className="stagebar"><span>PRESET SCENARIOS</span><em>BENCH2DRIVE · EXTERNAL READ ONLY</em></div><div><label>Route collection</label><select value={collection} onChange={e=>{const next=e.target.value;setCollection(next);setPreset(collections.find(v=>v.path===next)?.routes[0]?.id||"")}}>{collections.map(v=><option key={v.path} value={v.path}>{v.name} · {v.route_count} routes</option>)}</select></div><div><label>Town · route · scenarios</label><select value={preset} onChange={e=>setPreset(e.target.value)}>{selectedCollection?.routes.map(v=><option key={v.id} value={v.id}>{v.town} · #{v.id} · {v.scenarios.join(", ")}</option>)}</select></div><div className="preset-selection"><b>{selectedPreset?`${selectedPreset.town} · Route #${selectedPreset.id}`:"Select a route"}</b><small>{selectedPreset?.scenarios.join(" · ")||"No scenario selected"}</small></div><button className="primary preset-start" disabled={running||!preset||!selectedAlgorithm?.enabled} onClick={()=>start("preset-run")}>Start preset closed-loop test</button></div>
   <div className="model-telemetry"><div className="stagebar"><span>MODEL INPUT / OUTPUT</span><em>{telemetry?.inputs.synchronized?"SYNCHRONIZED":"WAITING"}</em></div>{telemetry?<><div className="camera-grid">{telemetry.inputs.camera_ids.map(id=><figure key={id}><img src={`${bridge}/e2e/camera?id=${id}&frame=${telemetry.frame}`} alt={id}/><figcaption>{id.replaceAll("CAM_","").replaceAll("_"," ")}</figcaption></figure>)}</div><div className="output-grid"><Plan points={telemetry.outputs.plan}/><dl><div><dt>Speed</dt><dd>{telemetry.inputs.speed_mps.toFixed(2)} m/s</dd></div><div><dt>Steer</dt><dd>{telemetry.outputs.steer.toFixed(3)}</dd></div><div><dt>Throttle</dt><dd>{telemetry.outputs.throttle.toFixed(3)}</dd></div><div><dt>Brake</dt><dd>{telemetry.outputs.brake.toFixed(3)}</dd></div></dl></div></>:<p className="telemetry-empty">Start a test to inspect synchronized model evidence.</p>}</div>
   <div className="benchmark-panel"><div className="stagebar"><span>BENCHMARK REPORTS</span><em>PUBLISHED RESULTS</em></div><div className="report-grid">{reports.map(r=><article key={r.algorithm}><h3>{r.algorithm}</h3><b>{r.driving_score.toFixed(2)}</b><small>Driving score</small><dl><div><dt>Routes</dt><dd>{r.routes}</dd></div><div><dt>Completion</dt><dd>{r.route_completion.toFixed(2)}%</dd></div><div><dt>Infractions</dt><dd>{Object.values(r.infractions).reduce((a,b)=>a+b,0)}</dd></div></dl></article>)}</div></div>
   <div className="e2e-console"><div className="stagebar"><span>LIVE LOG</span><em>{status?.job.kind}</em></div><pre>{status?.log||"Ready."}</pre></div>
  </div>
 </section>;
}
