import assert from 'node:assert/strict';
import {parseComparison} from './livery-designer/app/comparisonData.ts';
const expected={axis:'textures',baseline:'original',candidate:'edited'};
const valid={ok:true,comparison:{...expected,comparable_count:1,pairs:[{seed:1,fixed_variants:{scenes:'s',models:'m',weather:'w'},comparable:true,candidate_minus_baseline:{min_ttc_s:null,min_distance_m:-2,risk_score:0},baseline_collision:false,candidate_collision:true}]}};
assert.equal(parseComparison(valid,expected).pairs[0].candidate_minus_baseline.min_ttc_s,null);
for(const change of [v=>v.ok=false,v=>v.comparison.baseline='other',v=>v.comparison.comparable_count=2,v=>delete v.comparison.pairs[0].baseline_collision,v=>v.comparison.pairs[0].candidate_minus_baseline.risk_score='0',v=>Object.assign(v.comparison,{excluded_count:1,exclusion_counts:{missing_variant:1},execution_state_counts:{original:{completed:1},edited:{completed:1}}})]){
 const data=structuredClone(valid);change(data);assert.throws(()=>parseComparison(data,expected));
}
const excluded=structuredClone(valid);excluded.comparison.comparable_count=0;excluded.comparison.pairs=[{seed:1,fixed_variants:{scenes:'s',models:'m',weather:'w'},comparable:false,reason:'execution stopped'}];
assert.equal(parseComparison(excluded,expected).pairs[0].reason,'execution stopped');
const incomplete=structuredClone(valid);delete incomplete.comparison.pairs[0].fixed_variants.weather;
assert.throws(()=>parseComparison(incomplete,expected),/配对条件无效/);
const duplicate=structuredClone(valid);duplicate.comparison.pairs.push(structuredClone(duplicate.comparison.pairs[0]));duplicate.comparison.comparable_count=2;
assert.throws(()=>parseComparison(duplicate,expected),/重复配对/);
console.log('Comparison identity, metric and coverage contracts passed');
