"use client";
import {useEffect,useState} from 'react';
type Pair={seed:number;fixed_variants:Record<string,string>;comparable:boolean;reason?:string;candidate_minus_baseline?:Record<string,number|null>;baseline_collision?:boolean;candidate_collision?:boolean};
type Comparison={axis:string;baseline:string;candidate:string;comparable_count:number;pairs:Pair[]};
const axes={models:'模型',scenes:'场景',weather:'天气',textures:'纹理'};
export default function BatchComparison({batchId,rows}:{batchId:string;rows:{variants:Record<string,string>}[]}){
 const [axis,setAxis]=useState('weather'),[baseline,setBaseline]=useState(''),[candidate,setCandidate]=useState('');
 const [result,setResult]=useState<Comparison|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const variants=Array.from(new Set(rows.map(row=>row.variants[axis])));
 const signature=JSON.stringify(variants);
 useEffect(()=>{setBaseline('');setCandidate('')},[signature]);
 useEffect(()=>{
  setResult(null);setError('');
  if(!baseline||!candidate||baseline===candidate){setBusy(false);return}
  const controller=new AbortController();setBusy(true);
  const query=new URLSearchParams({batch_id:batchId,axis,baseline,candidate});
  fetch('http://127.0.0.1:8765/batches/compare?'+query,{signal:controller.signal}).then(async response=>{
   const value=await response.json() as {ok?:boolean;error?:string;comparison:Comparison};
   if(!response.ok||value.ok===false)throw new Error(value.error||'比较读取失败');
   if(!controller.signal.aborted)setResult(value.comparison);
  }).catch(e=>{if(!controller.signal.aborted)setError(String(e))}).finally(()=>{if(!controller.signal.aborted)setBusy(false)});
  return()=>controller.abort();
 },[batchId,axis,baseline,candidate,rows]);
 return <section aria-label="配对比较">
  <h3>配对比较</h3><p>固定种子和其余三个维度，查看“对照项 − 基准项”的指标差值。仅描述结果，不代表统计显著性或因果关系。</p>
  <div style={{display:'flex',gap:'12px',flexWrap:'wrap'}}>
   <label>比较维度 <select value={axis} onChange={e=>{setAxis(e.target.value);setBaseline('');setCandidate('')}}>{Object.entries(axes).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
   <label>基准项 <select value={baseline} onChange={e=>{setBaseline(e.target.value);if(candidate===e.target.value)setCandidate('')}}><option value="">请选择</option>{variants.map(id=><option key={id}>{id}</option>)}</select></label>
   <label>对照项 <select value={candidate} onChange={e=>setCandidate(e.target.value)}><option value="">请选择</option>{variants.filter(id=>id!==baseline).map(id=><option key={id}>{id}</option>)}</select></label>
  </div>
  {variants.length<2&&<p>当前维度不足两个变体，请选择其他维度或批次。</p>}
  {busy&&<p role="status">正在读取配对指标…</p>}{error&&<p role="alert">{error}</p>}
  {result&&<><p>可比较 {result.comparable_count} / {result.pairs.length} 对</p><div style={{overflowX:'auto'}}><table><thead><tr><th>固定条件 / 种子</th><th>最小 TTC 差值（秒）</th><th>最小距离差值（米）</th><th>风险分差值</th><th>碰撞（基准 → 对照）/ 原因</th></tr></thead><tbody>{result.pairs.map((pair,index)=><tr key={index}>
   <td>{Object.values(pair.fixed_variants).join(' / ')} / {pair.seed}</td>
   {['min_ttc_s','min_distance_m','risk_score'].map(metric=><td key={metric}>{pair.comparable?(pair.candidate_minus_baseline?.[metric]?.toFixed(4)??'未测得'):'不可比较'}</td>)}
   <td>{pair.comparable?`${pair.baseline_collision?'有':'无'} → ${pair.candidate_collision?'有':'无'}`:pair.reason}</td>
  </tr>)}</tbody></table></div></>}
 </section>;
}
