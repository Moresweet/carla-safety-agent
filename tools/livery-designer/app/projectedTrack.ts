export type TrackPoint={xyz_m:number[];dt_s:number|null};
export type ProjectedTrack={state:string;points?:TrackPoint[];reason?:string;source_frame?:number;map_sha256?:string;timing_verified?:boolean;error_metrics_computed?:boolean;navigation_position_delta_m?:number};
export function usableProjectedTrack(value:ProjectedTrack|undefined,sourceFrame:number|undefined):value is ProjectedTrack&{points:TrackPoint[];navigation_position_delta_m:number}{
 return !!value&&value.state==='available'&&Number.isInteger(sourceFrame)&&value.source_frame===sourceFrame&&
 typeof value.map_sha256==='string'&&/^[0-9a-f]{64}$/.test(value.map_sha256)&&
 value.timing_verified===false&&value.error_metrics_computed===false&&
 typeof value.navigation_position_delta_m==='number'&&Number.isFinite(value.navigation_position_delta_m)&&value.navigation_position_delta_m>=0&&
 Array.isArray(value.points)&&value.points.length===4&&value.points.every(p=>p&&p.dt_s===null&&Array.isArray(p.xyz_m)&&p.xyz_m.length===3&&p.xyz_m.every(v=>typeof v==='number'&&Number.isFinite(v)));
}
