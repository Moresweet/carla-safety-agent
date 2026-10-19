import assert from 'node:assert/strict';
import {captureOutcome,captureQuotaSummary} from './livery-designer/app/captureOutcome.ts';
for(const status of ['saved_capture_error','saved_cleanup_error']) {
 const message=captureOutcome({status,error:'disk full',stop_reason:'capture_io_error'});
 assert.match(message,/不是完整成功/);
 assert.match(message,/disk full/);
 assert.match(message,/capture_io_error/);
}
assert.match(captureOutcome({status:'recording'}),/不能证明任务仍在运行/);
assert.match(captureOutcome({status:'saved_limit'}),/不代表预定采集全部完成/);
for(const status of ['saved_limit','saved']){
 const message=captureOutcome({status,stop_reason:'quota_unknown',error:'measurement incomplete'});
 assert.match(message,/配额无法确认/);
 assert.match(message,/不是已确认达到容量上限/);
 assert.match(message,/measurement incomplete/);
}
assert.match(captureOutcome({status:'saved_capture_error',stop_reason:'quota_unknown'}),/录制异常结束/);
assert.match(captureOutcome({status:'saved',error:'legacy failure'}),/legacy failure/);
assert.match(captureOutcome({status:'saved',error:null}),/不证明评测通过或 CARLA 正常退出/);
assert.match(captureOutcome({status:'saved',error:{message:'bad type'}}),/仅描述录制保存状态/);
console.log('Capture outcome checks passed');
const policy={schema_version:'capture-quota-policy/1',valid:true,source:'default',limit_bytes:100*1024**3,measurement:'allocated_file_blocks_in_manifest_directories'};
assert.match(captureQuotaSummary(policy),/100 GiB.*默认配置/);
assert.match(captureQuotaSummary({...policy,source:'environment',limit_bytes:90*1024**3}),/90 GiB.*环境配置/);
assert.match(captureQuotaSummary(undefined),/不能用当前配置推断/);
assert.match(captureQuotaSummary({...policy,valid:false,limit_bytes:null}),/配置无效/);
for(const value of [[],{},'100',{...policy,limit_bytes:-1},{...policy,limit_bytes:Infinity},{...policy,limit_bytes:'100'},{...policy,valid:'true'}])assert.match(captureQuotaSummary(value),/格式异常/);
console.log('Capture quota summary checks passed');
