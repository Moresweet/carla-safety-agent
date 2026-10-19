const bridge='http://127.0.0.1:8765';

export function requireBatchIdentity<T>(value:{batch_id?:string;report:T},expected:string):T{
 if(!expected||value.batch_id!==expected)throw new Error('批次报告身份不匹配，请重新读取；未启用该报告的操作。');
 return value.report;
}

/** One attempt only. A timed-out write is unknown, not a rejected operation. */
export async function batchApi<T>(path:string,body?:unknown,transport:typeof fetch=fetch,timeoutMs=body===undefined?15000:60000):Promise<T>{
 const controller=new AbortController();
 let timer:ReturnType<typeof setTimeout>|undefined;
 const timeout=new Promise<never>((_,reject)=>{
  timer=setTimeout(()=>{
   controller.abort();
   reject(new Error(body===undefined?'批次读取超时，请手动刷新。':'批次操作响应超时，执行结果未知。请先刷新并核对队列与执行记录，不要重复提交。'));
  },timeoutMs);
 });
 try{
  return await Promise.race([timeout,(async()=>{
   const response=await transport(bridge+path,{signal:controller.signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
   const value=await response.json() as T & {ok?:boolean;error?:string};
   if(!response.ok||!value||value.ok!==true)throw new Error(value?.error||'批次响应无效或请求失败');
   return value;
  })()]);
 }finally{clearTimeout(timer)}
}
