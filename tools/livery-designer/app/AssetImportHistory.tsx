"use client";
import {useEffect,useState} from 'react';
type Attempt={attempt_id:string;job_id:string;state:string;destination?:string;error?:string;report_path:string;started_at:number};
const labels:Record<string,string>={preparing:'准备记录',importing:'导入未确认结束',registered:'已登记',needs_attention:'需要处理'};
export default function AssetImportHistory(){
 const [attempts,setAttempts]=useState<Attempt[]>([]),[error,setError]=useState('');
 useEffect(()=>{const abort=new AbortController();let active=false;
  const refresh=async()=>{if(active)return;active=true;try{
   const response=await fetch('http://127.0.0.1:8765/blender/imports',{signal:abort.signal}),data=await response.json() as {ok?:boolean;attempts?:Attempt[];error?:string};
   if(!response.ok||!data.ok||!Array.isArray(data.attempts))throw new Error(data.error??'导入记录不可用');
   if(!abort.signal.aborted){setAttempts(data.attempts);setError('')}
  }catch(e){if(!abort.signal.aborted)setError(String(e))}finally{active=false}};
  void refresh();const timer=setInterval(refresh,3000);return()=>{abort.abort();clearInterval(timer)};
 },[]);
 return <section className="asset-import-history"><h3>持久化导入记录</h3>
  <p>仅正常退出并核对身份后登记。失败资产保留在记录目录，不自动重试或删除；“导入未确认结束”也可能是进程中断，需要查看日志。</p>
  {error&&<p role="alert">刷新失败，下面可能是旧记录：{error}</p>}
  {!attempts.length&&!error?<p>尚无新版导入记录；旧资产仍保留在注册表。</p>:attempts.map(item=><details key={item.attempt_id}>
   <summary>{labels[item.state]??item.state} · {item.job_id} · {new Date(item.started_at*1000).toLocaleString()}</summary>
   <p>目标：{item.destination??'尚未启动 Unreal'}</p>{item.error&&<p role="alert">{item.error}</p>}
   <p>报告：{item.report_path}</p>
  </details>)}
 </section>;
}
