"use client";
import {useRef,useState} from 'react';
const bridge='http://127.0.0.1:8765';
type Bundle={bundle_id:string;archive:string;download_url:string;scenes:{scene_id:string;name:string;history:string[]}[];manifest:{files:Record<string,unknown>;dependencies:{maps:string[];blueprints:string[];material_slots:unknown[];generated_asset_sources?:Record<string,string>;model_ids?:string[]}}};
export default function ProjectBundlePanel({sceneId}:{sceneId:string}){
 const [bundle,setBundle]=useState<Bundle|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState(''),[confirmed,setConfirmed]=useState(false),[previews,setPreviews]=useState(false);
 const active=useRef(false);
 async function execute(path:string,body:BodyInit,contentType='application/json'){
  if(active.current)return;active.current=true;setBusy(true);setError('');setStatus('正在校验与处理；不会改动当前仿真场景。');
  try{
   const response=await fetch(bridge+path,{method:'POST',headers:{'Content-Type':contentType},body});
   const result=await response.json() as Bundle&{ok?:boolean;error?:string;directory?:string};if(!response.ok||!result.ok)throw new Error(result.error??'项目包处理失败');
   if(result.directory){setStatus('已隔离导入到：'+result.directory+'。尚未检查运行依赖，也未注册到 Unreal 或恢复当前场景。');setConfirmed(false)}
   else {setBundle(result as Bundle);setConfirmed(false);setStatus('文件结构与校验和通过；依赖可用性尚未检查。')}
  }catch(e){setError(String(e));setStatus('操作未确认完成；请勿因超时重复导入。')}
  finally{active.current=false;setBusy(false)}
 }
 const dependencies=bundle?.manifest.dependencies;
 return <section aria-label="项目打包迁移" className="bundle-panel">
  <h2>项目包 · 导出与隔离导入</h2>
  <p>导出上方选中场景的全部保存版本和引用纹理，可附带精准材质预览。当前图形导出不包含 Blender 源资产包、模型引用、权重、采集数据或源码；完整源资产与模型引用请使用项目打包命令行。</p>
  <label><input type="checkbox" checked={previews} disabled={busy} onChange={e=>setPreviews(e.target.checked)}/>包含引用材质的真实网格预览</label>
  <button disabled={busy||!sceneId} onClick={()=>void execute('/projects/bundle/export',JSON.stringify({scene_ids:[sceneId],include_material_previews:previews}))}>导出选中场景包</button>
  <label>上传并检查项目 ZIP（最多 16 MiB；更大文件使用命令行）<input type="file" accept=".zip,application/zip" disabled={busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(file.size>16*1024*1024){setError('文件超过浏览器16 MiB限制，请使用命令行导入。');return}void execute('/projects/bundle/upload',file,'application/zip')}}/></label>
  {error&&<p role="alert">{error}</p>}<p role="status">{status}</p>
  {bundle&&dependencies&&<div className="bundle-details">
   <h3>已验证文件的项目包</h3><p>包 ID：{bundle.bundle_id}</p>
   <p>{bundle.scenes.length} 个场景 · {Object.keys(bundle.manifest.files).length} 个文件 · {dependencies.maps.length} 张地图引用 · {dependencies.blueprints.length} 个 Blueprint 引用 · {dependencies.material_slots.length} 个材质槽引用</p>
   <ul>{bundle.scenes.map(scene=><li key={scene.scene_id}>{scene.name} · {scene.history.length} 个版本</li>)}</ul>
   <p>内含生成资产源包：{Object.keys(dependencies.generated_asset_sources??{}).length}；模型引用：{dependencies.model_ids?.length??0}。引用不代表本机运行依赖已可用。</p>
   <a href={bridge+bundle.download_url}>下载已校验 ZIP</a>
   <p>隔离导入只创建 data/imported-projects 下的新目录，不覆盖当前项目、不执行包中脚本、不切换地图。包中源资产仍须显式导入 Unreal。</p>
   <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>确认创建隔离项目目录，不直接恢复实景</label>
   <button disabled={busy||!confirmed} onClick={()=>void execute('/projects/bundle/import',JSON.stringify({bundle_id:bundle.bundle_id,confirmed:true}))}>隔离导入已检查项目包</button>
  </div>}
 </section>;
}
