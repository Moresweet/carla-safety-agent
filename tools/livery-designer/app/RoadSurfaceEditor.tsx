"use client";
import {RefObject,useEffect,useRef,useState} from "react";

export default function RoadSurfaceEditor({image,output,onRender}:{image:HTMLImageElement|null;output:RefObject<HTMLCanvasElement|null>;onRender:()=>void}){
 const preview=useRef<HTMLCanvasElement>(null),[repeat,setRepeat]=useState(4),[rotation,setRotation]=useState(0);
 useEffect(()=>{
  const visible=preview.current,out=output.current;if(!visible||!out)return;
  const render=(ctx:CanvasRenderingContext2D,size:number)=>{ctx.clearRect(0,0,size,size);ctx.fillStyle="#353b40";ctx.fillRect(0,0,size,size);if(!image)return;const tile=size/repeat;ctx.save();ctx.translate(size/2,size/2);ctx.rotate(rotation*Math.PI/180);for(let y=-size*1.5;y<size*1.5;y+=tile)for(let x=-size*1.5;x<size*1.5;x+=tile)ctx.drawImage(image,x,y,tile,tile);ctx.restore()};
  render(visible.getContext("2d")!,visible.width);render(out.getContext("2d")!,out.width);onRender();
 },[image,output,onRender,repeat,rotation]);
 return <div className="projection road-editor"><div className="viewtabs"><button className="active">asphalt surface</button></div><canvas ref={preview} width="1024" height="1024"/><div className="projection-controls"><label>Repeat <input type="range" min="1" max="16" value={repeat} onChange={e=>setRepeat(+e.target.value)}/></label><label>Rotation <input type="range" min="-180" max="180" value={rotation} onChange={e=>setRotation(+e.target.value)}/></label></div><small>World road meshes · seamless repeat · lane markings remain separate.</small></div>
}
