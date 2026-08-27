"use client";
import { ChangeEvent, useEffect, useRef, useState } from "react";
type Mode = "decal" | "tile" | "cover";
export default function Home() {
  const canvas=useRef<HTMLCanvasElement>(null); const [image,setImage]=useState<HTMLImageElement|null>(null);
  const [template,setTemplate]=useState<HTMLImageElement|null>(null);
  const [fileName,setFileName]=useState("No image selected"),[mode,setMode]=useState<Mode>("decal");
  const [x,setX]=useState(50),[y,setY]=useState(50),[scale,setScale]=useState(42),[rotation,setRotation]=useState(0);
  useEffect(()=>{const n=new Image();n.onload=()=>setTemplate(n);n.src="/tesla-model3-bodywork.png"},[]);
  useEffect(()=>{const target=canvas.current,ctx=target?.getContext("2d");if(!target||!ctx)return;const w=target.width,h=target.height;
    ctx.clearRect(0,0,w,h);ctx.fillStyle="#171d27";ctx.fillRect(0,0,w,h);
    const cell=64;for(let yy=0;yy<h;yy+=cell)for(let xx=0;xx<w;xx+=cell){ctx.fillStyle=((xx/cell+yy/cell)%2)?"#232b38":"#1d2430";ctx.fillRect(xx,yy,cell,cell)}
    if(template)ctx.drawImage(template,0,0,w,h);
    if(!image)return;ctx.save();ctx.globalAlpha=.88;if(mode==="cover")ctx.drawImage(image,0,0,w,h);else if(mode==="tile"){const t=Math.max(80,scale/100*760);for(let ty=0;ty<h;ty+=t)for(let tx=0;tx<w;tx+=t)ctx.drawImage(image,tx,ty,t,t)}else{const dw=scale/100*w,dh=dw*image.height/image.width;ctx.translate(x/100*w,y/100*h);ctx.rotate(rotation*Math.PI/180);ctx.drawImage(image,-dw/2,-dh/2,dw,dh)}ctx.restore();
  },[template,image,mode,x,y,scale,rotation]);
  function upload(e:ChangeEvent<HTMLInputElement>){const f=e.target.files?.[0];if(!f)return;const u=URL.createObjectURL(f),n=new Image();n.onload=()=>{setImage(n);URL.revokeObjectURL(u)};n.src=u;setFileName(f.name)}
  function png(){const a=document.createElement("a");a.download="tesla-model3-livery.png";a.href=canvas.current?.toDataURL("image/png")??"";a.click()}
  function config(){const data={version:1,vehicle:"vehicle.tesla.model3",mode,texture:"tesla-model3-livery.png",transform:{x:x/100,y:y/100,scale:scale/100,rotation_deg:rotation}};const a=document.createElement("a");a.download="vehicle-appearance.json";a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));a.click()}
  return <main><header><div><span className="eyebrow">CARLA SAFETY AGENT</span><h1>Vehicle Livery Studio</h1></div><div className="status"><i/>Local workspace</div></header>
    <section className="workspace"><aside className="controls"><div className="section"><label>Vehicle template</label><select><option>Tesla Model 3 · UV v1</option></select></div>
    <div className="section"><label className="upload">Upload image<input type="file" accept="image/png,image/jpeg,image/webp" onChange={upload}/></label><small>{fileName}</small></div>
    <div className="section"><label>Placement mode</label><div className="modes">{(["decal","tile","cover"] as Mode[]).map(v=><button key={v} className={mode===v?"active":""} onClick={()=>setMode(v)}>{v}</button>)}</div></div>
    {mode==="decal"&&<div className="section sliders"><Slider name="Horizontal" value={x} set={setX}/><Slider name="Vertical" value={y} set={setY}/><Slider name="Scale" value={scale} set={setScale}/><Slider name="Rotation" value={rotation} set={setRotation} min={-180} max={180}/></div>}
    <div className="note"><strong>Actual CARLA texture space</strong><p>The visible base was exported from Tesla Model 3 material M_Tesla_Bodywork_d_a. Uploaded graphics are composed at the asset's native 2048×2048 coordinates.</p></div></aside>
    <div className="stage"><div className="stagebar"><span>TESLA BODYWORK TEXTURE · 2048 × 2048</span><span>{mode.toUpperCase()}</span></div><canvas ref={canvas} width="2048" height="2048"/>{!image&&<div className="empty"><b>Actual model texture loaded</b><span>Upload PNG, JPEG or WebP to compose in its texture space</span></div>}</div>
    <aside className="export"><span className="eyebrow">OUTPUT</span><h2>Texture-space draft</h2><p>Export the composed bodywork texture with reproducible placement settings.</p><button className="primary" disabled={!image} onClick={png}>Export texture PNG</button><button disabled={!image} onClick={config}>Export configuration</button><dl><div><dt>Target</dt><dd>Tesla Model 3</dd></div><div><dt>Source</dt><dd>UE material asset</dd></div><div><dt>Resolution</dt><dd>2048 × 2048</dd></div></dl></aside></section></main>;
}
function Slider({name,value,set,min=0,max=100}:{name:string,value:number,set:(n:number)=>void,min?:number,max?:number}){return <label><span>{name}<b>{value}</b></span><input type="range" min={min} max={max} value={value} onChange={e=>set(Number(e.target.value))}/></label>}
