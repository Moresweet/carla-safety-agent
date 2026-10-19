"use client";
import {ChangeEvent,useCallback,useEffect,useMemo,useRef,useState} from "react";
import BevMap,{SceneObject,SceneState} from "./BevMap";
import BlenderAssetPage from "./BlenderAssetPage";
import AssetCameraPreview from "./AssetCameraPreview";
import BuildingSurfaceEditor from "./BuildingSurfaceEditor";
import CarPreview,{MeshData} from "./CarPreview";
import CreateObjectPage from "./CreateObjectPage";
import DataCollectionPage from "./DataCollectionPage";
import EndToEndPage from "./EndToEndPage";
import ObjectManager,{CatalogItem} from "./ObjectManager";
import PedestrianClothingEditor from "./PedestrianClothingEditor";
import ProjectionEditor from "./ProjectionEditor";
import RoadSurfaceEditor from "./RoadSurfaceEditor";
import ScenarioGeneratorPage from "./ScenarioGeneratorPage";
import Surface3DPreview from "./Surface3DPreview";
import ProjectPanel from "./ProjectPanel";
import MaterialSlotEditor from "./MaterialSlotEditor";
import {textureRoute} from './textureTarget';
import {readWithRetry} from './readWithRetry';

type Studio="vehicle"|"pedestrian"|"buildings"|"bridges"|"walls"|"fences"|"roads"|"road_lines"|"sidewalks"|"ground"|"terrain"|"vegetation"|"water"|"poles"|"guard_rails"|"traffic_signs"|"traffic_lights"|"parked_cars"|"dynamic_props"|"static_props"|"spawned_props";
type Page="edit"|"create"|"blender"|"generate"|"data"|"e2e";
const bridge="http://127.0.0.1:8765";
const labels:Record<Studio,string>={vehicle:"Vehicles",pedestrian:"Pedestrians",buildings:"Buildings",bridges:"Bridges",walls:"Walls",fences:"Fences",roads:"Roads",road_lines:"Road Lines",sidewalks:"Sidewalks",ground:"Ground",terrain:"Terrain",vegetation:"Vegetation",water:"Water",poles:"Poles",guard_rails:"Guard Rails",traffic_signs:"Traffic Signs",traffic_lights:"Traffic Lights",parked_cars:"Parked Cars",dynamic_props:"Dynamic Props",static_props:"Static Props",spawned_props:"Spawned Props"};
const roadStudios=new Set<Studio>(["roads","road_lines","sidewalks","ground","terrain","water"]);
type VehicleMeshCatalog=Record<string,{url:string;slot:number;slotName:string;baseType:string}>;

