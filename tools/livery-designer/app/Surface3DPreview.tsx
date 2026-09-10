"use client";
import {RefObject,useEffect,useState} from "react";
export default function Surface3DPreview({label}:{atlas:RefObject<HTMLCanvasElement|null>;revision:number;kind:string;label:string}){
 const [url,setUrl]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [audit,setAudit]=useState<{exported:number;registered:number}|null>(null);
 useEffect(()=>{let active=true;fetch('http://127.0.0.1:8765/assets/uv-audit').then(r=>r.json() as Promise<{exported:number;registered:number}>).then(v=>{if(active)setAudit(v)}).catch(()=>{});return()=>{active=false}},[]);
 useEffect(()=>()=>{if(url)URL.revokeObjectURL(url)},[url]);
 async function capture(){setBusy(true);setError("");try{const r=await fetch("http://127.0.0.1:8765/scene/preview");if(!r.ok){const v=await r.json() as {error:string};throw new Error(v.error)}setUrl(URL.createObjectURL(await r.blob()))}catch(e){setError(String(e))}finally{setBusy(false)}}
 return <div className="preview actual-preview surface-runtime-preview"><div className="previewbar"><b>CARLA 实景验证</b><span>{label}</span></div><p>此旧入口未加载所选对象的真实网格与 UV，不提供代理几何预览。</p><p>建筑、道路等环境对象请从 World Objects 选择具体对象，进入组件 / 材质槽编辑器；已导出的槽位支持真实 UV0 预览。</p><p>{audit?`车辆预览导出核验：${audit.exported}/${audit.registered}。`:'车辆预览核验结果读取中。'}此计数不代表整个 Unreal 资产库的 UV 完整性。</p><p>先聚焦具体对象，再获取实景。实景显示场景当前效果，不是未提交的纹理草稿。</p><button onClick={capture} disabled={busy}>{busy?"取景中…":"刷新 CARLA 实景"}</button>{error&&<p role="alert">{error}</p>}{url&&<img src={url} alt="CARLA 当前观察视角的真实渲染"/>}</div>
}
