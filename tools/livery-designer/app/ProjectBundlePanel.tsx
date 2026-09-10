"use client";
import {useRef,useState} from 'react';
import BundleRestorePanel from './BundleRestorePanel';
import BundleRegistrationPanel from './BundleRegistrationPanel';
const bridge='http://127.0.0.1:8765';
type Bundle={bundle_id:string;archive:string;download_url:string;scenes:{scene_id:string;name:string;history:string[]}[];manifest:{files:Record<string,unknown>;dependencies:{maps:string[];blueprints:string[];material_slots:unknown[];generated_asset_sources?:Record<string,string>;model_ids?:string[]}}};
type Diagnostic={bundle_id:string;observed_at:number;episode:string;current_map:string;all_declared_dependencies_available:boolean;checks:{kind:string;reference:string|string[];state:string;reason?:string}[]};
export default function ProjectBundlePanel({sceneId}:{sceneId:string}){
 const [bundle,setBundle]=useState<Bundle|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState(''),[confirmed,setConfirmed]=useState(false),[previews,setPreviews]=useState(false);
 const active=useRef(false);
 const [sources,setSources]=useState(false),[reference,setReference]=useState<unknown|null>(null),[referenceName,setReferenceName]=useState('');
 const [diagnostic,setDiagnostic]=useState<Diagnostic|null>(null);
 async function execute(path:string,body:BodyInit,contentType='application/json'){
  if(active.current)return;active.current=true;setBusy(true);setError('');setStatus('正在校验与处理；不会改动当前仿真场景。');
  try{
   const response=await fetch(bridge+path,{method:'POST',headers:{'Content-Type':contentType},body});
   const result=await response.json() as Bundle&{ok?:boolean;error?:string;directory?:string};if(!response.ok||!result.ok)throw new Error(result.error??'项目包处理失败');
   if(result.directory){setStatus('已隔离导入到：'+result.directory+'。导入目录尚未配置运行环境，也未注册到 Unreal 或恢复当前场景。');setConfirmed(false)}
   else {setBundle(result as Bundle);setDiagnostic(null);setConfirmed(false);setStatus('文件结构与校验和通过；依赖可用性尚未检查。')}
  }catch(e){setError(String(e));setStatus('操作未确认完成；请勿因超时重复导入。')}
  finally{active.current=false;setBusy(false)}
 }
 async function checkDependencies(){
  if(!bundle||active.current)return;active.current=true;setBusy(true);setError('');setDiagnostic(null);
  try{
   const response=await fetch(bridge+'/projects/bundle/doctor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bundle_id:bundle.bundle_id})});
   const result=await response.json() as Diagnostic&{error?:string};if(!response.ok)throw new Error(result.error??'依赖检查失败');
   if(result.bundle_id!==bundle.bundle_id||!Array.isArray(result.checks))throw new Error('依赖检查身份不匹配');
   setDiagnostic(result);setStatus('依赖检查完成；没有切换地图或生成对象。检查结果仅代表这个时间点，不是恢复实景验收。');
  }catch(e){setError(String(e));setStatus('依赖检查未完成；有仿真任务时请等待其结束。')}
  finally{active.current=false;setBusy(false)}
 }
 const dependencies=bundle?.manifest.dependencies;
 async function openRegistered(id:string){
  setBusy(true);setError('');
  try{const r=await fetch(bridge+'/projects/bundle?bundle_id='+encodeURIComponent(id)),v=await r.json() as Bundle&{error?:string};if(!r.ok)throw Error(v.error??'新项目包不可用');setBundle(v);setDiagnostic(null);setConfirmed(false);setStatus('已打开新注册引用的项目包；实景未修改，仍需单独预览并确认恢复。')}
  catch(e){setError(String(e))}finally{setBusy(false)}
 }
 return <section aria-label="项目打包迁移" className="bundle-panel">
  <h2>项目包 · 导出与隔离导入</h2>
  <p>导出上方选中场景的全部保存版本和引用纹理，可附带精准材质预览、已登记 Blender 源文件及模型文件校验引用。不包含权重、采集数据、源码、Unreal 编译资产或 Python/CUDA 环境。</p>
  <label><input type="checkbox" checked={previews} disabled={busy} onChange={e=>setPreviews(e.target.checked)}/>包含引用材质的真实网格预览</label>
  <label><input type="checkbox" checked={sources} disabled={busy} onChange={e=>setSources(e.target.checked)}/>包含历史版本引用的全部已登记 Blender 源资产</label>
  <p>源文件必须仍位于本项目的 Blender 任务目录；缺失、旧目录或材质参数不明确时会拒绝导出，不悄悄省略。源包不等于已经在目标机器注册。</p>
  <label>可选模型引用 JSON（最多 1 MiB；只包含文件路径别名与校验和）<input aria-label="模型引用 JSON" type="file" accept=".json,application/json" disabled={busy} onChange={e=>{
   const file=e.target.files?.[0];e.target.value='';if(!file||active.current)return;
   if(file.size>1024*1024){setError('模型引用超过1 MiB');return}
   active.current=true;setBusy(true);setError('');setReference(null);setReferenceName('');
   void file.text().then(text=>{const value:unknown=JSON.parse(text);if(!value||typeof value!=='object'||!('schema_version' in value)||value.schema_version!=='carla-runtime-reference/1')throw Error('不是模型文件引用格式');setReference(value);setReferenceName(file.name)})
    .catch(e=>setError(String(e))).finally(()=>{active.current=false;setBusy(false)});
  }}/></label>
  {referenceName&&<p>待附加：{referenceName} · 导出时校验结构，未重新读取或核验本机权重。<button disabled={busy} onClick={()=>{setReference(null);setReferenceName('')}}>移除模型引用</button></p>}
  <button disabled={busy||!sceneId} onClick={()=>void execute('/projects/bundle/export',JSON.stringify({scene_ids:[sceneId],include_material_previews:previews,include_generated_sources:sources,runtime_reference:reference}))}>导出选中场景包</button>
  <label>上传并检查项目 ZIP（最多 16 MiB；更大文件使用命令行）<input aria-label="项目 ZIP" type="file" accept=".zip,application/zip" disabled={busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(file.size>16*1024*1024){setError('文件超过浏览器16 MiB限制，请使用命令行导入。');return}void execute('/projects/bundle/upload',file,'application/zip')}}/></label>
  {error&&<p role="alert">{error}</p>}<p role="status">{status}</p>
  {bundle&&dependencies&&<div className="bundle-details">
   <h3>已验证文件的项目包</h3><p>包 ID：{bundle.bundle_id}</p>
   <p>{bundle.scenes.length} 个场景 · {Object.keys(bundle.manifest.files).length} 个文件 · {dependencies.maps.length} 张地图引用 · {dependencies.blueprints.length} 个 Blueprint 引用 · {dependencies.material_slots.length} 个材质槽引用</p>
   <ul>{bundle.scenes.map(scene=><li key={scene.scene_id}>{scene.name} · {scene.history.length} 个版本</li>)}</ul>
   <p>内含生成资产源包：{Object.keys(dependencies.generated_asset_sources??{}).length}；模型引用：{dependencies.model_ids?.length??0}。引用不代表本机运行依赖已可用。</p>
   <a href={bridge+bundle.download_url}>下载已校验 ZIP</a>
   <div><button disabled={busy} onClick={()=>void checkDependencies()}>检查本机依赖（不切换地图）</button></div>
   {diagnostic&&<div aria-label="项目包依赖检查">
    <p>{diagnostic.all_declared_dependencies_available?'已检查的全部声明依赖可用；尚未验证实景恢复。':'存在缺失或尚未检查的依赖。'} · {new Date(diagnostic.observed_at*1000).toLocaleString()} · {diagnostic.current_map}</p>
    <ul>{diagnostic.checks.map((check,i)=><li key={i}>{({available:'可用',missing:'缺失',not_checked:'未检查'} as Record<string,string>)[check.state]??check.state} · {check.kind} · {Array.isArray(check.reference)?check.reference.join(' / '):check.reference}{check.reason&&<p>{check.reason}</p>}</li>)}</ul>
    <p>生成资产别名与模型文件需要单独验证；包中源文件不等于完成 Unreal 注册。非当前地图的材质不自动切图检查。</p>
   </div>}
   <p>隔离导入只创建 data/imported-projects 下的新目录，不覆盖当前项目、不执行包中脚本、不切换地图。包中源资产仍须显式导入 Unreal。</p>
   <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>确认创建隔离项目目录，不直接恢复实景</label>
   <button disabled={busy||!confirmed} onClick={()=>void execute('/projects/bundle/import',JSON.stringify({bundle_id:bundle.bundle_id,confirmed:true}))}>隔离导入已检查项目包</button>
   {!!Object.keys(dependencies.generated_asset_sources??{}).length&&<BundleRegistrationPanel key={'register:'+bundle.bundle_id} bundleId={bundle.bundle_id} count={Object.keys(dependencies.generated_asset_sources??{}).length} disabled={busy} onBusy={setBusy} onRegistered={id=>void openRegistered(id)}/>}
   <BundleRestorePanel key={'restore:'+bundle.bundle_id} bundleId={bundle.bundle_id} scenes={bundle.scenes} disabled={busy} onBusy={setBusy}/>
  </div>}
 </section>;
}
