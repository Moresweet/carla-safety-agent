export function captureOutcome(dataset: {status:string;error?:unknown;stop_reason?:unknown}): string|null {
 const detail=typeof dataset.error==='string'&&dataset.error.trim()?dataset.error.trim():'';
 const reason=typeof dataset.stop_reason==='string'?dataset.stop_reason:'';
 if(dataset.status==='saved_capture_error'||dataset.status==='saved_cleanup_error')
  return `录制异常结束，不是完整成功数据。${detail?`原因：${detail}。`:''}${reason?`停止标记：${reason}。`:''}已有帧可供诊断；请先验证执行已停止，再创建恢复副本。`;
 if(dataset.status==='recording')
  return '此录制尚无正常结束确认；recording 标记不能证明任务仍在运行。已有帧不代表完整录制。';
 if(reason==='quota_unknown')
  return `采集配额无法确认，录制被保护性停止；不是已确认达到容量上限，也不是完整成功数据。请检查配额配置和目录可读性，结合执行记录及数据质量报告判断已有帧。${detail}`;
 if(dataset.status==='saved_limit')
  return `录制达到限制后停止，不代表预定采集全部完成。${reason?`停止标记：${reason}。`:''}${detail}`;
 if(detail)return `录制记录包含错误：${detail}。请先检查数据质量，不要仅凭保存状态判断成功。`;
 if(dataset.status==='saved')return '样本已保存；saved 仅描述录制保存状态，不证明评测通过或 CARLA 正常退出。请结合对应执行记录和数据质量报告判断。';
 return null;
}

export function captureQuotaSummary(value:unknown):string {
 if(value===undefined||value===null)return '此历史录制未保存配额策略，不能用当前配置推断当时上限。';
 if(typeof value!=='object'||Array.isArray(value))return '录制配额策略格式异常，无法确认当时上限。';
 const policy=value as Record<string,unknown>;
 if(policy.schema_version!=='capture-quota-policy/1'||!['default','environment'].includes(String(policy.source))||
    policy.measurement!=='allocated_file_blocks_in_manifest_directories')return '录制配额策略格式异常，无法确认当时上限。';
 if(policy.valid===false&&policy.limit_bytes===null)return '录制开始时配额配置无效，未确认有效容量上限。';
 if(policy.valid!==true||typeof policy.limit_bytes!=='number'||!Number.isSafeInteger(policy.limit_bytes)||policy.limit_bytes<=0)
  return '录制配额策略格式异常，无法确认当时上限。';
 return `录制时采集目录上限：${(policy.limit_bytes/1024**3).toLocaleString('zh-CN',{maximumFractionDigits:2})} GiB · 来源：${policy.source==='default'?'默认配置':'环境配置'}。仅统计带 manifest 的录制目录文件块，不是文件系统硬配额，也不代表当前剩余容量。`;
}
