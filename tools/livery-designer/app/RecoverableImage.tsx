"use client";
import {useEffect,useState,type ImgHTMLAttributes} from 'react';
type Props=Omit<ImgHTMLAttributes<HTMLImageElement>,'src'|'onLoad'|'onError'> & {src:string;alt:string;retryKey?:number};
function Attempt({src,alt,retryKey,style,...props}:Props){
 const [attempt,setAttempt]=useState(0),[failed,setFailed]=useState(false),[loaded,setLoaded]=useState(false);
 useEffect(()=>{if(loaded||failed)return;const timer=setTimeout(()=>setFailed(true),4000);return()=>clearTimeout(timer)},[attempt,loaded,failed]);
 useEffect(()=>{if(!failed||attempt>=2)return;const timer=setTimeout(()=>{setFailed(false);setLoaded(false);setAttempt(n=>n+1)},600*(attempt+1));return()=>clearTimeout(timer)},[failed,attempt]);
 const reload=retryKey?src+(src.includes('?')?'&':'?')+'read_reload='+retryKey:src;
 const url=attempt?reload+(reload.includes('?')?'&':'?')+'read_retry='+attempt:reload;
 return <span className="recoverable-image" style={{display:'grid',position:'relative',width:'100%',height:'100%',minHeight:0,placeItems:'center'}}>
  <img key={url} {...props} src={url} alt={alt} style={{...style,gridArea:'1 / 1',visibility:loaded?'visible':'hidden'}} onLoad={()=>{setLoaded(true);setFailed(false)}} onError={()=>{setLoaded(false);setFailed(true)}}/>
  {!loaded&&<span role={failed&&attempt>=2?'alert':'status'} style={{gridArea:'1 / 1',padding:12,textAlign:'center'}}>{failed&&attempt>=2?'图像读取失败，请点击“重新加载图像”':failed?`图像连接暂不可用，准备重试 ${attempt+2}/3…`:'正在读取图像…'}</span>}
 </span>;
}
// URL identity changes remount state: a late event cannot reveal a previous frame.
export default function RecoverableImage(props:Props){return <Attempt key={`${props.src}:${props.retryKey??0}`} {...props}/>}
