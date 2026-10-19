export function executionSummaryText(raw:unknown):string{
 const unavailable='对应执行记录不可用，不能从录制保存状态推断执行成功。';
 if(!raw||typeof raw!=='object'||Array.isArray(raw))return unavailable;
 const value=raw as Record<string,unknown>;
 if(value.available!==true)return unavailable;
 const labels:Record<string,string>={idle:'空闲',preparing:'准备中',running:'运行中',stopping:'停止中',recovering:'恢复中',completed:'已完成',stopped:'已停止',failed:'失败'};
 if(typeof value.state!=='string'||!Object.hasOwn(labels,value.state)||
    typeof value.execution_id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(value.execution_id)||
    (value.error!==null&&value.error!==undefined&&typeof value.error!=='string'))return unavailable;
 return `对应执行记录：${labels[value.state]}（${value.state}） · ${value.execution_id}。${value.error?`记录原因：${value.error}。`:''}这是保存的本地状态，不是当前进程存活证明，也不是驾驶质量评分。`;
}
