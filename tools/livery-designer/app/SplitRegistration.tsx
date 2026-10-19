"use client";
import {useRef,useState} from 'react';
import {parseSplitRegistration,splitFileError} from './splitRegistration';

export default function SplitRegistration({onWriteAttempt}:{onWriteAttempt:()=>void}){
 const [file,setFile]=useState<File|null>(null),[busy,setBusy]=useState(false);
 const [message,setMessage]=useState(''),[error,setError]=useState('');
 const active=useRef(false);
 async function register(){
  if(active.current||!file)return;
  active.current=true;setBusy(true);setError('');setMessage('');
  try{
   const invalid=splitFileError(file.size);if(invalid)throw Error(invalid);
   const payload=await file.text();
   onWriteAttempt();
   const response=await fetch('http://127.0.0.1:8765/datasets/splits/register',{
    method:'POST',headers:{'Content-Type':'application/json'},body:payload,signal:AbortSignal.timeout(30000)});
   const raw:unknown=await response.json();
   const value=parseSplitRegistration(raw,response.status);
   setMessage(`${value.created?'登记成功':'该划分已登记，无重复写入'}：${value.run_count} 份录制；SHA-256 ${value.sha256}。请重新盘点查看引用。`);
   onWriteAttempt();
  }catch(e){setError(String(e)+'；若响应中断，登记结果可能不明确。可手动重试同一文件，内容相同不会重复登记。不会自动重试。');}
  finally{active.current=false;setBusy(false);}
 }
 return <section aria-label="数据划分登记">
  <h3>登记已有数据划分</h3>
  <p>上传已生成的 carla-safety-split/0.1 JSON，将其录制引用纳入本地清理保护。登记会核对录制元信息，不修改录制、不自动分组，也不代表原始传感器数据已逐文件验证。</p>
  <label>划分 JSON<input aria-label="划分 JSON 文件" type="file" accept=".json,application/json" disabled={busy}
   onChange={e=>{const chosen=e.target.files?.[0]??null;setFile(chosen);setError(chosen?splitFileError(chosen.size):'');setMessage('');}}/></label>
  {file&&<p>{file.name} · {file.size} 字节</p>}
  <button disabled={busy||!file||!!splitFileError(file.size)} onClick={()=>void register()}>{busy?'正在校验登记…':'确认登记划分引用'}</button>
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}
