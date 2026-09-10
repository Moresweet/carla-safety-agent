"use client";
import {useEffect,useRef,useState} from "react";
import BevMap,{SceneObject,SceneState} from "./BevMap";

const bridge="http://127.0.0.1:8765";
type Kind="all"|"vehicle"|"walker"|"prop"|"generated";
const names:{id:Kind;label:string}[]=[{id:"all",label:"All"},{id:"vehicle",label:"Vehicles"},{id:"walker",label:"Pedestrians"},{id:"prop",label:"Props"},{id:"generated",label:"Generated"}];
function kindOf(id:string):"vehicle"|"walker"|"prop"{return id.startsWith("vehicle.")?"vehicle":id.startsWith("walker.")?"walker":"prop"}
function shortName(id:string){return id.split(".").slice(-2).join(" ").replaceAll("_"," ")}

export default function CreateObjectPage({scene,onChanged,onPick}:{scene:SceneState|null;onChanged:()=>void;onPick:(o:SceneObject)=>void}){
 const [blueprints,setBlueprints]=useState<string[]>([]),[kind,setKind]=useState<Kind>("all"),[query,setQuery]=useState(""),[selected,setSelected]=useState(""),[status,setStatus]=useState("Choose an asset, then drag it onto the map"),[creating,setCreating]=useState(false);
 const active=useRef(false);
 const [offset,setOffset]=useState(0),[total,setTotal]=useState(0),[loading,setLoading]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();let alive=true;setLoading(true);setError('');setBlueprints([]);setSelected('');
  const timeout=setTimeout(()=>controller.abort(),10000);
  const timer=setTimeout(()=>{void (async()=>{try{
   const params=new URLSearchParams({q:query,kind,offset:String(offset),limit:'48'});
   const r=await fetch(bridge+'/catalog/blueprints?'+params,{signal:controller.signal}),v=await r.json() as {ok?:boolean;error?:string;blueprints:string[];total:number;offset:number};
   if(!r.ok||!v.ok||!Array.isArray(v.blueprints)||v.offset!==offset||!Number.isInteger(v.total))throw Error(v.error??'Invalid catalog response');
   if(alive){setBlueprints(v.blueprints);setTotal(v.total);setSelected(v.blueprints[0]??'')}
  }catch(e){if(alive){setError(String(e));setTotal(0)}}finally{clearTimeout(timeout);if(alive)setLoading(false)}})()},200);
  return()=>{alive=false;controller.abort();clearTimeout(timer);clearTimeout(timeout)};
 },[query,kind,offset]);
 const visible=blueprints;
 async function create(id:string,x:number,y:number){
  if(active.current||loading||!blueprints.includes(id))return;
  active.current=true;setCreating(true);setSelected(id);setStatus('Creating '+id+'…');
  try{
   const r=await fetch(bridge+'/objects/spawn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({blueprint_id:id,transform:{location:{x,y,z:1},rotation:{yaw:0},snap_to_ground:true}})}),v=await r.json() as {error?:string;object:{id:number}};
   if(!r.ok)throw Error(v.error);
   setStatus('Created '+id+' · actor #'+v.object.id);onChanged();
   try{const focus=await fetch(bridge+'/focus/actor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actor_id:v.object.id})});if(!focus.ok)throw Error('Focus rejected')}
   catch{setStatus('Created '+id+' · actor #'+v.object.id+'; camera focus failed. Do not repeat creation.')}
  }catch(e){setStatus(e instanceof Error?e.message:'Creation outcome unknown; inspect objects before retrying')}
  finally{active.current=false;setCreating(false)}
 }
 const selectedKind=selected?kindOf(selected):"prop";
 return <section className="create-page"><div className="create-head"><div><span className="eyebrow">ASSET LIBRARY</span><h2>Create Objects</h2><p>完整目录分页检索；支持名称及车辆、行人、护栏、路锥、长椅、生成资产等中文关键词，多个词用空格分隔。不验证颜色、尺寸或外形；运行期间目录来自执行快照。</p></div><div className={`asset-hero ${selectedKind}`}>{selected&&!selected.startsWith("generated.")?<img src={`${bridge}/catalog/thumbnail?blueprint=${encodeURIComponent(selected)}`} alt={`${selected} CARLA preview`}/>:<div className="asset-silhouette"><i/><i/><i/></div>}<strong>{selected?shortName(selected):"Select an asset"}</strong><small title={selected}>{selected}</small></div></div><div className="create-layout"><aside className="asset-browser"><div className="asset-tabs">{names.map(v=><button key={v.id} className={kind===v.id?"active":""} onClick={()=>{setKind(v.id);setOffset(0)}}>{v.label}</button>)}</div><input aria-label="检索资产" placeholder="Search blueprints / 中文关键词" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0)}}/>{error&&<p role="alert">{error}</p>}<p aria-label="资产检索统计">{loading?"检索中…":total+" 个匹配 · "+(visible.length?offset+1:0)+"–"+(offset+visible.length)}</p><div className="asset-pagination"><button disabled={loading||offset===0} onClick={()=>setOffset(v=>Math.max(0,v-48))}>上一页</button><button disabled={loading||offset+48>=total} onClick={()=>setOffset(v=>v+48)}>下一页</button></div><div className="asset-grid">{visible.map(id=>{const type=kindOf(id);return <button draggable={!creating&&!loading} title={id} key={id} className={`asset-card ${selected===id?"selected":""}`} onClick={()=>setSelected(id)} onDragStart={e=>{if(active.current){e.preventDefault();return}setSelected(id);e.dataTransfer.setData("application/x-carla-blueprint",id);e.dataTransfer.effectAllowed="copy"}}>{id.startsWith("generated.")?<span>生成资产 · 缩略图未验证</span>:<img loading="lazy" className="asset-thumb-image" src={`${bridge}/catalog/thumbnail?blueprint=${encodeURIComponent(id)}`} alt={`${id} thumbnail`}/>}<b>{shortName(id)}</b><small>{type}</small></button>})}</div></aside><div className="create-map"><BevMap state={scene} selected="" onPick={onPick} onDropBlueprint={create}/><div className="drop-status"><i className={creating?"busy":""}/><span>{status}</span></div></div></div></section>
}
