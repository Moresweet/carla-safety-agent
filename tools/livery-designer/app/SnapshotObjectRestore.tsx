"use client";
import {useEffect,useRef,useState} from 'react';
import {snapshotObjects,type SnapshotObject} from './snapshotObjects';
import {restoreObjectRequest} from './restoreObjectRequest';
const bridge='http://127.0.0.1:8765';

export default function SnapshotObjectRestore({sceneId,version,disabled}:{sceneId:string;version?:string;disabled:boolean}){
 const [objects,setObjects]=useState<SnapshotObject[]>([]),[selected,setSelected]=useState('');
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState('');
 const active=useRef(false);
 useEffect(()=>{
  const controller=new AbortController();let alive=true;
  setObjects([]);setSelected('');setConfirmed(false);setStatus('');
  if(!sceneId||!version)return()=>controller.abort();
  const timer=setTimeout(()=>controller.abort(),15000);
  void (async()=>{try{
   const r=await fetch(`${bridge}/scenes/document?scene_id=${encodeURIComponent(sceneId)}&version=${encodeURIComponent(version)}`,{signal:controller.signal});
   const value=await r.json() as {ok?:boolean;error?:string};if(!r.ok||value?.ok!==true)throw Error(value?.error??'快照读取失败');
   const rows=snapshotObjects(value);if(alive)setObjects(rows);
  }catch(e){if(alive)setStatus('无法读取快照对象：'+String(e))}finally{clearTimeout(timer)}})();
  return()=>{alive=false;clearTimeout(timer);controller.abort()};
 },[sceneId,version]);
 async function restore(){
  if(active.current||!confirmed||!selected||!version||disabled)return;
  active.current=true;setBusy(true);setConfirmed(false);setStatus('正在恢复指定对象…');
  try{
   const actorId=await restoreObjectRequest({scene_id:sceneId,version,stable_id:selected},true);
   setStatus(`指定对象恢复已确认，运行时 ID ${actorId}。再次恢复同一已存在对象会被拒绝，不会覆盖它。`);
  }catch(e){setStatus(String(e))}
  finally{active.current=false;setBusy(false)}
 }
 return <section aria-label="从历史快照恢复单对象">
  <h3>从此快照恢复单个缺失对象</h3>
  <p>不回退其他对象、天气、相机和环境材质；仅恢复选中对象及已记录的受支持材质。对象已存在、地图不一致或任务运行中会拒绝操作。</p>
  <p>版本：{version??'未选择'}</p>
  <select aria-label="历史快照对象" disabled={busy||disabled||!objects.length} value={selected} onChange={e=>{setSelected(e.target.value);setConfirmed(false)}}>
   <option value="">选择需要恢复的对象</option>{objects.map(o=><option key={o.stable_id} value={o.stable_id}>{o.blueprint_id} · {o.stable_id}</option>)}
  </select>
  <label><input type="checkbox" disabled={busy||disabled||!selected} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>确认仅恢复选中的缺失对象</label>
  <button disabled={busy||disabled||!selected||!confirmed} onClick={()=>void restore()}>从快照恢复此对象</button>
  <p role="status">{status}</p>
 </section>;
}
