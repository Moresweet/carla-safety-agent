"use client";
import {useEffect,useRef,useState} from 'react';
type Asset={job_id?:string;name?:string;objects?:number;vertices?:number;materials?:number;outputs?:Record<string,string|null>};
type Spec={shape:string;dimensions:number[];color:number[];roughness:number};
type Plan={plan_sha256:string;plan:{description:string;spec:Spec;warnings:string[];scope:string}};
export default function NaturalAssetPlan({disabled,onBusy,onGenerated}:{disabled:boolean;onBusy:(busy:boolean)=>void;onGenerated:(asset:Asset,spec:Spec)=>void}){
 const [text,setText]=useState('生成一个蓝色长方体，长2米，宽40厘米，高0.8米，粗糙度0.6');
 const [plan,setPlan]=useState<Plan|null>(null),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const active=useRef(false),controller=useRef<AbortController|null>(null),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;controller.current?.abort()}},[]);
 async function request(execute:boolean){
  if(disabled||active.current||execute&&(!plan||!confirmed))return;
  active.current=true;setBusy(true);onBusy(true);setMessage(execute?'Blender 正在按已确认计划导出…':'正在编译，只保存计划，不启动 Blender…');
  if(!execute){setPlan(null);setConfirmed(false)}
  const abort=new AbortController();controller.current=abort;
  const timeout=setTimeout(()=>abort.abort(),execute?200000:10000);
  try{
   const response=await fetch('http://127.0.0.1:8765/blender/'+(execute?'execute-plan':'plan'),{method:'POST',headers:{'Content-Type':'application/json'},signal:abort.signal,body:JSON.stringify(execute?{plan_sha256:plan!.plan_sha256,confirmed:true}:{description:text})});
   const result=await response.json() as Plan&Asset&{ok?:boolean;error?:string};
   if(!response.ok||!result.ok)throw Error(result.error??'Asset plan request failed');
   if(!alive.current)return;
   if(execute){onGenerated(result,plan!.plan.spec);setConfirmed(false);setMessage('已按归档计划导出。请检查下方结果，再分别导入注册和生成到 CARLA。')}
   else{if(!result.plan_sha256||!result.plan?.spec)throw Error('Invalid asset plan response');setPlan(result);setMessage('请审阅参数及限制；尚未启动 Blender 或修改 CARLA。')}
  }catch(e){if(alive.current){setMessage(String(e)+'；执行结果不明确时请检查生成历史，不要直接重复执行。');setConfirmed(false)}}
  finally{clearTimeout(timeout);active.current=false;if(alive.current){setBusy(false);onBusy(false)}}
 }
 return <section className="plan-revision" aria-label="自然语言 Blender 计划">
  <h3>自然语言 → 本地参数化 Blender 模型</h3>
  <p>明确描述长方体/立方体、圆柱体、圆锥体、球体或平面，逐项给出长、宽、高及米/厘米单位。支持蓝、红、黄、绿、白、黑、灰色及粗糙度。未知要求整次拒绝，不是任意文本到3D生成器。</p>
  <textarea aria-label="模型自然语言描述" disabled={disabled||busy} value={text} onChange={e=>{setText(e.target.value);setPlan(null);setConfirmed(false)}}/>
  <button disabled={disabled||busy||!text.trim()} onClick={()=>void request(false)}>编译模型计划（不生成）</button>
  {plan&&<div><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(plan.plan.spec,null,2)}</pre><p>计划 SHA-256：{plan.plan_sha256}</p>{plan.plan.warnings.map(w=><p key={w}>{w}</p>)}
   <label><input type="checkbox" disabled={disabled||busy} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>我已检查参数与限制，确认生成该归档计划</label>
   <button disabled={disabled||busy||!confirmed} onClick={()=>void request(true)}>按确认计划生成并导出</button>
  </div>}
  <p role="status">{message}</p>
 </section>;
}
