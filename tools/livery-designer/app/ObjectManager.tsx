"use client";
import {useEffect,useMemo,useRef,useState} from "react";
import {objectOriginLabel, type ObjectOrigin} from "./objectOrigin";
import TransformEditor from './TransformEditor';
import PositionHistory from './PositionHistory';
import type {EditIdentity} from './transformDraft';

const bridge="http://127.0.0.1:8765";
type Category={id:string;group:string;coarse:string;count:number;editable:string};
export type CatalogItem={key:string;id:number|string;source:"actor"|"environment";category:string;group:string;kind:string;name:string;label:string;visible?:boolean;origin?:ObjectOrigin;edit_identity?:EditIdentity|null;location:{x:number;y:number;z:number};extent:{x:number;y:number;z:number};rotation?:{pitch:number;yaw:number;roll:number}};
async function request(path:string,method="GET",data?:unknown){const r=await fetch(`${bridge}/${path}`,{method,headers:data?{"Content-Type":"application/json"}:undefined,body:data?JSON.stringify(data):undefined}),v=await r.json() as {error?:string;categories:Category[];objects:CatalogItem[];total:number};if(!r.ok)throw new Error(v.error);return v}

export default function ObjectManager({onChanged,onTextureTarget}:{onChanged:()=>void;onTextureTarget:(item:CatalogItem)=>void}){
 const [origin,setOrigin]=useState("all");
 const [categories,setCategories]=useState<Category[]>([]),[category,setCategory]=useState("buildings"),[items,setItems]=useState<CatalogItem[]>([]),[query,setQuery]=useState(""),[offset,setOffset]=useState(0),[total,setTotal]=useState(0),[selected,setSelected]=useState<CatalogItem|null>(null),[status,setStatus]=useState("Ready"),[revision,setRevision]=useState(0),[busy,setBusy]=useState(false),[loadError,setLoadError]=useState('');
 const pending=useRef(false);
 useEffect(()=>{let alive=true,loading=false;const load=async()=>{if(loading)return;loading=true;try{const v=await request('catalog/categories');if(alive)setCategories(v.categories)}catch(e){if(alive)setLoadError(String(e))}finally{loading=false}};void load();const timer=setInterval(()=>void load(),2500);return()=>{alive=false;clearInterval(timer)}},[revision]);
 useEffect(()=>{let alive=true,loading=false;const load=async()=>{if(loading)return;loading=true;try{const v=await request(`catalog/objects?category=${encodeURIComponent(category)}&q=${encodeURIComponent(query)}&offset=${offset}&limit=50&origin=${origin}`);if(!alive)return;setItems(v.objects);setTotal(v.total);setCategories(current=>current.map(c=>c.id===category?{...c,count:v.total}:c));setSelected(current=>v.objects.find(item=>item.key===current?.key)??v.objects[0]??null);setLoadError('')}catch(e){if(alive)setLoadError(String(e))}finally{loading=false}};const delay=setTimeout(()=>void load(),180),live=setInterval(()=>void load(),2000);return()=>{alive=false;clearTimeout(delay);clearInterval(live)}},[category,query,offset,revision,origin]);
 const groups=useMemo(()=>Object.entries(categories.reduce<Record<string,Category[]>>((a,c)=>{(a[c.group]??=[]).push(c);return a},{})),[categories]);
 async function act(path:string,data:unknown,message:string,refreshList=false){if(pending.current)return false;pending.current=true;setBusy(true);try{await request(path,"POST",data);setStatus(message);if(refreshList)setRevision(v=>v+1);onChanged();return true}catch(e){setStatus(e instanceof Error?e.message:"Operation failed");return false}finally{pending.current=false;setBusy(false)}}
 async function focus(item:CatalogItem){setSelected(item);await act(item.source==="actor"?"focus/actor":"focus/environment",item.source==="actor"?{actor_id:item.id}:{object_id:item.id},`Focused ${item.name}`)}
 async function visibility(){if(!selected||selected.source!=="environment")return;const visible=selected.visible===false;await act("objects/environment/visibility",{object_id:selected.id,visible},visible?"Object restored":"Object hidden",true)}
 return <section className="object-manager">
  <div className="manager-head"><div><span className="eyebrow">WORLD OBJECTS</span><h2>Scene Object Manager</h2></div><span role="status">{busy?'操作中…':status}</span></div>
  {loadError&&<p role="alert">目录刷新失败：{loadError}</p>}
  <div className="manager-grid"><aside className="catalog-groups">{groups.map(([group,list])=><div key={group}><b>{group.replaceAll('_',' ')}</b>{list.map(c=><button disabled={busy} key={c.id} className={category===c.id?'active':''} onClick={()=>{setCategory(c.id);setOffset(0);setSelected(null)}}><span>{c.id.replaceAll('_',' ')}</span><em>{c.count}</em></button>)}</div>)}</aside>
   <div className="catalog-list"><label>对象来源<select aria-label="对象来源" disabled={busy} value={origin} onChange={e=>{setOrigin(e.target.value);setOffset(0)}}><option value="all">全部来源</option><option value="existing">场景原有</option><option value="user">用户新增</option><option value="evaluation">评测生成</option><option value="unknown">来源未知</option></select></label>
    <input disabled={busy} placeholder="Search name or ID" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0)}}/>
    <select size={15} disabled={busy} value={selected?.key??''} onChange={e=>{const item=items.find(v=>v.key===e.target.value);if(item)void focus(item)}}>{items.map(item=><option key={item.key} value={item.key}>{item.visible===false?'[hidden] ':''}{`[${objectOriginLabel(item.origin)}] `}{item.label}</option>)}</select>
    <div className="pager"><button disabled={busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous</button><span>{total?`${offset+1}–${Math.min(offset+50,total)} / ${total}`:'0 objects'}</span><button disabled={busy||offset+50>=total} onClick={()=>setOffset(offset+50)}>Next</button></div>
   </div>
   <aside className="object-inspector"><h3>{selected?.name??'Select an object'}</h3>{selected&&<>
    <dl><div><dt>Source</dt><dd>{objectOriginLabel(selected.origin)}</dd></div><div><dt>Category</dt><dd>{selected.category}</dd></div><div><dt>ID</dt><dd>{selected.id}</dd></div></dl>
    <TransformEditor key={selected.key+':'+selected.name+':'+JSON.stringify(selected.edit_identity)} item={selected} editable={selected.source==='actor'} busy={busy} onApply={(transform,expected)=>act('objects/update-reviewed',{actor_id:selected.id,transform,expected},'Actor transform updated',true)}/>
    {selected.source==='actor'&&<PositionHistory key={'history:'+JSON.stringify(selected.edit_identity)} item={selected} busy={busy} onAction={data=>act('objects/transform-history',data,'位置历史操作已确认',true)}/>}
    <button disabled={busy} onClick={()=>void focus(selected)}>Focus & highlight</button><button disabled={busy} className="primary" onClick={()=>onTextureTarget(selected)}>Edit texture</button>
    {selected.source==='actor'?<><button disabled={busy} onClick={()=>void act('objects/duplicate',{actor_id:selected.id},'Actor duplicated',true)}>Duplicate</button><button disabled={busy} className="danger" onClick={()=>void act('objects/delete',{actor_id:selected.id},'Actor deleted',true)}>Delete actor</button></>:<button disabled={busy} onClick={()=>void visibility()}>{selected.visible===false?'Restore object':'Hide object'}</button>}
   </>}</aside>
  </div>
 </section>;
}
