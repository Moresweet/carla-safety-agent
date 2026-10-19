"use client";
import {useEffect,useRef,useState} from 'react';
import {parseEditorHistory,type EditorHistoryData} from './editorHistoryData';
import CopyUndo from './CopyUndo';
import CopyRedo from './CopyRedo';
import MaterialHistoryAction from './MaterialHistoryAction';
import MaterialInspection from './MaterialInspection';
import type {ObjectRestoreSelection} from './deletionResult';
const kinds:Record<string,string>={transform:'位置变换','transform-intent':'未结变换操作',delete:'删除',copy:'复制（显示源对象）',material:'环境材质槽','actor-material':'车辆/行人材质槽'};
const states:Record<string,string>={applied:'已应用',undone:'已撤销',attempting:'操作结果待检查',needs_attention:'需要检查',confirmed:'操作已确认',undo_attempting:'撤销结果待检查',undo_needs_attention:'撤销需要检查',redo_attempting:'重做结果待检查',redo_needs_attention:'重做需要检查'};
export default function EditorHistory({onRestore}:{onRestore:(selection:ObjectRestoreSelection)=>void}){
 const [data,setData]=useState<EditorHistoryData|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const request=useRef<AbortController|null>(null);
 const recoveries=useRef(new Set<string>());
 const [recovering,setRecovering]=useState(false);
 const [lookup,setLookup]=useState(''),[lookupActor,setLookupActor]=useState(false);
 const [selectedLookup,setSelectedLookup]=useState<{id:string;actor:boolean}|null>(null);
 function recoveryPending(operation:string,pending:boolean){
  if(pending)recoveries.current.add(operation);else recoveries.current.delete(operation);
  setRecovering(recoveries.current.size>0);
 }
 useEffect(()=>()=>request.current?.abort(),[]);
 async function refresh(){
  if(recoveries.current.size)return;
  request.current?.abort();const controller=new AbortController();request.current=controller;
  const timer=setTimeout(()=>controller.abort(),10000);
  setBusy(true);setError('');setData(null);
  try{
   const response=await fetch('http://127.0.0.1:8765/objects/edit-history?limit=200',{signal:controller.signal});
   if(!response.ok)throw Error('编辑历史读取失败：HTTP '+response.status);
   const value=parseEditorHistory(await response.json());
   if(request.current===controller&&!controller.signal.aborted)setData(value);
  }catch(e){if(request.current===controller)setError(controller.signal.aborted?'读取超时或已取消，请重试':String(e))}
  finally{clearTimeout(timer);if(request.current===controller){request.current=null;setBusy(false)}}
 }
 return <details className="deletion-history"><summary>统一编辑历史</summary>
  <p>展示当前变换链、删除、本地复制、精确环境材质槽及受管车辆/行人已支持槽的新增纹理日志，不代表对象当前状态。旧操作、评测中的复制、其他纹理入口和已归档变换分支尚未纳入；完整统一撤销重做尚未开放。材质记录确认表示调用与引用保存完成，不代表实景视觉验收。</p>
  <button disabled={busy||recovering} onClick={()=>void refresh()}>{recovering?'材质恢复请求处理中，暂不刷新历史':busy?'读取中…':'读取编辑历史'}</button>
  <fieldset disabled={recovering} style={{display:'flex',flexDirection:'column',gap:12,marginTop:12}}>
   <legend>按材质操作 ID 检查（不受列表 200 条限制）</legend>
   <label>操作 ID <input style={{display:'block',width:'100%',maxWidth:480,boxSizing:'border-box',padding:10,border:'1px solid #64748b',borderRadius:6}} value={lookup} onChange={event=>setLookup(event.target.value)} placeholder="粘贴错误提示中的 32 位操作 ID" maxLength={32}/></label>
   <label><input type="checkbox" checked={lookupActor} onChange={event=>setLookupActor(event.target.checked)}/>车辆／行人材质（环境材质不勾选）</label>
   <button disabled={!/^[a-f0-9]{32}$/.test(lookup.trim())} onClick={()=>setSelectedLookup({id:lookup.trim(),actor:lookupActor})}>选择此操作</button>
  </fieldset>
  {selectedLookup&&<section><p>已选择{selectedLookup.actor?'车辆／行人':'环境'}材质操作：{selectedLookup.id}。先只读检查，再决定是否显式恢复。</p>
   <MaterialInspection key={'direct:'+selectedLookup.actor+':'+selectedLookup.id} actor={selectedLookup.actor} operation={selectedLookup.id} onRecoveryPending={recoveryPending}/>
  </section>}
  {error&&<p role="alert">{error}</p>}
  {data&&<><p role="status">共 {data.total} 条，显示 {data.entries.length} 条{data.truncated?'（已截断）':''}。{!data.complete?'部分日志损坏或不可读，列表不完整。':''}</p>
   {data.warnings.map((warning,index)=><p role="alert" key={index}>{warning.source}：{warning.error}</p>)}
   {data.entries.filter(row=>!(selectedLookup&&row.operation_id===selectedLookup.id&&row.kind===(selectedLookup.actor?'actor-material':'material'))).map(row=><div className="deletion-history-entry" key={row.kind+':'+row.operation_id}>
    <span>{kinds[row.kind]} · {states[row.state]} · {row.type_id} · {row.material?'环境对象':'actor'} {row.actor_id}<br/>{row.material?'世界 episode':'稳定 ID'}：{row.stable_id}<br/>{row.created_at===null?'原记录无时间，置顶待检查':new Date(row.created_at*1000).toLocaleString()} · 操作 {row.operation_id}
    {row.material&&<><br/>组件 {row.material.component} · 槽 {row.material.slot}<br/>修改前：{row.material.before??'原材质（无工作台覆盖）'}<br/>修改后：{row.material.after??'原材质（无工作台覆盖）'}</>}</span>
    {row.actorMaterial&&<><p>组件 {row.actorMaterial.component} · 槽 {row.actorMaterial.slot}<br/>修改前：{row.actorMaterial.before??'原材质（无工作台覆盖）'}<br/>修改后：{row.actorMaterial.after??'原材质（无工作台覆盖）'}<br/>后台仍会核对当前对象身份和登记纹理；待检查操作不能重试，不支持自动故障恢复。</p>
     {row.actorMaterial.transitionSupported&&['confirmed','undone'].includes(row.state)&&<MaterialHistoryAction actor key={row.actorMaterial.revision} operation={row.operation_id} revision={row.actorMaterial.revision} direction={row.state==='undone'?'redo':'undo'} texture={row.state==='undone'?row.actorMaterial.after:row.actorMaterial.before} onDone={()=>void refresh()}/>}
     <MaterialInspection actor key={'actor-inspect:'+row.actorMaterial.revision} operation={row.operation_id} onRecoveryPending={recoveryPending}/>
     {!row.actorMaterial.transitionSupported&&<p>当前服务未声明此类撤销重做能力，仅展示记录。</p>}</>}
    {row.kind==='copy'&&row.state==='confirmed'&&row.target&&<CopyUndo operation={row.operation_id} target={row.target} onDone={()=>void refresh()}/>}
    {row.material&&<MaterialInspection key={'inspect:'+row.material.revision} operation={row.operation_id} onRecoveryPending={recoveryPending}/>}
    {row.material&&['confirmed','undone'].includes(row.state)&&<MaterialHistoryAction key={row.material.revision} operation={row.operation_id} revision={row.material.revision} direction={row.state==='undone'?'redo':'undo'} texture={row.state==='undone'?row.material.after:row.material.before} onDone={()=>void refresh()}/>}
    {row.recovery&&<div>{row.target&&row.deletion_id&&<CopyRedo key={row.deletion_id} operation={row.operation_id} deletion={row.deletion_id} target={row.target} backup={row.recovery} onDone={()=>void refresh()}/>}<p>也可选择备份转入单对象恢复；此备用入口不改写复制历史状态。</p><button disabled={busy} onClick={()=>onRestore(row.recovery!)}>选择副本恢复备份</button></div>}
   </div>)}
  </>}
 </details>
}
