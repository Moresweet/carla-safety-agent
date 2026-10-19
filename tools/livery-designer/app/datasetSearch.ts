export type SearchableDataset={run_id:string;scenario_id?:string;status?:string;map?:string;model?:unknown;family?:unknown};
export function datasetModelLabel(row:SearchableDataset):string {
 if(typeof row.model==='string'&&row.model.trim())return row.model;
 return row.family==='sensor-rig'?'独立采集（无模型）':'模型未记录';
}
export function searchDatasets<T extends SearchableDataset>(rows:T[],query:string,selected:string){
 const terms=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
 const matches=rows.filter(row=>{
  const text=[row.run_id,row.scenario_id,row.status,row.map,row.model,row.family,datasetModelLabel(row)].filter(value=>typeof value==='string').join(' ').toLocaleLowerCase();
  return terms.every(term=>text.includes(term));
 });
 const current=rows.find(row=>row.run_id===selected);
 const retained=!!current&&!matches.some(row=>row.run_id===selected);
 return {matches,options:retained?[current!,...matches]:matches,retained};
}
