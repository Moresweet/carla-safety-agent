"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import CarPreview,{MeshData} from './CarPreview';
import SurfaceTextureEditor from './SurfaceTextureEditor';
import {MaterialSlot,slotSupported,slotSupportLabel} from './materialSlotSupport';

const bridge='http://127.0.0.1:8765';
type Catalog={target:string;map:string;components:{component:string;slots:MaterialSlot[]}[]};
type Reply={ok?:boolean;error?:string};
export default function MaterialSlotEditor(props:{objectId:string|number;name:string}){
 return <TargetEditor key={String(props.objectId)} {...props}/>;
}
function TargetEditor({objectId,name}:{objectId:string|number;name:string}){
 const [catalog,setCatalog]=useState<Catalog|null>(null),[selection,setSelection]=useState(''),[mesh,setMesh]=useState<MeshData|null>(null);
 const [image,setImage]=useState<HTMLImageElement|null>(null),[revision,setRevision]=useState(0),[busy,setBusy]=useState(false);
 const [status,setStatus]=useState('读取真实材质槽…'),[sceneRevision,setSceneRevision]=useState(0),[reload,setReload]=useState(0),[showScene,setShowScene]=useState(false);
 const output=useRef<HTMLCanvasElement>(null),writeLock=useRef(false),imageRequest=useRef(0);
 const rendered=useCallback(()=>setRevision(v=>v+1),[]);
 const options=catalog?.components.flatMap(c=>c.slots.map(s=>({...s,component:c.component,key:JSON.stringify([c.component,s.slot])})))??[];
 const selected=options.find(o=>o.key===selection);
 const ready=!!selected&&slotSupported(selected)&&!!mesh;
 useEffect(()=>()=>{imageRequest.current++},[]);
 useEffect(()=>{
  const abort=new AbortController();setCatalog(null);setMesh(null);setSelection('');setStatus('读取真实材质槽…');
  fetch(`${bridge}/materials/catalog?object_id=${encodeURIComponent(objectId)}`,{signal:abort.signal})
   .then(async r=>{const data=await r.json() as Catalog & Reply;if(!r.ok||!data.ok)throw Error(data.error??'目录不可用');return data})
   .then(data=>{if(abort.signal.aborted)return;setCatalog(data);const c=data.components.find(c=>c.slots.some(slotSupported)),s=c?.slots.find(slotSupported);setSelection(c&&s?JSON.stringify([c.component,s.slot]):'');setStatus(s?'选择材质槽 → 上传或生成校准纹理 → 应用 → 查看实景':'此对象尚无可用真实 UV 导出；不使用通用网格替代。')})
   .catch(e=>{if(!abort.signal.aborted)setStatus(String(e))});
  return()=>abort.abort();
 },[objectId,reload]);
 useEffect(()=>{
  const abort=new AbortController();setMesh(null);
  if(!selected||!slotSupported(selected)||!catalog)return;
  fetch(`${bridge}/materials/mesh?${new URLSearchParams({map:catalog.map,file:selected.mesh_file!})}`,{signal:abort.signal})
   .then(async r=>{const data=await r.json() as MeshData & Reply;if(!r.ok)throw Error(data.error??'网格读取失败');if(!Array.isArray(data.vertices)||!data.vertices.length)throw Error('网格数据无效');return data})
   .then(data=>{if(!abort.signal.aborted){setMesh(data);setStatus('真实 UV0 网格已加载；纹理修改仅影响当前组件和槽。')}})
   .catch(e=>{if(!abort.signal.aborted)setStatus(String(e))});
  return()=>abort.abort();
 },[catalog,selection]);
 function loadImage(url:string,revoke=false){
  const request=++imageRequest.current,img=new Image();
  img.onload=()=>{if(request===imageRequest.current){setImage(img);setStatus('纹理草稿已加载，尚未应用到 CARLA')}if(revoke)URL.revokeObjectURL(url)};
  img.onerror=()=>{if(revoke)URL.revokeObjectURL(url);if(request===imageRequest.current)setStatus('图片无法解码')};img.src=url;
 }
 function calibration(){
  const canvas=document.createElement('canvas');canvas.width=canvas.height=1024;const ctx=canvas.getContext('2d');if(!ctx)return;
  for(let y=0;y<8;y++)for(let x=0;x<8;x++){ctx.fillStyle=(x+y)%2?'#e55acb':'#60dedc';ctx.fillRect(x*128,y*128,128,128);ctx.fillStyle='#101820';ctx.font='bold 24px sans-serif';ctx.fillText(`${x+1},${y+1}`,x*128+42,y*128+75)}
  ctx.fillStyle='#ff3838';ctx.fillRect(0,0,1024,40);ctx.fillStyle='#ffe044';ctx.fillRect(0,0,40,1024);ctx.fillStyle='#101820';ctx.font='bold 28px sans-serif';ctx.fillText('TOP / U →',370,30);
  loadImage(canvas.toDataURL('image/png'));
 }
 async function focus(){
  if(writeLock.current)return;writeLock.current=true;setBusy(true);
  try{const r=await fetch(bridge+'/focus/environment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({object_id:String(objectId)})});const result=await r.json() as Reply;if(!r.ok||!result.ok)throw Error(result.error??'聚焦失败');setShowScene(true);setSceneRevision(v=>v+1);setStatus('已聚焦当前对象；可对照实景检查纹理方向与重复情况')}
  catch(e){setStatus(String(e))}finally{writeLock.current=false;setBusy(false)}
 }
 async function apply(restore=false){
  if(!selected||!ready||writeLock.current||(!restore&&!image))return;writeLock.current=true;setBusy(true);
  try{
   const data={object_id:String(objectId),component:selected.component,slot:String(selected.slot)};
   const blob=restore?JSON.stringify(data):await new Promise<Blob>((resolve,reject)=>{const canvas=output.current;if(!canvas){reject(Error('纹理画布未就绪'));return}canvas.toBlob(b=>b?resolve(b):reject(Error('纹理编码失败')),'image/png')});
   const r=await fetch(`${bridge}/materials/${restore?'restore':'apply?'+new URLSearchParams(data)}`,{method:'POST',headers:{'Content-Type':restore?'application/json':'image/png'},body:blob});
   const result=await r.json() as Reply;if(!r.ok||!result.ok)throw Error(result.error??'操作失败');setStatus(restore?'已恢复原材质；左侧保留草稿，可再次应用':'已应用：单组件、单材质槽，UV0 映射');setShowScene(true);setSceneRevision(v=>v+1);
  }catch(e){setStatus(String(e))}finally{writeLock.current=false;setBusy(false)}
 }
 return <section className="material-slot-editor">
  <h2>{name} · 精准材质编辑</h2>
  <p>当前对象：{String(objectId)} · {options.filter(slotSupported).length} / {options.length} 个材质槽已具备编辑所需导出；不代表整类资产全部支持。</p>
  <button disabled={busy} onClick={()=>setReload(v=>v+1)}>重新读取材质目录</button><button disabled={busy} onClick={()=>void focus()}>聚焦此对象并查看实景</button>
  <details><summary>查看各材质槽的支持情况</summary><ul>{options.map(o=><li key={o.key}>{o.component} / {o.slot} · {o.name}：{slotSupportLabel(o)}</li>)}</ul>{!options.length&&<p>当前没有可列出的导出槽位，具体原因见下方状态。</p>}</details>
  <label>组件 / 材质槽 <select value={selection} disabled={busy} onChange={e=>{setMesh(null);setSelection(e.target.value)}}>{!selection&&<option value="">没有可编辑的材质槽</option>}{options.map(o=><option key={o.key} value={o.key} disabled={!slotSupported(o)}>{o.component} / {o.slot} · {o.name}{slotSupported(o)?'':'（暂不支持）'}</option>)}</select></label>
  <p>使用真实网格的 UV0。重复 UV 会重复纹理；这里修改基础颜色，不复制原材质的光照与凹凸效果。红边为纹理顶部、黄边为左侧；UV 岛本身可能旋转或镜像。</p>
  <label>上传纹理 <input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy||!ready} onChange={e=>{const file=e.target.files?.[0];if(file)loadImage(URL.createObjectURL(file),true)}}/></label><button disabled={busy||!ready} onClick={calibration}>生成 UV 校准棋盘格</button>
  <div className="material-slot-grid"><SurfaceTextureEditor image={image} output={output} onRender={rendered} label="UV0 纹理草稿" note="预览仅为当前槽真实几何；恢复原材质不会清除草稿。校准时选择 Cover Surface。" baseColor="#b8c1c5"/><CarPreview mesh={mesh} atlas={output} revision={revision} useSourceUV repeatTexture label="真实材质槽 · UV0"/></div>
  <canvas className="atlas-output" ref={output} width={1024} height={1024}/><button disabled={busy||!ready||!image} onClick={()=>void apply()}>应用到此材质槽</button><button disabled={busy||!ready} onClick={()=>void apply(true)}>恢复原材质</button><p role="status">{status}</p>
  <details open={showScene} onToggle={e=>setShowScene(e.currentTarget.open)}><summary>CARLA 实景（应用后更新）</summary><button disabled={busy} onClick={()=>setSceneRevision(v=>v+1)}>刷新实景</button>{showScene&&<img src={`${bridge}/scene/preview?material=${sceneRevision}`} alt="当前 CARLA 观察相机实景" style={{width:'100%',maxHeight:'65vh',objectFit:'contain'}}/>}</details><small>原材质：{selected?.original_material??'无'}</small>
 </section>;
}
