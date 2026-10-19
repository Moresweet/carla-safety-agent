import {batchApi} from './batchApi';

export async function setRecording(recording:boolean,every:number,transport:typeof fetch=fetch){
 if(typeof recording!=='boolean'||(recording&&(!Number.isInteger(every)||every<1||every>100))){
  throw Error('采样间隔必须是 1 到 100 的整数。');
 }
 const value=await batchApi<{session:{run_id:string;state:string}}>('/session/status',undefined,transport);
 if(value.session?.state!=='running'||typeof value.session.run_id!=='string'||!value.session.run_id){
  throw Error('没有正在运行的采集或评测任务，请刷新状态。');
 }
 const result=await batchApi<{request:{execution_id:string;recording:boolean}}>('/collection/recording',
  {run_id:value.session.run_id,recording,...(recording?{every,max_frames:2000}:{})},transport);
 if(result.request?.execution_id!==value.session.run_id||result.request.recording!==recording){
  throw Error('录制响应身份不匹配，结果未确认；请核对状态，不要重复提交。');
 }
}
