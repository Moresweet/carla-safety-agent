export function splitFileError(size:number):string{
 if(!Number.isSafeInteger(size)||size<=0)return '请选择非空的划分 JSON 文件';
 if(size>8*1024**2)return '划分 JSON 文件不能超过 8 MiB';
 return '';
}

export function parseSplitRegistration(raw:unknown,httpStatus:number){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('登记响应格式异常');
 const value=raw as Record<string,unknown>;
 if(httpStatus<200||httpStatus>=300||value.ok!==true)throw Error(typeof value.error==='string'?value.error:`登记失败（HTTP ${httpStatus}）`);
 if(typeof value.sha256!=='string'||!/^[a-f0-9]{64}$/.test(value.sha256)||typeof value.created!=='boolean'||
    typeof value.run_count!=='number'||!Number.isSafeInteger(value.run_count)||value.run_count<1||
    value.verification!=='finalized_manifest_and_temporal_index'||value.raw_sensor_files_verified!==false)throw Error('登记响应格式异常');
 return {sha256:value.sha256,created:value.created,run_count:value.run_count};
}
