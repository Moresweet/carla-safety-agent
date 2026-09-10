"use client";
import {useState} from "react";
import RuleSessionControls from "./RuleSessionControls";
import ReviewedModelRun from "./ReviewedModelRun";
import PlanRevisionPanel from './PlanRevisionPanel';
const bridge="http://127.0.0.1:8765";
const examples=["Town04 大雨夜间，前车在18米处急刹，自车速度15 m/s","生成一条双向4车道S弯道路，前方35米掉落6根金属管，有20棵树和8栋建筑","Town04 路口行人横穿，自车速度12 m/s，有雾"];
export default function ScenarioGeneratorPage({onEvaluationStarted}:{onEvaluationStarted?:()=>void}){
 const [text,setText]=useState(examples[0]),[seed,setSeed]=useState(7),[result,setResult]=useState<Record<string,unknown>|null>(null),[status,setStatus]=useState("Describe a safety-critical interaction in Chinese or English."),[busy,setBusy]=useState(false);
 const [unifiedCapture,setUnifiedCapture]=useState(false);
 const [reviewing,setReviewing]=useState(false);
 function invalidate(){setResult(null);setReviewing(false)}
 async function call(path:string){const evaluating=path.endsWith("evaluate"),running=path.endsWith("run");setBusy(true);setStatus(evaluating?"Compiling and launching native UniAD evaluation…":running?"Building and running scenario in CARLA…":"Compiling description…");try{const r=await fetch(`${bridge}/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({description:text,seed,...(running?{unified_capture:unifiedCapture}:{})})}),v=await r.json() as Record<string,unknown>;if(!r.ok)throw new Error(String(v.error));setResult(v);setStatus(evaluating?"Native closed-loop evaluation started.":running?"Scenario finished. Results are shown below.":"Structured scenario ready for review.");if(evaluating)onEvaluationStarted?.()}catch(e){setStatus(e instanceof Error?e.message:"Scenario request failed")}finally{setBusy(false)}}
 function download(){if(!result)return;const blob=new Blob([JSON.stringify(result.scenario??result,null,2)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`scenario-${(result.scenario as {seed?:number}|undefined)?.seed??seed}.json`;a.click();URL.revokeObjectURL(a.href)}
 return <section className="scenario-page"><div className="scenario-compose">
  <span className="eyebrow">NATURAL LANGUAGE → STRUCTURED SCENE</span><h2>Safety Scenario Generator</h2><p>先编译并检查右侧地图、对象、天气、触发条件及限制，再选择模型并确认运行。修改原始描述或种子会重新编译；局部修订通过下方独立入口保留其他字段。</p>
  <label style={{display:'block',fontSize:'14px',marginBottom:'12px'}}><input type="checkbox" checked={unifiedCapture} disabled={busy||reviewing} onChange={e=>setUnifiedCapture(e.target.checked)}/>规则运行时录制六视角、深度、点云和 BEV</label>
  <p style={{fontSize:'14px'}}>此项仅用于规则场景任务；最多保存2000个同步样本，结束后在数据列表中回放。模型测试采集请在下方单独选择。</p>
  <textarea aria-label="场景描述" disabled={busy||reviewing} value={text} onChange={e=>{setText(e.target.value);invalidate()}} rows={7}/>
  <div className="scenario-actions"><label>Seed <input disabled={busy||reviewing} type="number" value={seed} onChange={e=>{setSeed(+e.target.value);invalidate()}}/></label><button disabled={busy||reviewing||!text.trim()} onClick={()=>{invalidate();void call('scenario/compile')}}>Compile & preview</button></div>
  <PlanRevisionPanel key={String(result?.scenario_sha256??'none')} plan={result} disabled={busy} onPending={setReviewing} onAdopt={value=>{setResult(value);setReviewing(false);setStatus('局部修订已采纳，未运行仿真；请检查新JSON并重新确认执行。')}}/>
  <ReviewedModelRun key={'model:'+String(result?.scenario_sha256??'none')} plan={result} disabled={busy||reviewing} onStarted={onEvaluationStarted}/>
  <RuleSessionControls plan={result} capture={unifiedCapture} disabled={busy||reviewing}/>
  <small role="status">{status}</small><div className="scenario-examples">{examples.map(v=><button disabled={busy||reviewing} key={v} onClick={()=>{setText(v);invalidate()}}>{v}</button>)}</div>
 </div><div className="scenario-json"><div className="stagebar"><span>STRUCTURED SCENARIO JSON</span><button disabled={!result} onClick={download}>Download JSON</button></div><pre>{result?JSON.stringify(result,null,2):'Compile a description to inspect its actors, environment, map, assets and safety oracle.'}</pre></div></section>;
}
