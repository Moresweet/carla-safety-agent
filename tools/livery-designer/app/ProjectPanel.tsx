"use client";
import {useEffect,useState} from 'react';
import ExperimentHistory from './ExperimentHistory';
import ProjectBundlePanel from './ProjectBundlePanel';
import SceneHandoffPanel from './SceneHandoffPanel';
import SnapshotObjectRestore from './SnapshotObjectRestore';
import DeletionHistory from './DeletionHistory';
import EditorHistory from './EditorHistory';
const bridge='http://127.0.0.1:8765';
type Head={scene_id:string;name:string;version:string;cursor:number;history:string[];object_count:number};
type Health={ready:boolean;checks:{id:string;ok:boolean;detail?:string;map?:string}[];session:{state:string;error?:string}};
export default function ProjectPanel(){
 const [health,setHealth]=useState<Health|null>(null),[scenes,setScenes]=useState<Head[]>([]),[selected,setSelected]=useState(''),[name,setName]=useState('我的场景'),[status,setStatus]=useState(''),[busy,setBusy]=useState(false);
 const current=scenes.find(s=>s.scene_id===selected);
 const [objectVersion,setObjectVersion]=useState('');
 const selectedObjectVersion=current?.history.includes(objectVersion)?objectVersion:current?.version;
 // Versions are globally unique: an old selection falls back to the new scene head.
 // Do not reset in an effect: it would erase an explicitly selected deletion backup.
 async function refresh(){try{const [a,b]=await Promise.all([fetch(bridge+'/system/preflight'),fetch(bridge+'/scenes')]);if(!a.ok||!b.ok)throw new Error('服务检查失败');const h=await a.json() as Health,s=await b.json() as {scenes:Head[]};if(!h.session||!Array.isArray(h.checks)||!Array.isArray(s.scenes))throw new Error('后端版本尚未就绪，请刷新检查');setHealth(h);setScenes(s.scenes)}catch(e){setStatus(String(e))}}
 useEffect(()=>{void refresh()},[]);
 async function act(action:string){setBusy(true);try{const payload=action==='save'?{name,scene_id:selected||undefined,expected_version:current?.version}:action==='restore'?{scene_id:selected}:{scene_id:selected,direction:action==='undo'?-1:1,expected_version:current?.version};const r=await fetch(bridge+'/scenes/'+(action==='undo'||action==='redo'?'history':action),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const value=await r.json() as {error?:string;head:Head};if(!r.ok)throw new Error(value.error);setSelected(value.head.scene_id);setStatus(action==='save'?'场景版本已保存':'场景已合并恢复，无关对象保留');await refresh()}catch(e){setStatus(String(e))}finally{setBusy(false)}}
 async function recover(){setBusy(true);try{const r=await fetch(bridge+'/session/recover',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const v=await r.json() as {error?:string};if(!r.ok)throw new Error(v.error);await refresh()}catch(e){setStatus(String(e))}finally{setBusy(false)}}
 return <details className="project-panel"><summary>项目与场景版本 · {health?(health.ready?'最近预检通过':'最近预检需处理'):'检查中'} · 最近会话：{health?.session.state??'未知'}</summary><div className="project-panel-content">
  <p>预检结果与最近会话结果分别显示。历史失败不会被清除；预检是上次查询的快照，不是持续健康保证，可点击刷新重新核对。</p>
  <h2>运行检查</h2><button disabled={busy} onClick={()=>void refresh()}>刷新检查</button><ul>{health?.checks.map(c=><li key={c.id}>{c.ok?'通过':'需处理'} · {c.id} · {c.detail??c.map??''}</li>)}</ul>{health?.session.error&&<p role="alert">{health.session.error}</p>}{health?.session.state==='recovering'&&<button disabled={busy} onClick={recover}>重试恢复仿真</button>}
  <h2>场景保存与恢复</h2><p>保存用户新增对象、天气、观察视角、精准环境材质槽及本工作台设置的隐藏状态。同地图合并恢复，不删除无关对象；已纳管的环境材质与可见性恢复为选中版本。对象纹理目前纳入工作台新增 Audi A2 车身槽和 walker.pedestrian.0001 裤装槽 14；其他型号、旧式纹理及外部工具的隐藏操作尚未纳入版本。</p>
  <label>场景<select value={selected} onChange={e=>{setSelected(e.target.value);setName(scenes.find(s=>s.scene_id===e.target.value)?.name??'我的场景')}}><option value="">新建场景文档</option>{scenes.map(s=><option key={s.scene_id} value={s.scene_id}>{s.name} · {s.object_count} 个对象</option>)}</select></label><label>名称<input value={name} maxLength={120} onChange={e=>setName(e.target.value)}/></label>
  <div className="project-actions"><button disabled={busy||!health?.ready} onClick={()=>act('save')}>保存新版本</button><button disabled={busy||!current||!health?.ready} onClick={()=>act('restore')}>恢复选中版本</button><button disabled={busy||!current||current.cursor===0||!health?.ready} onClick={()=>act('undo')}>恢复上一版本</button><button disabled={busy||!current||current.cursor>=current.history.length-1||!health?.ready} onClick={()=>act('redo')}>恢复下一版本</button></div><p role="status">{status}</p>
 <ProjectBundlePanel sceneId={selected}/>
 {current&&<label>单对象恢复来源版本<select aria-label="单对象恢复来源版本" disabled={busy} value={selectedObjectVersion} onChange={e=>setObjectVersion(e.target.value)}>{current.history.map((version,index)=><option key={version} value={version}>版本 {index+1} · {version}{version===current.version?'（当前）':''}</option>)}</select></label>}
 <EditorHistory onRestore={selection=>{setSelected(selection.scene_id);setObjectVersion(selection.version);setStatus('已选择副本删除前备份，请在单对象恢复区核对稳定ID：'+selection.stable_id);void refresh()}}/>
 <DeletionHistory onSelect={selection=>{setSelected(selection.scene_id);setObjectVersion(selection.version);setStatus('已选择删除备份，请核对稳定ID：'+selection.stable_id);void refresh()}}/>
 <SnapshotObjectRestore key={'object-restore:'+selected+':'+selectedObjectVersion} sceneId={selected} version={selectedObjectVersion} disabled={busy||!health?.ready}/>
 <SceneHandoffPanel key={'handoff:'+selected+':'+current?.version} sceneId={selected} version={current?.version} onSelect={id=>{setSelected(id);void refresh()}}/>
 <ExperimentHistory onSaved={(id,newName)=>{setSelected(id);setName(newName);void refresh()}}/>
 </div></details>
}
