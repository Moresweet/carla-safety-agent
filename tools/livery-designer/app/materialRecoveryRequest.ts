import type {MaterialInspection} from './materialInspection';

// A timed-out write has an unknown outcome. Never retry it automatically.
export async function requestMaterialRecovery(operation:string,inspection:MaterialInspection,choice:'source'|'target',fetcher:typeof fetch=fetch,timeoutMs=30000,actor=false):Promise<void>{
 if(!inspection.recoverable||!inspection.token||!['source','target'].includes(choice))throw Error('需要最新的未解决材质检查');
 const controller=new AbortController();
 let timer:ReturnType<typeof setTimeout>|undefined;
 const timeout=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error('恢复请求超时，写入结果未知'))},timeoutMs)});
 try{
  const work=(async()=>{
   const response=await fetcher('http://127.0.0.1:8765/materials/'+(actor?'actor-history-recover':'history-recover'),{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({operation_id:operation,inspection_token:inspection.token,choice,registered_texture:inspection.registered,confirmed:true})});
   const raw=await response.json();
   if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('恢复响应无效');
   const value=raw as {ok?:boolean;error?:string;operation_id?:string;recovery?:{state?:string;desired?:string|null;choice?:string}};
   if(!response.ok||value.ok!==true)throw Error(typeof value.error==='string'?value.error:'恢复未确认');
   if(value.operation_id!==operation||value.recovery?.state!=='confirmed'||value.recovery.choice!==choice||value.recovery.desired!==inspection[choice])throw Error('恢复回执与确认内容不一致');
  })();
  await Promise.race([work,timeout]);
 }finally{clearTimeout(timer)}
}
