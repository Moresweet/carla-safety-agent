"use client";
import {useEffect,useRef,useState} from 'react';
type Control={throttle:number;steer:number;brake:number;hand_brake:boolean;reverse:boolean};
const brake:Control={throttle:0,steer:0,brake:1,hand_brake:true,reverse:false};
export default function ManualDriving({runId}:{runId:string}){
 const desired=useRef<Control>(brake),[label,setLabel]=useState('制动'),[error,setError]=useState('');
 const stop=()=>{desired.current=brake;setLabel('制动')};
 useEffect(()=>{let active=true,pending=false,lastSent:Control=brake;
 const send=async()=>{if(pending||(desired.current===brake&&lastSent===brake))return;pending=true;const control=desired.current;try{
 const response=await fetch('http://127.0.0.1:8765/collection/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId,control})});
 const result=await response.json() as {error?:string};if(!response.ok)throw new Error(result.error??'控制请求失败');lastSent=control;if(active)setError('');
 }catch(e){desired.current=brake;if(active){setLabel('制动');setError(String(e))}}finally{pending=false}};
 const release=()=>{stop();void send()};
 window.addEventListener('blur',release);document.addEventListener('visibilitychange',release);
 const timer=setInterval(()=>{if(document.hidden)desired.current=brake;void send()},100);void send();
 return()=>{active=false;clearInterval(timer);window.removeEventListener('blur',release);document.removeEventListener('visibilitychange',release);desired.current=brake;void send()};
 },[runId]);
 const actions=[['前进',0,false],['左转前进',-.35,false],['右转前进',.35,false],['倒车',0,true]] as const;
 const drive=(name:string,steer:number,reverse:boolean)=>{desired.current={throttle:.35,steer,reverse,brake:0,hand_brake:false};setLabel(name)};
 return <div><h3>人工驾驶 · 按住操作</h3><p>松开即请求制动。按钮获得焦点后可按住空格或 Enter；离开页面或失焦会停止控制。网络和仿真卡顿可能延迟制动。</p>
 <div className="sensor-toolbar">{actions.map(([name,steer,reverse])=><button key={name} style={{touchAction:'none'}}
 onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);drive(name,steer,reverse)}}
 onPointerUp={stop} onPointerCancel={stop} onLostPointerCapture={stop} onBlur={stop}
 onKeyDown={e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();drive(name,steer,reverse)}}}
 onKeyUp={e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();stop()}}}>{name}</button>)}
 <button onClick={stop}>制动 / 手刹</button></div><p role="status">请求：{label}（以实时控制值为准）</p>{error&&<p role="alert">{error}</p>}</div>;
}
