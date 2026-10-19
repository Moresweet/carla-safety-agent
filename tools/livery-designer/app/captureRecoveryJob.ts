export type CandidatePresence={staged:boolean;published:boolean;raw_data_verified:false};
export type RecoveryJob={request_id:string;state:string;recovered_run_id?:string;error?:string;phase?:string;staging_directory?:string;candidate_run_id?:string;candidate_presence?:CandidatePresence};
export function recoverySubmissionId(job:RecoveryJob|null,attempt:string|null,create:()=>string):string{
 if(job&&['running','needs_attention','recovered'].includes(job.state))throw Error('当前恢复任务不可重新提交');
 if(job?.state==='checking'){
  if(!/^[a-f0-9]{32}$/.test(job.request_id)||attempt!==job.request_id)throw Error('未知结果必须使用原请求 ID');
  return job.request_id;
 }
 if(job&&job.state!=='failed')throw Error('恢复状态无效');
 return job?.state==='failed'?create():(attempt??create());
}
export function candidateLocation(p:CandidatePresence):string{
 return p.staged?(p.published?'暂存区与目标目录均存在候选副本，需核对冲突':'候选副本仍在暂存区，尚不能认定已发布'):(p.published?'目标目录存在候选副本，最终恢复结果仍以任务回执为准':'两处均未发现候选目录，需检查文件位置');
}
export function parseRecoveryJob(raw:unknown,requestId:string,source:string):RecoveryJob{
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('恢复任务响应无效');
 const value=raw as Record<string,unknown>;
 if(value.ok!==true||value.request_id!==requestId||value.source_run_id!==source||!['running','failed','needs_attention','recovered'].includes(String(value.state)))throw Error('恢复任务身份或状态无效');
 for(const key of ['error','phase','staging_directory'])if(value[key]!==undefined&&typeof value[key]!=='string')throw Error('恢复任务说明字段无效');
 for(const key of ['recovered_run_id','candidate_run_id'])if(value[key]!==undefined&&(typeof value[key]!=='string'||!/^recovered-[a-f0-9]{32}$/.test(value[key] as string)))throw Error('恢复副本身份无效');
 if(value.state==='recovered'&&!value.recovered_run_id)throw Error('恢复成功缺少副本身份');
 if(value.state!=='recovered'&&value.recovered_run_id!==undefined)throw Error('未完成任务不能声明已发布副本');
 if(value.candidate_run_id&&value.recovered_run_id&&value.candidate_run_id!==value.recovered_run_id)throw Error('候选与已发布副本不一致');
 if(value.candidate_presence!==undefined){
  const p=value.candidate_presence;
  if(!value.candidate_run_id||!p||typeof p!=='object'||Array.isArray(p))throw Error('候选位置检查无效');
  const presence=p as Record<string,unknown>;
  if(typeof presence.staged!=='boolean'||typeof presence.published!=='boolean'||presence.raw_data_verified!==false)throw Error('候选位置检查范围无效');
 }
 return value as RecoveryJob;
}
