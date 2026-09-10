"use client";
import {useEffect,useRef,useState} from 'react';
type Scene={scene_id:string;name:string;history:string[];version?:string};
type Review={review_token:string;expires_in_s:number;map:string;episode:string;create_count:number;update_count:number;preserved_user_objects:number;weather_fields:string[];camera_changed:boolean;material_state_replaced:boolean;actor_material_state_replaced:boolean;actor_material_count:number;visibility_state_replaced:boolean};
export default function BundleRestorePanel({bundleId,scenes,disabled,onBusy}:{bundleId:string;scenes:Scene[];disabled:boolean;onBusy:(busy:boolean)=>void}){
 const initial=scenes[0];
 const [selection,setSelection]=useState(initial?initial.scene_id+'/'+(initial.version??initial.history[0]):'');
 const [review,setReview]=useState<Review|null>(null),[confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState('');
 const active=useRef(false);
 useEffect(()=>{if(!review)return;const timer=setTimeout(()=>{setReview(null);setConfirmed(false);setStatus('恢复预览已过期，请重新预览。')},review.expires_in_s*1000);return()=>clearTimeout(timer)},[review]);
 async function run(apply:boolean){
  if(active.current||disabled||!selection||(apply&&(!review||!confirmed)))return;
  const [scene_id,version]=selection.split('/');
  const body=apply?{review_token:review!.review_token,confirmed:true}:{bundle_id:bundleId,scene_id,version};
  active.current=true;onBusy(true);setError('');setReview(null);setConfirmed(false);
  setStatus(apply?'正在保存恢复前快照并恢复实景；不要重复提交。':'正在读取恢复范围，不修改实景。');
  try{
   const response=await fetch('http://127.0.0.1:8765/projects/bundle/'+(apply?'restore-confirm':'restore-preview'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   const value=await response.json() as Review&{ok:boolean;error?:string;spawned:number;restored:number;backup:{scene_id:string;version:string}};if(!response.ok||!value.ok)throw Error(value.error??'恢复操作未成功');
   if(apply){setStatus(`实景已同地图合并恢复：新增 ${value.spawned}，目标对象 ${value.restored}。恢复前快照：${value.backup.scene_id} / ${value.backup.version}。包内历史未安装到当前目录；如需保留当前效果，请保存新场景。`)}
   else {setReview(value as Review);setStatus('范围预览完成；实际依赖和原生属性仍在执行前检查。')}
  }catch(e){setError(String(e));setStatus(apply?'恢复未确认成功；请先检查错误及恢复前快照，再重新预览。不会自动重试。':'预览失败；未执行恢复。')}
  finally{active.current=false;onBusy(false)}
 }
 return <section aria-label="项目包实景恢复">
  <h3>可选：恢复到当前实景</h3>
  <p>这会修改正在运行的场景，与隔离导入不同。仅支持当前同名地图，不自动安装或注册源资产。对象纹理版本支持工作台新增 Audi A2 车身槽和 walker.pedestrian.0001 裤装槽 14；其他型号及旧式纹理未纳入版本。</p>
  <label>包内场景版本<select aria-label="包内恢复版本" disabled={disabled} value={selection} onChange={e=>{setSelection(e.target.value);setReview(null);setConfirmed(false);setError('');setStatus('')}}>
   {scenes.flatMap(scene=>scene.history.map(version=><option key={scene.scene_id+'/'+version} value={scene.scene_id+'/'+version}>{scene.name} · {version}{version===scene.version?'（当前版本）':''}</option>))}
  </select></label>
  <button disabled={disabled||!selection} onClick={()=>void run(false)}>预览实景恢复范围</button>
  {review&&<div aria-label="实景恢复范围">
   <p>{review.map} · 世界 {review.episode} · 120 秒有效，场景变化后须重做预览</p>
   <p>创建 {review.create_count} 个对象 · 更新 {review.update_count} 个对象 · 保留其他 {review.preserved_user_objects} 个用户对象</p>
   <p>天气字段：{review.weather_fields.join('、')||'不修改'}；相机：{review.camera_changed?'修改':'不修改'}</p>
   <p>已纳管环境材质：{review.material_state_replaced?'整体恢复为选中版本（可能清除当前覆盖）':'保持'}；已纳管可见性：{review.visibility_state_replaced?'整体恢复为选中版本':'保持'}。</p>
   <p>目标对象纹理：{review.actor_material_state_replaced?`恢复 ${review.actor_material_count} 个已纳管槽位；可能清除目标对象当前覆盖，无关对象保持不变`:'旧版本未记录，保持当前覆盖'}。</p>
   <label><input aria-label="确认实景恢复" type="checkbox" checked={confirmed} disabled={disabled} onChange={e=>setConfirmed(e.target.checked)}/>确认上述实景修改；先保存恢复前快照，不删除无关对象</label>
   <button disabled={disabled||!confirmed} onClick={()=>void run(true)}>确认恢复当前实景</button>
  </div>}
  {error&&<p role="alert">{error}</p>}<p role="status">{status}</p>
 </section>;
}
