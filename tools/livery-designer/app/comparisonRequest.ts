import {parseComparison,type Comparison} from './comparisonData';

// Cancellation is silent; timeout is an actionable failure, including while
// reading JSON. A late response must never publish into a newer selection.
export function readComparison(
 selection:{batch_id:string;axis:string;baseline:string;candidate:string},
 publish:(value:Comparison)=>void,
 fail:(message:string)=>void,
 finish:()=>void,
 transport:typeof fetch=fetch,
 timeoutMs=15000,
){
 const controller=new AbortController();let settled=false;
 const timer=setTimeout(()=>{
  if(settled)return;
  settled=true;controller.abort();
  fail('比较读取超时，请确认桥接服务正常后手动重试。');finish();
 },timeoutMs);
 void (async()=>{
  try{
   const response=await transport('http://127.0.0.1:8765/batches/compare?'+new URLSearchParams(selection),{signal:controller.signal});
   if(!response.ok)throw new Error('比较读取失败：HTTP '+response.status);
   const value=parseComparison(await response.json(),selection);
   if(!settled)publish(value);
  }catch(error){if(!settled)fail(String(error))}
  finally{clearTimeout(timer);if(!settled){settled=true;finish()}}
 })();
 return()=>{settled=true;clearTimeout(timer);controller.abort()};
}
