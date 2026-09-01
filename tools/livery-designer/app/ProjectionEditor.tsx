"use client";
import {RefObject,useEffect,useRef,useState} from "react";
import {MeshData} from "./CarPreview";
type View="top"|"left"|"right";
type Mode="decal"|"tile"|"cover";
type Props={mesh:MeshData|null;base:HTMLImageElement|null;image:HTMLImageElement|null;output:RefObject<HTMLCanvasElement|null>;onRender:()=>void};
function normal(a:number[],b:number[],c:number[]){const u=[b[0]-a[0],b[1]-a[1],b[2]-a[2]],v=[c[0]-a[0],c[1]-a[1],c[2]-a[2]];return[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]}
export default function ProjectionEditor({mesh,image,output,onRender}:Props){
 const visible=useRef<HTMLCanvasElement>(null),drag=useRef<{x:number;y:number;px:number;py:number}|null>(null);
 const [view,setView]=useState<View>("left"),[mode,setMode]=useState<Mode>("decal"),[x,setX]=useState(50),[y,setY]=useState(50),[scale,setScale]=useState(46),[rotation,setRotation]=useState(0);
 useEffect(()=>{
  const display=visible.current,out=output.current;if(!display||!out||!mesh)return;
  const dc=display.getContext("2d")!,oc=out.getContext("2d")!,size=display.width,a=mesh.vertices;
  const mins=[Infinity,Infinity,Infinity],maxs=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<a.length;i+=5)for(let k=0;k<3;k++){mins[k]=Math.min(mins[k],a[i+k]);maxs[k]=Math.max(maxs[k],a[i+k])}
  const nrm=(v:number,k:number)=>(v-mins[k])/(maxs[k]-mins[k]),verticalAxis=view==="top"?1:2;
  const aspect=(maxs[0]-mins[0])/(maxs[verticalAxis]-mins[verticalAxis]),frame={w:size*.9,h:size*.9/aspect,x:size*.05,y:(size-size*.9/aspect)/2};
  const project=(p:number[])=>[frame.x+nrm(p[0],0)*frame.w,frame.y+(1-nrm(p[verticalAxis],verticalAxis))*frame.h];
  const eligible=(p:number[][])=>{const n=normal(p[0],p[1],p[2]),m=Math.hypot(...n)||1;if(view==="top")return Math.abs(n[2])/m>.35;const cy=(p[0][1]+p[1][1]+p[2][1])/3;return Math.abs(n[1])/m>.35&&(view==="left"?cy<0:cy>0)};
  dc.clearRect(0,0,size,size);dc.fillStyle="#080d16";dc.fillRect(0,0,size,size);const triangles:number[][][]=[];dc.beginPath();
  for(let i=0;i<a.length;i+=15){const p=[[a[i],a[i+1],a[i+2]],[a[i+5],a[i+6],a[i+7]],[a[i+10],a[i+11],a[i+12]]];if(!eligible(p))continue;const s=p.map(project);triangles.push(s);dc.moveTo(s[0][0],s[0][1]);dc.lineTo(s[1][0],s[1][1]);dc.lineTo(s[2][0],s[2][1]);dc.closePath()}dc.fillStyle="#dce5e9";dc.fill();
  const layer=document.createElement("canvas");layer.width=layer.height=size;const lc=layer.getContext("2d")!;if(image){const w=scale/100*frame.w,h=w*image.height/image.width;if(mode==="cover")lc.drawImage(image,frame.x,frame.y,frame.w,frame.h);else{lc.translate(frame.x+x/100*frame.w,frame.y+y/100*frame.h);lc.rotate(rotation*Math.PI/180);if(mode==="decal")lc.drawImage(image,-w/2,-h/2,w,h);else for(let py=-size*1.5;py<size*1.5;py+=Math.max(20,h))for(let px=-size*1.5;px<size*1.5;px+=Math.max(20,w))lc.drawImage(image,px,py,w,h)}}
  dc.save();dc.globalCompositeOperation="source-atop";dc.drawImage(layer,0,0);dc.restore();dc.beginPath();for(const s of triangles){dc.moveTo(s[0][0],s[0][1]);dc.lineTo(s[1][0],s[1][1]);dc.lineTo(s[2][0],s[2][1]);dc.closePath()}dc.strokeStyle="#243743";dc.globalAlpha=.25;dc.stroke();dc.globalAlpha=1;
  dc.fillStyle="#8da1ad";dc.font="24px sans-serif";dc.fillText("REAR",frame.x,frame.y+frame.h+34);const front="FRONT";dc.fillText(front,frame.x+frame.w-dc.measureText(front).width,frame.y+frame.h+34);
  oc.clearRect(0,0,2048,2048);if(image){const third=2048/3,index=view==="top"?0:view==="left"?1:2;oc.drawImage(layer,frame.x,frame.y,frame.w,frame.h,index*third,0,third,2048)}onRender();
 },[mesh,image,output,onRender,view,mode,x,y,scale,rotation]);
 function move(e:React.PointerEvent<HTMLCanvasElement>){if(!drag.current)return;const r=e.currentTarget.getBoundingClientRect();setX(Math.max(0,Math.min(100,drag.current.x+(e.clientX-drag.current.px)/r.width*100/.9)));setY(Math.max(0,Math.min(100,drag.current.y+(e.clientY-drag.current.py)/r.height*100)))}
 return <div className="projection"><div className="viewtabs">{(["top","left","right"] as View[]).map(v=><button className={view===v?"active":""} key={v} onClick={()=>setView(v)}>{v} view</button>)}</div><div className="texture-modes">{(["decal","tile","cover"] as Mode[]).map(v=><button className={mode===v?"active":""} key={v} onClick={()=>setMode(v)}>{v}</button>)}</div><canvas ref={visible} width="1024" height="1024" onPointerDown={e=>{if(!image)return;e.currentTarget.setPointerCapture(e.pointerId);drag.current={px:e.clientX,py:e.clientY,x,y}}} onPointerMove={move} onPointerUp={()=>drag.current=null} onWheel={e=>{if(image){e.preventDefault();setScale(v=>Math.max(5,Math.min(120,v-e.deltaY*.05)))}}}/><div className="projection-controls"><label>Scale <input type="range" min="5" max="120" value={scale} onChange={e=>setScale(+e.target.value)}/></label><label>Rotation <input type="range" min="-180" max="180" value={rotation} onChange={e=>setRotation(+e.target.value)}/></label></div><small>Decal, tiled and full-surface projection · rear left, front right.</small></div>
}
