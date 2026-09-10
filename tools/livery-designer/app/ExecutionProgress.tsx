"use client";
import {useEffect,useState} from 'react';
type Progress={available:boolean;phase?:string;completed_steps?:number|null;total_steps?:number|null;age_s?:number;preview_remaining_s?:number|null;active?:boolean;reason?:string;invalid?:boolean};
type Status={session:{run_id:string|null;state:string;kind?:string;configuration?:{request?:{algorithm?:string}}};progress:Progress};
const labels:Record<string,string>={connecting:'连接仿真',loading_world:'加载目标地图',spawning:'创建测试对象',loading_model:'加载模型与权重',warming_sensors:'准备传感器与预热',inference:'闭环推理',preview:'推理已结束，保留实景供查看',cleaning:'清理本次执行资源',worker_finished:'工作进程清理结束，等待会话确认'};
export default function ExecutionProgress(){
 const [status,setStatus]=useState<Status|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  let alive=true,timer:ReturnType<typeof setTimeout>,controller:AbortController;
  async function poll(){
   controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
   try{const r=await fetch('http://127.0.0.1:8765/session/status',{signal:controller.signal});if(!r.ok)throw Error('阶段状态不可用');const value=await r.json() as Status;if(alive){setStatus(value);setError('')}}
   catch(e){if(alive)setError(String(e))}finally{clearTimeout(timeout);if(alive)timer=setTimeout(poll,1000)}
  }
  void poll();return()=>{alive=false;clearTimeout(timer);controller?.abort()};
 },[]);
 const progress=status?.progress,active=['preparing','running','stopping','recovering'].includes(status?.session.state??'');
 return <section aria-label="执行阶段" data-phase={progress?.available?progress.phase:'unavailable'} data-execution={status?.session.run_id??''} style={{padding:16,margin:'12px 0',border:'1px solid #354b60',borderRadius:12}}>
  <h3>执行阶段 · {status?.session.state??'读取中'}</h3>
  {status?.session.run_id&&<p style={{overflowWrap:'anywhere'}}>当前执行：{status.session.configuration?.request?.algorithm??status.session.kind??'未知类型'} · {status.session.run_id}</p>}
  {error?<p role="alert">{error}；不能据此判断任务已退出，请勿重复启动。</p>:progress?.available?<>
   <p role="status">{!active?'最后记录：':''}{labels[progress.phase??'']??'未知阶段'}</p>
   {progress.total_steps!=null&&progress.completed_steps!=null&&<p>已完成 {progress.completed_steps} / {progress.total_steps} 个计划仿真步；不是总运行时间百分比。</p>}
   {active&&progress.phase==='preview'&&<p>{(progress.preview_remaining_s??0)>0?`实景保留约剩 ${Math.ceil(progress.preview_remaining_s!)} 秒`:'实景保留期限已到，等待进程及资源清理确认'}。此阶段暂不推进新推理，仍占用仿真会话。</p>}
   <small style={{whiteSpace:'normal',overflow:'visible'}}>最近阶段报告距读取时 {Math.floor(progress.age_s??0)} 秒；这不是心跳或卡死判定。最终结果以会话结束和清理检查为准。</small>
  </>:<p>{status?.session.run_id?'当前执行尚无可验证的阶段报告；旧执行或其他后端可能不提供此信息。':'暂无执行。'}{progress?.invalid&&` 阶段数据无效：${progress.reason}`}</p>}
 </section>;
}
