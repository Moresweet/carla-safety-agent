"use client";
import {RefObject,useEffect,useState} from "react";
export default function Surface3DPreview({label}:{atlas:RefObject<HTMLCanvasElement|null>;revision:number;kind:string;label:string}){
 const [url,setUrl]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [audit,setAudit]=useState<{exported:number;registered:number}|null>(null);
 useEffect(()=>{let active=true;fetch('http://127.0.0.1:8765/assets/uv-audit').then(r=>r.json() as Promise<{exported:number;registered:number}>).then(v=>{if(active)setAudit(v)}).catch(()=>{});return()=>{active=false}},[]);
 useEffect(()=>()=>{if(url)URL.revokeObjectURL(url)},[url]);
 async function capture(){setBusy(true);setError("");try{const r=await fetch("http://127.0.0.1:8765/scene/preview");if(!r.ok){const v=await r.json() as {error:string};throw new Error(v.error)}setUrl(URL.createObjectURL(await r.blob()))}catch(e){setError(String(e))}finally{setBusy(false)}}
 return <div className="preview actual-preview"><div className="previewbar"><b>CARLA 实景验证</b><span>{label}</span></div><p>该类型尚未导出可核验的网格、UV 与材质映射。已取消代理几何预览，避免误导贴图位置。</p><p>{audit?`UV 核验：车辆导出 ${audit.exported}/${audit.registered}；其他类型尚未导出。`:'UV 核验结果读取中。'}这不代表 Unreal 原始资产没有 UV。</p><p>先聚焦目标并应用纹理，再获取实景。实景显示已应用效果，不是未提交的编辑草稿。</p><button onClick={capture} disabled={busy}>{busy?"取景中…":"刷新 CARLA 实景"}</button>{error&&<p role="alert">{error}</p>}{url&&<img src={url} alt="CARLA 当前观察视角的真实渲染" style={{width:"100%"}}/>}</div>
}
