"use client";
import {RefObject,useEffect,useRef} from "react";
export type MeshData={source:string;triangleCount:number;vertices:number[]};
function shader(gl:WebGLRenderingContext,type:number,source:string){const s=gl.createShader(type)!;gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s)??"Shader error");return s}
function program(gl:WebGLRenderingContext){const p=gl.createProgram()!;gl.attachShader(p,shader(gl,gl.VERTEX_SHADER,`attribute vec3 p;attribute vec2 uv;uniform mat4 m;varying vec2 v;void main(){v=uv;gl_Position=m*vec4(p,1.);}`));gl.attachShader(p,shader(gl,gl.FRAGMENT_SHADER,`precision mediump float;uniform sampler2D atlas;varying vec2 v;void main(){vec4 c=texture2D(atlas,v);gl_FragColor=vec4(mix(vec3(.72),c.rgb,c.a),1.);}`));gl.linkProgram(p);return p}
function matrix(yaw:number,pitch:number,aspect:number){const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),s=.72;return new Float32Array([cy*s/aspect,sy*sp*s/aspect,sy*cp*s/aspect,0,-sy*s,cy*sp*s,cy*cp*s,0,0,cp*s,-sp*s,0,0,0,0,1])}
export default function CarPreview({mesh,atlas,revision}:{mesh:MeshData|null;atlas:RefObject<HTMLCanvasElement|null>;revision:number}){
 const canvas=useRef<HTMLCanvasElement>(null),angle=useRef({yaw:-.7,pitch:.42}),drag=useRef<{x:number;y:number;yaw:number;pitch:number}|null>(null);
 useEffect(()=>{
  const c=canvas.current;if(!c||!mesh)return;const gl=c.getContext("webgl",{antialias:true});if(!gl)return;
  const p=program(gl),raw=mesh.vertices,positions=new Float32Array(raw.length/5*3),uvs=new Float32Array(raw.length/5*2),mins=[Infinity,Infinity,Infinity],maxs=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<raw.length;i+=5)for(let q=0;q<3;q++){mins[q]=Math.min(mins[q],raw[i+q]);maxs[q]=Math.max(maxs[q],raw[i+q])}
  const norm=(v:number,q:number)=>(v-mins[q])/(maxs[q]-mins[q]);
  for(let i=0,j=0,k=0;i<raw.length;i+=15){
   const a=[raw[i],raw[i+1],raw[i+2]],b=[raw[i+5],raw[i+6],raw[i+7]],d=[raw[i+10],raw[i+11],raw[i+12]],u=[b[0]-a[0],b[1]-a[1],b[2]-a[2]],v=[d[0]-a[0],d[1]-a[1],d[2]-a[2]],n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],side=Math.abs(n[1])>Math.abs(n[2]),right=(a[1]+b[1]+d[1])/3>0;
   for(const point of [a,b,d]){positions.set(point,j);let px:number,py:number;if(!side){px=norm(point[0],0)/3;py=1-norm(point[1],1)}else if(!right){px=(1+norm(point[0],0))/3;py=1-norm(point[2],2)}else{px=(2+norm(point[0],0))/3;py=1-norm(point[2],2)}uvs.set([px,py],k);j+=3;k+=2}
  }
  const bind=(name:string,data:Float32Array,size:number)=>{const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);const a=gl.getAttribLocation(p,name);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,size,gl.FLOAT,false,0,0)};
  gl.useProgram(p);bind("p",positions,3);bind("uv",uvs,2);const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.enable(gl.DEPTH_TEST);gl.enable(gl.CULL_FACE);
  const draw=()=>{c.width=c.clientWidth*devicePixelRatio;c.height=c.clientHeight*devicePixelRatio;gl.viewport(0,0,c.width,c.height);gl.clearColor(.035,.055,.085,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.uniformMatrix4fv(gl.getUniformLocation(p,"m"),false,matrix(angle.current.yaw,angle.current.pitch,c.width/c.height));if(atlas.current){gl.bindTexture(gl.TEXTURE_2D,tex);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,1);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,atlas.current)}gl.drawArrays(gl.TRIANGLES,0,positions.length/3)};
  draw();(c as HTMLCanvasElement&{redraw?:()=>void}).redraw=draw;return()=>{gl.deleteProgram(p);gl.deleteTexture(tex)}
 },[mesh,atlas]);
 useEffect(()=>{(canvas.current as HTMLCanvasElement&{redraw?:()=>void})?.redraw?.()},[revision]);
 function move(e:React.PointerEvent<HTMLCanvasElement>){if(!drag.current)return;angle.current={yaw:drag.current.yaw+(e.clientX-drag.current.x)*.01,pitch:Math.max(-1,Math.min(1,drag.current.pitch+(e.clientY-drag.current.y)*.01))};(e.currentTarget as HTMLCanvasElement&{redraw?:()=>void}).redraw?.()}
 return <div className="preview"><div className="previewbar"><b>3D BODY PREVIEW</b><span>Drag to orbit · front direction calibrated</span></div><canvas ref={canvas} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);drag.current={x:e.clientX,y:e.clientY,...angle.current}}} onPointerMove={move} onPointerUp={()=>drag.current=null}/><div className="axis"><i className="front"/>Front<i className="left"/>Sides<i className="top"/>Roof</div></div>
}
