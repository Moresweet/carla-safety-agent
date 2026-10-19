export type QualityReport={run_id:string;state:string;manifest_freshness?:'changed'|'unchanged'|'unknown';reason_code?:string|null;problem_frame?:number|null;detail?:string;finished_at_unix?:number;error?:string};
export function parseQualityReport(value:unknown,runId:string,httpOk:boolean):QualityReport {
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('校验报告格式异常');
 const row=value as Record<string,unknown>;
 if(row.manifest_freshness!==undefined&&!['changed','unchanged','unknown'].includes(row.manifest_freshness as string))throw Error('校验新鲜度格式异常');
 if(!httpOk||row.ok!==true)throw Error(typeof row.error==='string'?row.error:'校验请求失败');
 if(row.run_id!==runId)throw Error('校验报告身份不匹配');
 if(typeof row.state!=='string'||!['not_checked','running','passed','failed','incomplete'].includes(row.state))throw Error('未知校验状态');
 for(const key of ['detail','error'])if(row[key]!==undefined&&typeof row[key]!=='string')throw Error('校验日志格式异常');
 if(row.reason_code!==undefined&&row.reason_code!==null&&typeof row.reason_code!=='string')throw Error('校验原因格式异常');
 if(row.problem_frame!==undefined&&row.problem_frame!==null&&(typeof row.problem_frame!=='number'||!Number.isSafeInteger(row.problem_frame)||row.problem_frame<0))throw Error('问题帧编号格式异常');
 if(row.finished_at_unix!==undefined&&(typeof row.finished_at_unix!=='number'||!Number.isFinite(row.finished_at_unix)||row.finished_at_unix<0||row.finished_at_unix>8640000000000))throw Error('校验时间格式异常');
 return row as QualityReport;
}
