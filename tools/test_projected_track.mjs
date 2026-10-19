import assert from 'node:assert/strict';
import {usableProjectedTrack} from './livery-designer/app/projectedTrack.ts';
const valid={state:'available',points:Array.from({length:4},()=>({xyz_m:[1,2,0],dt_s:null})),source_frame:7,map_sha256:'a'.repeat(64),timing_verified:false,error_metrics_computed:false,navigation_position_delta_m:.09};
assert(usableProjectedTrack(valid,7));
assert(!usableProjectedTrack(valid,8));
for(const change of [{state:'unavailable'},{points:[]},{map_sha256:'bad'},{timing_verified:true},{error_metrics_computed:true},{navigation_position_delta_m:NaN},{points:[...valid.points.slice(1),{xyz_m:[Infinity,0,0],dt_s:null}]}])assert(!usableProjectedTrack({...valid,...change},7));
assert(!usableProjectedTrack(undefined,7));
console.log('Projected track selection validation passed');
