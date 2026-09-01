"use client";
const bridge="http://127.0.0.1:8765";
export default function AssetCameraPreview({blueprint,label}:{blueprint:string;label:string}){return <div className="preview actual-preview"><div className="previewbar"><b>CARLA ASSET PREVIEW</b><span>Rendered from the selected blueprint</span></div>{blueprint?<img src={`${bridge}/catalog/thumbnail?blueprint=${encodeURIComponent(blueprint)}`} alt={`${label} CARLA preview`}/>:<div className="empty"><b>No running asset selected</b><span>Create or select an actor first.</span></div>}<small>{label}</small></div>}
