export type Pair={seed:number;fixed_variants:Record<string,string>;comparable:boolean;reason?:string;candidate_minus_baseline?:Record<string,number|null>;baseline_collision?:boolean;candidate_collision?:boolean};
export type Comparison={axis:string;baseline:string;candidate:string;comparable_count:number;pairs:Pair[];excluded_count?:number;exclusion_counts?:Record<string,number>;execution_state_counts?:Record<string,Record<string,number>>};
function object(value:unknown):Record<string,unknown>{
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('比较响应结构无效');
 return value as Record<string,unknown>;
}
function count(value:unknown):value is number{return typeof value==='number'&&Number.isSafeInteger(value)&&value>=0}
export function parseComparison(raw:unknown,expected:{axis:string;baseline:string;candidate:string}):Comparison{
 const axes=['scenes','models','weather','textures'];
 if(!axes.includes(expected.axis)||expected.baseline===expected.candidate)throw Error('比较选择无效');
 const fixedAxes=axes.filter(axis=>axis!==expected.axis),seen=new Set<string>();
 const envelope=object(raw);if(envelope.ok!==true)throw Error('比较读取未确认成功');
 const data=object(envelope.comparison);
 for(const key of ['axis','baseline','candidate'] as const)if(data[key]!==expected[key])throw Error('比较条件与请求不一致');
 if(!Array.isArray(data.pairs)||data.pairs.length>10000||!count(data.comparable_count))throw Error('比较计数无效');
 const pairs:Pair[]=data.pairs.map(raw=>{
  const p=object(raw),fixed=object(p.fixed_variants);
  if(!count(p.seed)||typeof p.comparable!=='boolean'||Object.keys(fixed).length!==fixedAxes.length||fixedAxes.some(axis=>typeof fixed[axis]!=='string'||!fixed[axis]))throw Error('配对条件无效');
  const identity=JSON.stringify([p.seed,...fixedAxes.map(axis=>fixed[axis])]);
  if(seen.has(identity))throw Error('重复配对条件');seen.add(identity);
  const row:Pair={seed:p.seed,fixed_variants:fixed as Record<string,string>,comparable:p.comparable};
  if(p.comparable){
   const metrics=object(p.candidate_minus_baseline);
   for(const key of ['min_ttc_s','min_distance_m','risk_score']){
    const v=metrics[key];if(v!==null&&(typeof v!=='number'||!Number.isFinite(v)))throw Error('比较指标无效');
   }
   if(typeof p.baseline_collision!=='boolean'||typeof p.candidate_collision!=='boolean')throw Error('碰撞结果未知');
   Object.assign(row,{candidate_minus_baseline:metrics,baseline_collision:p.baseline_collision,candidate_collision:p.candidate_collision});
  }else{if(typeof p.reason!=='string'||!p.reason)throw Error('缺少排除原因');row.reason=p.reason}
  return row;
 });
 if(pairs.filter(p=>p.comparable).length!==data.comparable_count)throw Error('比较总数不一致');
 const result:Comparison={...expected,pairs,comparable_count:data.comparable_count};
 if(data.excluded_count!==undefined||data.exclusion_counts!==undefined||data.execution_state_counts!==undefined){
  const exclusions=object(data.exclusion_counts),states=object(data.execution_state_counts);
  if(!count(data.excluded_count)||data.excluded_count!==pairs.length-data.comparable_count||Object.values(exclusions).some(v=>!count(v))||Object.values(exclusions).reduce<number>((sum,v)=>sum+(v as number),0)!==data.excluded_count)throw Error('排除计数不一致');
  for(const variant of [expected.baseline,expected.candidate])if(Object.values(object(states[variant])).some(v=>!count(v)))throw Error('执行状态计数无效');
  Object.assign(result,{excluded_count:data.excluded_count,exclusion_counts:exclusions,execution_state_counts:states});
 }
 return result;
}
