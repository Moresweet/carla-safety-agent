export function captureQualityMessage(report:{state:string;reason_code?:unknown;problem_frame?:number|null;detail?:string}):string|null {
 if(report.state==='failed'&&report.reason_code==='invalid_ego_pose')
  return `自车位姿无效${typeof report.problem_frame==='number'&&Number.isSafeInteger(report.problem_frame)&&report.problem_frame>=0?`（帧 ${report.problem_frame}）`:''}，不能用于可靠的轨迹回放或评测。原始数据未被自动修复，请查看校验日志。`;
 if(report.state==='failed'&&(report.reason_code==='no_samples'||
    (report.reason_code===undefined&&report.detail?.includes('ValueError: No recorded samples'))))
  return '没有已录制样本，无法验证原始数据质量。此检查失败不表示 CARLA 崩溃；请结合录制停止原因判断。';
 if(report.state==='incomplete'&&report.reason_code==='validation_timeout')return '校验超过时间限制，尚未得到完整质量结论。';
 if(report.state==='incomplete'&&report.reason_code==='validation_interrupted')return '保存的质量任务不由当前服务管理，完成结果未知；不会自动重试。请先核查后台任务，再决定是否重新检查。';
 if(report.state==='incomplete'&&report.reason_code==='validator_unavailable')return '校验器无法启动，尚未检查数据；请查看日志中的环境或路径错误。';
 return null;
}
