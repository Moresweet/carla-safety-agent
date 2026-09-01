"use client";
import {ChangeEvent,useCallback,useEffect,useMemo,useRef,useState} from "react";
import BevMap,{SceneObject,SceneState} from "./BevMap";
import BuildingSurfaceEditor from "./BuildingSurfaceEditor";
import CarPreview,{MeshData} from "./CarPreview";
import ObjectManager,{CatalogItem} from "./ObjectManager";
import PedestrianClothingEditor from "./PedestrianClothingEditor";
import ProjectionEditor from "./ProjectionEditor";
import RoadSurfaceEditor from "./RoadSurfaceEditor";

type Studio="vehicle"|"road"|"building"|"pedestrian"|"environment";
const bridge="http://127.0.0.1:8765";
const labels:Record<Studio,string>={vehicle:"Vehicle",road:"Road",building:"Building",pedestrian:"Pedestrian",environment:"Catalog Surface"};

export default function Home(){
 const output=useRef<HTMLCanvasElement>(null);
 const [studio,setStudio]=useState<Studio>("vehicle"),[image,setImage]=useState<HTMLImageElement|null>(null),[base,setBase]=useState<HTMLImageElement|null>(null),[mesh,setMesh]=useState<MeshData|null>(null),[fileName,setFileName]=useState("No image selected"),[revision,setRevision]=useState(0),[applyState,setApplyState]=useState("Bridge ready"),[applying,setApplying]=useState(false),[scene,setScene]=useState<SceneState|null>(null),[selected,setSelected]=useState(""),[refresh,setRefresh]=useState(0),[catalogTarget,setCatalogTarget]=useState<CatalogItem|null>(null);
 useEffect(()=>{const n=new Image();n.onload=()=>setBase(n);n.src="/tesla-model3-bodywork.png";fetch("/tesla-model3-uv0.json").then(r=>r.json()).then(setMesh)},[]);
 useEffect(()=>{let live=true;const poll=()=>fetch(`${bridge}/scene/state`).then(r=>r.json()).then(v=>{if(live)setScene(v)}).catch(()=>{});poll();const timer=setInterval(poll,700);return()=>{live=false;clearInterval(timer)}},[refresh]);
 const rendered=useCallback(()=>setRevision(v=>v+1),[]);
 const objects=useMemo(()=>{if(!scene||studio==="environment")return[];return [...scene.static_targets,...scene.objects].filter(o=>studio==="pedestrian"?o.kind==="walker":o.kind===studio)},[scene,studio]);
 useEffect(()=>{if(objects.length&&!objects.some(o=>o.key===selected))setSelected(objects[0].key)},[objects,selected]);
 function upload(e:ChangeEvent<HTMLInputElement>){const f=e.target.files?.[0];if(!f)return;const u=URL.createObjectURL(f),n=new Image();n.onload=()=>{setImage(n);URL.revokeObjectURL(u)};n.src=u;setFileName(f.name)}
 function png(){const a=document.createElement("a");a.download=`${studio}-texture.png`;a.href=output.current?.toDataURL("image/png")??"";a.click()}
 async function post(path:string,data:unknown){const r=await fetch(`${bridge}/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),v=await r.json();if(!r.ok)throw new Error(v.error);return v}
 async function focus(o:SceneObject){const compatible=studio==="pedestrian"?o.kind==="walker":o.kind===studio;if(compatible)setSelected(o.key);setApplyState(`Focused ${o.label}`);if(o.id)await post("focus/actor",{actor_id:o.id});else await post("focus/static",{kind:o.kind,name:o.name})}
 async function toggleHero(){try{const v=await post("camera/hero-lock",{enabled:!scene?.hero_lock});setApplyState(v.enabled?`Hero camera locked to actor ${v.hero_id}`:"Hero camera released")}catch(e){setApplyState(e instanceof Error?e.message:"Hero camera failed")}}
 async function apply(){
  if(!output.current)return;setApplying(true);setApplyState("Uploading texture…");
  try{const blob=await new Promise<Blob>((ok,no)=>output.current!.toBlob(v=>v?ok(v):no(new Error("PNG encoding failed")),"image/png"));const target=objects.find(o=>o.key===selected);const endpoint=studio==="vehicle"?"apply":studio==="road"?"apply/road?scope=all":studio==="building"?`apply/building?target=${encodeURIComponent(target?.name??"BP_House16")}`:studio==="pedestrian"?"apply/pedestrian":`apply/environment?object_id=${encodeURIComponent(catalogTarget?.id??"")}`;const r=await fetch(`${bridge}/${endpoint}`,{method:"POST",headers:{"Content-Type":"image/png"},body:blob}),v=await r.json();if(!r.ok)throw new Error(v.error);setApplyState(`Applied ${studio} texture to ${v.object_name??v.object_count??v.actor_id}`)}catch(e){setApplyState(e instanceof Error?e.message:"Apply failed")}finally{setApplying(false)}
 }
 function changeStudio(next:Studio){setStudio(next);setImage(null);setFileName("No image selected");setApplyState("Bridge ready")}
 function editCatalogTexture(item:CatalogItem){setCatalogTarget(item);setStudio("environment");setImage(null);setFileName("No image selected");setApplyState(`Texture target: ${item.name}`);window.scrollTo({top:0,behavior:"smooth"})}
 const target=objects.find(o=>o.key===selected),activeTarget=studio==="environment"?catalogTarget:target,title=studio==="vehicle"?"TESLA BODY SURFACE":studio==="road"?"ROAD SURFACE":studio==="building"?"BUILDING WALL SURFACE":studio==="pedestrian"?"PEDESTRIAN CLOTHING":"SELECTED CATALOG SURFACE";
 return <main>
  <header><div><span className="eyebrow">CARLA SAFETY AGENT</span><h1>Scene Control Studio</h1></div><div className="status"><i/>{scene?`${scene.map.split("/").pop()} · ${scene.objects.length} dynamic objects`:"Connecting to CARLA…"}</div></header>
  <div className="viewtabs">{(Object.keys(labels) as Studio[]).map(v=><button key={v} className={studio===v?"active":""} onClick={()=>changeStudio(v)}>{labels[v]}</button>)}</div>
  <section className="workspace">
   <aside className="controls"><div className="section"><label htmlFor="target">Texture target</label>{studio==="environment"?<div className="note"><strong>{catalogTarget?.name??"Choose an object below"}</strong><p>{catalogTarget?.category.replaceAll("_"," ")??"Use Edit this surface texture in the object manager."}</p></div>:<><select id="target" value={selected} onChange={e=>{const o=objects.find(v=>v.key===e.target.value);if(o)focus(o)}}>{objects.length?objects.map(o=><option value={o.key} key={o.key}>{o.label}</option>):<option value="">No matching objects</option>}</select><button disabled={!target} onClick={()=>target&&focus(target)}>Focus & highlight</button></>}</div><div className="section"><button className={scene?.hero_lock?"primary":""} onClick={toggleHero}>{scene?.hero_lock?"Release hero camera":"Lock hero camera"}</button><small>Follow the only role_name=hero vehicle.</small></div><div className="section"><label className="upload">Upload image<input type="file" accept="image/png,image/jpeg,image/webp" onChange={upload}/></label><small>{fileName}</small></div><div className="note"><strong>Category highlights</strong><p>Vehicles blue · pedestrians yellow · buildings purple · roads red.</p></div></aside>
   <div className="visuals"><div className="stage surface-stage"><div className="stagebar"><span>{title}</span><span>{studio==="vehicle"?"Drag image · wheel to scale":"Local decal or tiled surface"}</span></div>{studio==="vehicle"?<ProjectionEditor mesh={mesh} base={base} image={image} output={output} onRender={rendered}/>:studio==="road"?<RoadSurfaceEditor image={image} output={output} onRender={rendered}/>:studio==="building"||studio==="environment"?<BuildingSurfaceEditor image={image} output={output} onRender={rendered} label={studio==="environment"?catalogTarget?.name:undefined} note={studio==="environment"?"The selected object's runtime material target will receive this composed texture.":undefined}/>:<PedestrianClothingEditor image={image} output={output} onRender={rendered}/>}<canvas className="atlas-output" ref={output} width={studio==="vehicle"?2048:1024} height={studio==="vehicle"?2048:1024}/></div>{studio==="vehicle"?<CarPreview mesh={mesh} atlas={output} revision={revision}/>:<div className="preview road-preview"><div className="previewbar"><b>SELECTED TEXTURE TARGET</b><span>{activeTarget?.label??"None"}</span></div><div className="road-perspective"><span>Independent materials preserved</span></div></div>}<BevMap state={scene} selected={selected} onPick={focus}/><ObjectManager onChanged={()=>setRefresh(v=>v+1)} onTextureTarget={editCatalogTexture}/></div>
   <aside className="export"><span className="eyebrow">LIVE OUTPUT</span><h2>Send to CARLA</h2><p>Apply the composed local decal or tile to the selected surface target.</p><button className="primary" disabled={!image||applying||!activeTarget} onClick={apply}>{applying?"Applying…":`Apply ${studio} texture`}</button><small>{applyState}</small><button disabled={!image} onClick={png}>Export texture PNG</button><dl><div><dt>Target</dt><dd>{activeTarget?.kind??"None"}</dd></div><div><dt>BEV</dt><dd>Live · click to focus</dd></div><div><dt>Hero</dt><dd>{scene?.hero_lock?"Locked":"Free"}</dd></div></dl></aside>
  </section>
 </main>
}
