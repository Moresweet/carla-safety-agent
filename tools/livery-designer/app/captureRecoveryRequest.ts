import {parseRecoveryJob,type RecoveryJob} from './captureRecoveryJob';

// Timeout/abort does not establish whether the server accepted this ID.
export async function requestCaptureRecovery(source:string,id:string,signal:AbortSignal,fetcher:typeof fetch=fetch,timeoutMs=30000):Promise<RecoveryJob>{
 if(!/^capture-[A-Za-z0-9-]+$/.test(source)||!/^[a-f0-9]{32}$/.test(id))throw Error('恢复请求身份无效');
 const controller=new AbortController();
 let timer:ReturnType<typeof setTimeout>|undefined;
 let abort=()=>{};
 const stopped=new Promise<never>((_,reject)=>{
  abort=()=>{controller.abort();reject(Error('恢复请求已中止，结果未知'))};
  signal.addEventListener('abort',abort,{once:true});
  timer=setTimeout(()=>{controller.abort();reject(Error('恢复请求超时，结果未知'))},timeoutMs);
 });
 try{
  if(signal.aborted){abort();return await stopped}
  const work=(async()=>{
   const response=await fetcher('http://127.0.0.1:8765/datasets/recovery',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({run_id:source,request_id:id,confirmed:true})});
   if(!response.ok)throw Error('恢复启动结果未确认：HTTP '+response.status);
   return parseRecoveryJob(await response.json(),id,source);
  })();
  return await Promise.race([work,stopped]);
 }finally{clearTimeout(timer);signal.removeEventListener('abort',abort)}
}
