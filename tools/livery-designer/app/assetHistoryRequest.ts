export type AssetAttempt={attempt_id:string;job_id:string;state:string;destination?:string;error?:string;report_path:string;started_at:number;observation?:{coordinator:string;error?:string|null;requires_attention:boolean};registration_observation?:{state:string;error?:string|null}};
export function parseAssetAttempts(raw:unknown,generation:boolean):AssetAttempt[]{
 if(!Array.isArray(raw)||raw.length>100)throw Error('资产历史列表无效');
 const ids=new Set<string>();
 const states=generation?['preparing','generating','exported','needs_attention']:['preparing','importing','registered','needs_attention'];
 const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
 return raw.map(value=>{
  if(!object(value)||typeof value.attempt_id!=='string'||!/^[a-zA-Z0-9]{1,64}$/.test(value.attempt_id)
   ||ids.has(value.attempt_id)||typeof value.job_id!=='string'||!/^[a-zA-Z0-9]{1,64}$/.test(value.job_id)
   ||typeof value.state!=='string'||!states.includes(value.state)||typeof value.report_path!=='string'
   ||!value.report_path||typeof value.started_at!=='number'||!Number.isFinite(value.started_at)
   ||value.started_at<0||!Number.isFinite(new Date(value.started_at*1000).getTime()))throw Error('资产历史记录无效');
  for(const key of ['destination','error'])if(value[key]!==undefined&&typeof value[key]!=='string')throw Error('资产历史文本无效');
  if(value.observation!==undefined){
   const v=value.observation;
   if(!object(v)||!['present','exited','unknown'].includes(String(v.coordinator))||typeof v.requires_attention!=='boolean'
    ||(v.error!=null&&typeof v.error!=='string'))throw Error('协调进程状态无效');
  }
  if(value.registration_observation!==undefined){
   const v=value.registration_observation;
   if(generation||!object(v)||!['matching','absent','conflict','unknown'].includes(String(v.state))
    ||(v.error!=null&&typeof v.error!=='string'))throw Error('登记核对状态无效');
  }
  ids.add(value.attempt_id);
  return value as AssetAttempt;
 });
}
export async function readAssetHistory(generation:boolean,signal:AbortSignal,fetcher:typeof fetch=fetch,timeoutMs=15000):Promise<AssetAttempt[]>{
 const controller=new AbortController();
 let timer:ReturnType<typeof setTimeout>|undefined;
 let cancel=()=>{};
 const stopped=new Promise<never>((_,reject)=>{
  cancel=()=>{controller.abort();reject(Error('历史读取已取消'))};
  if(signal.aborted){cancel();return}
  signal.addEventListener('abort',cancel,{once:true});
  timer=setTimeout(()=>{controller.abort();reject(Error('历史读取超时，显示的可能是旧记录'))},timeoutMs);
 });
 try{
  const work=(async()=>{
   if(signal.aborted)throw Error('历史读取已取消');
   const response=await fetcher('http://127.0.0.1:8765/blender/'+(generation?'generations':'imports'),{signal:controller.signal});
   const data=await response.json() as {ok?:unknown;attempts?:unknown}|null;
   if(!response.ok||!data||data.ok!==true||!Array.isArray(data.attempts))throw Error('资产历史响应无效');
   return parseAssetAttempts(data.attempts,generation);
  })();
  return await Promise.race([work,stopped]);
 }finally{clearTimeout(timer);signal.removeEventListener('abort',cancel)}
}