export default function Home(){
 const output=useRef<HTMLCanvasElement>(null);
 const [sceneError,setSceneError]=useState('');
 const [page,setPage]=useState<Page>("edit"),[studio,setStudio]=useState<Studio>("vehicle"),[image,setImage]=useState<HTMLImageElement|null>(null),[base,setBase]=useState<HTMLImageElement|null>(null),[meshes,setMeshes]=useState<Record<string,MeshData>>({}),[meshCatalog,setMeshCatalog]=useState<VehicleMeshCatalog>({}),[fileName,setFileName]=useState("No image selected"),[revision,setRevision]=useState(0),[applyState,setApplyState]=useState("Bridge ready"),[applying,setApplying]=useState(false),[scene,setScene]=useState<SceneState|null>(null),[selected,setSelected]=useState(""),[refresh,setRefresh]=useState(0),[catalogTarget,setCatalogTarget]=useState<CatalogItem|null>(null);
 useEffect(()=>{const n=new Image();n.onload=()=>setBase(n);n.src="/tesla-model3-bodywork.png";Promise.all([fetch("/tesla-model3-uv0.json").then(r=>r.json() as Promise<MeshData>),fetch("/european-hgv-uv0.json").then(r=>r.json() as Promise<MeshData>),fetch("/vehicle-mesh-catalog.json").then(r=>r.json() as Promise<VehicleMeshCatalog>),fetch('/pedestrian-mesh-catalog.json').then(r=>r.json() as Promise<VehicleMeshCatalog>)]).then(([tesla,hgv,catalog,pedestrians])=>{setMeshes({"vehicle.tesla.model3":tesla,"vehicle.carlamotors.european_hgv":hgv});setMeshCatalog({...catalog,...pedestrians})}).catch(e=>setApplyState(`预览目录不可用：${String(e)}`))},[]);
 useEffect(()=>{
  if(page==='e2e')return;
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{
   try{
    const value=await readWithRetry<SceneState>(bridge+'/scene/state',{signal:controller.signal,attempts:1,timeoutMs:2500});
    if(typeof value.map!=='string'||!Array.isArray(value.objects)||!Array.isArray(value.static_targets))throw Error('场景响应不完整');
    if(!controller.signal.aborted){setScene(value);setSceneError('')}
   }catch(error){if(!controller.signal.aborted)setSceneError('场景连接暂不可用，保留上次视图：'+String(error))}
   finally{if(!controller.signal.aborted)timer=setTimeout(poll,700)}
  };
  void poll();return()=>{controller.abort();clearTimeout(timer)};
 },[page,refresh]);
 const rendered=useCallback(()=>setRevision(v=>v+1),[]);
 const objects=useMemo(()=>{if(!scene)return[];const all=[...scene.static_targets,...scene.objects];if(studio==="vehicle")return all.filter(o=>o.kind==="vehicle");if(studio==="pedestrian")return all.filter(o=>o.kind==="walker");if(roadStudios.has(studio))return all.filter(o=>o.kind==="road");return all.filter(o=>o.kind==="building"||o.kind==="prop")},[scene,studio]);
 // Keep the controlled target aligned with the asynchronously refreshed CARLA catalog.
 // eslint-disable-next-line react-hooks/set-state-in-effect
 useEffect(()=>{if(objects.length&&!objects.some(o=>o.key===selected))setSelected(objects[0].key)},[objects,selected]);
 function upload(e:ChangeEvent<HTMLInputElement>){const f=e.target.files?.[0];if(!f)return;const u=URL.createObjectURL(f),n=new Image();n.onload=()=>{setImage(n);URL.revokeObjectURL(u)};n.src=u;setFileName(f.name)}
 function png(){const a=document.createElement("a");a.download=`${studio}-texture.png`;a.href=output.current?.toDataURL("image/png")??"";a.click()}
 async function post(path:string,data:unknown){const r=await fetch(`${bridge}/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),v=await r.json() as {error?:string;enabled?:boolean;hero_id?:number;object_name?:string;object_count?:number;actor_id?:number};if(!r.ok)throw new Error(v.error);return v}
 async function focus(o:SceneObject){const compatible=(studio==="pedestrian"&&o.kind==="walker")||(studio==="vehicle"&&o.kind==="vehicle")||(roadStudios.has(studio)&&o.kind==="road")||(!roadStudios.has(studio)&&(o.kind==="building"||o.kind==="prop"));if(compatible){setSelected(o.key);setCatalogTarget(null)}setApplyState(`Focused ${o.label}`);if(o.id)await post("focus/actor",{actor_id:o.id});else await post("focus/static",{kind:o.kind,name:o.name})}
 async function toggleHero(){try{const v=await post("camera/hero-lock",{enabled:!scene?.hero_lock});setApplyState(v.enabled?`Hero camera locked to actor ${v.hero_id}`:"Hero camera released")}catch(e){setApplyState(e instanceof Error?e.message:"Hero camera failed")}}
async function apply(){if(!output.current)return;setApplying(true);setApplyState("Uploading texture…");try{const route=textureRoute(catalogTarget??objects.find(o=>o.key===selected));if(route.error)throw new Error(route.error);const blob=await new Promise<Blob>((ok,no)=>output.current!.toBlob(v=>v?ok(v):no(new Error("PNG encoding failed")),"image/png"));const r=await fetch(`${bridge}/${route.path}`,{method:"POST",headers:{"Content-Type":"image/png"},body:blob}),v=await r.json() as {error?:string;enabled?:boolean;hero_id?:number;object_name?:string;object_count?:number;actor_id?:number;versionable?:boolean};if(!r.ok)throw new Error(v.error);setApplyState(`Applied texture to ${v.object_name??v.object_count??v.actor_id}${v.versionable?' · 已纳入纹理版本，请保存场景':''}`)}catch(e){setApplyState(e instanceof Error?e.message:"Apply failed")}finally{setApplying(false)}}
 function changeStudio(next:Studio){setStudio(next);setCatalogTarget(null);setImage(null);setFileName("No image selected");setApplyState("Bridge ready")}
 function editCatalogTexture(item:CatalogItem){const next=item.kind==="walker"?"pedestrian":item.kind==="vehicle"?"vehicle":((item.category in labels?item.category:item.kind==="road"?"roads":"buildings") as Studio);setPage("edit");setStudio(next);setCatalogTarget(item);setImage(null);setFileName("No image selected");setApplyState(`Texture target: ${item.name}`);window.scrollTo({top:0,behavior:"smooth"})}
 const target=objects.find(o=>o.key===selected),activeTarget=catalogTarget??target,vehicleBlueprint=((studio==="vehicle"&&activeTarget?.kind==="vehicle")||(studio==='pedestrian'&&activeTarget?.kind==='walker'))?activeTarget.name:"",mesh=meshes[vehicleBlueprint]??null,isTesla=vehicleBlueprint==="vehicle.tesla.model3",hasVehicleMesh=!!mesh,isVehicleEditor=studio==="vehicle",previewKind=studio==="pedestrian"?"pedestrian":roadStudios.has(studio)?"road":"building",title=studio==="vehicle"?`${vehicleBlueprint||"SELECTED"} BODY SURFACE`:labels[studio].toUpperCase()+" SURFACE";
 const textureSelection=textureRoute(activeTarget);
 useEffect(()=>{const entry=meshCatalog[vehicleBlueprint];if(!entry||meshes[vehicleBlueprint])return;const abort=new AbortController();fetch(entry.url,{signal:abort.signal}).then(async r=>{if(!r.ok)throw new Error('该资产的真实预览尚未生成');const data=await r.json() as MeshData;if(!Array.isArray(data.vertices)||!data.vertices.length)throw new Error('真实预览网格无效');return data}).then(data=>{if(!abort.signal.aborted)setMeshes(current=>({...current,[vehicleBlueprint]:data}))}).catch(e=>{if(!abort.signal.aborted)setApplyState(String(e))});return()=>abort.abort()},[vehicleBlueprint,meshCatalog,meshes]);
 // A target change invalidates the previously composed texture by design.
 // eslint-disable-next-line react-hooks/set-state-in-effect
 useEffect(()=>{setImage(null);setFileName("No image selected");const canvas=output.current;canvas?.getContext("2d")?.clearRect(0,0,canvas.width,canvas.height)},[activeTarget?.key]);
 if(page==="edit"&&catalogTarget?.source==="environment")return <main><button onClick={()=>setCatalogTarget(null)}>← 返回场景工作台</button><MaterialSlotEditor key={catalogTarget.key} objectId={catalogTarget.id} name={catalogTarget.name}/><ObjectManager onChanged={()=>setRefresh(v=>v+1)} onTextureTarget={editCatalogTexture}/></main>;
 return <main>
  <ProjectPanel/>
  {sceneError&&<p role="status" aria-label="场景连接状态">{sceneError}</p>}
  <header><div><span className="eyebrow">CARLA SAFETY AGENT</span><h1>Scene Control Studio</h1></div><nav className="page-nav"><button className={page==="edit"?"active":""} onClick={()=>setPage("edit")}>Edit World</button><button className={page==="create"?"active":""} onClick={()=>setPage("create")}>Create Objects</button><button className={page==="blender"?"active":""} onClick={()=>setPage("blender")}>Asset Workshop</button><button className={page==="generate"?"active":""} onClick={()=>setPage("generate")}>Generate Scene</button><button className={page==="data"?"active":""} onClick={()=>setPage("data")}>Collect Data</button><button className={page==="e2e"?"active":""} onClick={()=>setPage("e2e")}>End-to-End Test</button></nav><div className="status"><i/>{scene?`${scene.runtime_mode==="docker"?"DOCKER":"NATIVE"} · ${scene.map.split("/").pop()} · ${scene.objects.length} dynamic objects`:"Connecting to CARLA…"}</div></header>
  {page==="e2e"?<EndToEndPage/>:page==="data"?<DataCollectionPage/>:page==="blender"?<BlenderAssetPage/>:page==="generate"?<ScenarioGeneratorPage onEvaluationStarted={()=>setPage("e2e")}/>:page==="create"?<CreateObjectPage scene={scene} onChanged={()=>setRefresh(v=>v+1)} onPick={focus}/>:<><div className="viewtabs">{(Object.keys(labels) as Studio[]).map(v=><button key={v} className={studio===v?"active":""} onClick={()=>changeStudio(v)}>{labels[v]}</button>)}</div><section className="workspace">
   <aside className="controls"><div className="section"><label htmlFor="target">Texture target</label>{catalogTarget?<div className="note"><strong>{catalogTarget.name}</strong><p>{catalogTarget.category.replaceAll("_"," ")} · selected from World Objects</p></div>:<><select id="target" value={selected} onChange={e=>{const o=objects.find(v=>v.key===e.target.value);if(o)focus(o)}}>{objects.length?objects.map(o=><option value={o.key} key={o.key}>{o.label}</option>):<option value="">No matching objects</option>}</select><button disabled={!target} onClick={()=>target&&focus(target)}>Focus & highlight</button></>}</div><div className="section"><button className={scene?.hero_lock?"primary":""} onClick={toggleHero}>{scene?.hero_lock?"Release hero camera":"Lock hero camera"}</button><small>Follow the only role_name=hero vehicle.</small></div><div className="section"><label className="upload">Upload image<input type="file" accept="image/png,image/jpeg,image/webp" onChange={upload}/></label><small>{fileName}</small></div><div className="note"><strong>Category highlights</strong><p>Vehicles blue · pedestrians yellow · buildings purple · roads red · props green.</p></div></aside>
   <div className="visuals">
    <div className="stage surface-stage"><div className="stagebar"><span>2D TEXTURE · {title}</span><span>{isVehicleEditor?"Decal · tile · cover":"Local decal, tile or cover"}</span></div>
     {hasVehicleMesh?<ProjectionEditor mesh={mesh} base={isTesla?base:null} image={image} output={output} onRender={rendered} useSourceUV={!isTesla} label={`${vehicleBlueprint} · ${meshCatalog[vehicleBlueprint]?.slotName??"Bodywork"}`}/>:isVehicleEditor?<BuildingSurfaceEditor image={image} output={output} onRender={rendered} label={`${vehicleBlueprint} runtime diffuse atlas`} note="This blueprint has no successfully exported web mesh; CARLA is the authoritative preview."/>:roadStudios.has(studio)?<RoadSurfaceEditor image={image} output={output} onRender={rendered}/>:studio==="pedestrian"?<PedestrianClothingEditor image={image} output={output} onRender={rendered}/>:<BuildingSurfaceEditor image={image} output={output} onRender={rendered} label={catalogTarget?.name} note={catalogTarget?"Semantic surface preview; CARLA remains authoritative until this asset mesh is exported.":undefined}/>}
     <canvas className="atlas-output" ref={output} width={hasVehicleMesh&&isVehicleEditor?2048:1024} height={hasVehicleMesh&&isVehicleEditor?2048:1024}/>
    </div>
    {hasVehicleMesh?<CarPreview mesh={mesh} atlas={output} revision={revision} useSourceUV={!isTesla} label={isVehicleEditor?`${vehicleBlueprint} · LIVE 3D BODYWORK`:'裤装槽 14 · 源网格绑定姿态'} axisLabels={isVehicleEditor?undefined:['真实 UV0','仅裤装','非实时动画']}/>:isVehicleEditor?<AssetCameraPreview blueprint={vehicleBlueprint} label={activeTarget?.label??"No vehicle"}/>:<Surface3DPreview atlas={output} revision={revision} kind={previewKind} label={activeTarget?.label??"No target"}/>}
    <BevMap state={scene} selected={selected} onPick={focus}/><ObjectManager onChanged={()=>setRefresh(v=>v+1)} onTextureTarget={editCatalogTexture}/>
   </div>
   <aside className="export"><span className="eyebrow">LIVE OUTPUT</span><h2>Send to CARLA</h2><p>{textureSelection.error??`修改范围：${textureSelection.scope}`}</p><button className="primary" disabled={!image||applying||!activeTarget||!!textureSelection.error} onClick={apply}>{applying?"Applying…":`Apply ${studio} texture`}</button><small>{applyState}</small><button disabled={!image} onClick={png}>Export texture PNG</button><dl><div><dt>Target</dt><dd>{activeTarget?.kind??"None"}</dd></div><div><dt>BEV</dt><dd>Live · click to focus</dd></div><div><dt>Hero</dt><dd>{scene?.hero_lock?"Locked":"Free"}</dd></div></dl></aside>
  </section></>}
 </main>
}
