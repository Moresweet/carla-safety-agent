"use client";
import {useEffect,useState} from 'react';
import {readAssetHistory,type AssetAttempt as Attempt} from './assetHistoryRequest';
const labels:Record<string,string>={preparing:'准备记录',importing:'导入未确认结束',registered:'已登记',needs_attention:'需要处理',generating:'生成未确认结束',exported:'已导出，未确认注册'};
export default function AssetImportHistory({generation=false,onReopen,disabled=false}:{generation?:boolean;onReopen?:(job:string)=>void;disabled?:boolean}){
 const [attempts,setAttempts]=useState<Attempt[]>([]),[error,setError]=useState('');
 useEffect(()=>{const abort=new AbortController();let active=false;
  const refresh=async()=>{if(active)return;active=true;try{
   const attempts=await readAssetHistory(generation,abort.signal);
   if(!abort.signal.aborted){setAttempts(attempts);setError('')}
  }catch(e){if(!abort.signal.aborted)setError(String(e))}finally{active=false}};
  void refresh();const timer=setInterval(refresh,3000);return()=>{abort.abort();clearInterval(timer)};
 },[generation]);
 return <section className="asset-import-history"><h3>{generation?'持久化 Blender 生成记录':'持久化导入记录'}</h3>
  <p>{generation?'生成失败保留任务目录与报告，不自动重试或删除。生成未确认结束也可能是桥接中断；不得据此重复执行。导出不等于已注册到 CARLA。':'仅正常退出并核对身份后登记。失败资产保留在记录目录，不自动重试或删除；“导入未确认结束”也可能是进程中断，需要查看日志。'}</p>
  {error&&<p role="alert">刷新失败，下面可能是旧记录：{error}</p>}
  {!attempts.length&&!error?<p>尚无新版{generation?'生成':'导入'}记录；旧资产仍保留。</p>:attempts.map(item=><details key={item.attempt_id}>
   <summary>{labels[item.state]??item.state} · {item.job_id} · {new Date(item.started_at*1000).toLocaleString()}</summary>
   <p>目标：{item.destination??'尚未启动 Unreal'}</p>{item.error&&<p role="alert">{item.error}</p>}
   {item.observation&&<p role={item.observation.requires_attention?'alert':undefined}>协调进程：{({present:'仍存在（不代表任务有进展）',exited:'已退出，结果待检查',unknown:'无法确认'} as Record<string,string>)[item.observation.coordinator]??'无法确认'}。Blender/Unreal 子进程状态未确认，不可据此重复执行。{item.observation.error}</p>}
   <p>报告：{item.report_path}</p>
   {generation&&item.state==='exported'&&onReopen&&<button disabled={disabled} onClick={()=>onReopen(item.job_id)}>重新打开导出结果（不执行导入）</button>}
   {item.registration_observation&&<p>注册表核对：{({matching:'存在与本次尝试匹配的登记',absent:'未找到本次尝试的登记',conflict:'登记身份冲突',unknown:'注册表无法读取'} as Record<string,string>)[item.registration_observation.state]??'无法确认'}。仅核对登记，不代表 Unreal 资产或场景对象已验证，不自动重试。{item.registration_observation.error}</p>}
  </details>)}
 </section>;
}
