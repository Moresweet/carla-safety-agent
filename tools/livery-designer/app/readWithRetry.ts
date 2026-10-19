// GET only: never replay a simulator command or a recording mutation.
export class ReadHttpError extends Error {
 status:number;
 constructor(status:number,message:string){super(message);this.status=status;}
}
type Options={signal:AbortSignal;onRetry?:(attempt:number)=>void;timeoutMs?:number;delayMs?:number;attempts?:number;fetcher?:typeof fetch};
function pause(ms:number,signal:AbortSignal){
 return new Promise<void>((resolve,reject)=>{
  if(signal.aborted){reject(signal.reason);return;}
  const abort=()=>{clearTimeout(timer);signal.removeEventListener('abort',abort);reject(signal.reason)};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve()},ms);
  signal.addEventListener('abort',abort,{once:true});
 });
}
export async function readWithRetry<T>(url:string,{signal,onRetry,timeoutMs=4000,delayMs=600,attempts=3,fetcher=fetch}:Options):Promise<T>{
 if(!Number.isInteger(attempts)||attempts<1||attempts>3||!Number.isFinite(timeoutMs)||timeoutMs<1||!Number.isFinite(delayMs)||delayMs<0)throw Error('Invalid bounded read policy');
 for(let attempt=1;attempt<=attempts;attempt++){
  signal.throwIfAborted();
  const controller=new AbortController();
  const cancel=()=>controller.abort(signal.reason);
  signal.addEventListener('abort',cancel,{once:true});
  const timer=setTimeout(()=>controller.abort(new DOMException('读取超时','TimeoutError')),timeoutMs);
  let retry=false;
  try{
   const response=await fetcher(url,{method:'GET',signal:controller.signal,cache:'no-store'});
   if(!response.ok)throw new ReadHttpError(response.status,`读取失败（HTTP ${response.status}）`);
   const value=await response.json() as T;
   signal.throwIfAborted();
   return value;
  }catch(error){
   signal.throwIfAborted();
   retry=error instanceof TypeError||controller.signal.aborted||(error instanceof ReadHttpError&&[408,429,502,503,504].includes(error.status));
   if(!retry||attempt===attempts)throw error;
  }finally{clearTimeout(timer);signal.removeEventListener('abort',cancel)}
  if(retry){onRetry?.(attempt+1);await pause(delayMs*attempt,signal)}
 }
 throw Error('Read attempts exhausted');
}
