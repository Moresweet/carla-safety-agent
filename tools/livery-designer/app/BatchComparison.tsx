"use client";
import {useEffect,useState} from 'react';
import {type Comparison} from './comparisonData';
import {readComparison} from './comparisonRequest';
const axes={models:'模型',scenes:'场景',weather:'天气',textures:'纹理'};
export default function BatchComparison({batchId,rows}:{batchId:string;rows:{variants:Record<string,string>}[]}){
 const [axis,setAxis]=useState('weather'),[baseline,setBaseline]=useState(''),[candidate,setCandidate]=useState('');
 const [result,setResult]=useState<Comparison|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [retry,setRetry]=useState(0);
 // Equal report contents must not cancel an in-flight read on parent renders.
 const reportRevision=JSON.stringify(rows);
 const variants=Array.from(new Set(rows.map(row=>row.variants[axis])));
 const signature=JSON.stringify(variants);
 useEffect(()=>{setBaseline('');setCandidate('')},[signature]);
 useEffect(()=>{
  setResult(null);setError('');
  if(!baseline||!candidate||baseline===candidate){setBusy(false);return}
  setBusy(true);
  return readComparison({batch_id:batchId,axis,baseline,candidate},setResult,setError,()=>setBusy(false));
 },[batchId,axis,baseline,candidate,reportRevision,retry]);
 return <section aria-label="配对比较">
  <h3>配对比较</h3><p>固定种子和其余三个维度，查看“对照项 − 基准项”的指标差值。仅描述结果，不代表统计显著性或因果关系。</p>
  <div style={{display:'flex',gap:'12px',flexWrap:'wrap'}}>
   <label>比较维度 <select value={axis} onChange={e=>{setAxis(e.target.value);setBaseline('');setCandidate('')}}>{Object.entries(axes).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
   <label>基准项 <select value={baseline} onChange={e=>{setBaseline(e.target.value);if(candidate===e.target.value)setCandidate('')}}><option value="">请选择</option>{variants.map(id=><option key={id}>{id}</option>)}</select></label>
   <label>对照项 <select value={candidate} onChange={e=>setCandidate(e.target.value)}><option value="">请选择</option>{variants.filter(id=>id!==baseline).map(id=><option key={id}>{id}</option>)}</select></label>
  </div>
  {variants.length<2&&<p>当前维度不足两个变体，请选择其他维度或批次。</p>}
  {busy&&<p role="status">正在读取配对指标…</p>}{error&&<p role="alert">{error}</p>}
  <button disabled={busy||!baseline||!candidate||baseline===candidate} onClick={()=>setRetry(value=>value+1)}>重新读取比较</button>
  {result?.exclusion_counts&&<div aria-label="比较覆盖与排除原因">
   <p>未纳入比较 {result.excluded_count} 对。执行失败、主动停止或缺少指标不按通过处理，也不填成零分。</p>
   <ul>{Object.entries(result.exclusion_counts).map(([code,count])=><li key={code}>{({missing_variant:'缺少配对变体',execution_or_metrics_unverified:'执行未完成或指标未核验',duration_mismatch:'观察时长不同'} as Record<string,string>)[code]??code}：{count}</li>)}</ul>
   {Object.entries(result.execution_state_counts??{}).map(([variant,counts])=><p key={variant}>{variant}：{Object.entries(counts).map(([state,count])=>`${state} ${count}`).join(' / ')}</p>)}
  </div>}
  {result&&<><p>可比较 {result.comparable_count} / {result.pairs.length} 对</p><div style={{overflowX:'auto'}}><table><thead><tr><th>固定条件 / 种子</th><th>最小 TTC 差值（秒）</th><th>最小距离差值（米）</th><th>风险分差值</th><th>碰撞（基准 → 对照）/ 原因</th></tr></thead><tbody>{result.pairs.map((pair,index)=><tr key={index}>
   <td>{Object.values(pair.fixed_variants).join(' / ')} / {pair.seed}</td>
   {['min_ttc_s','min_distance_m','risk_score'].map(metric=><td key={metric}>{pair.comparable?(pair.candidate_minus_baseline?.[metric]?.toFixed(4)??'未测得'):'不可比较'}</td>)}
   <td>{pair.comparable?`${pair.baseline_collision?'有':'无'} → ${pair.candidate_collision?'有':'无'}`:pair.reason}</td>
  </tr>)}</tbody></table></div></>}
 </section>;
}
