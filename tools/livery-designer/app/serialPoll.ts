// One outstanding read per poller, including explicit refreshes. The caller
// owns the read timeout; stop also aborts an in-flight read on page unmount.
export function serialPoll(read:(signal:AbortSignal)=>Promise<void>,intervalMs:number){
 const controller=new AbortController();
 let pending:Promise<void>|null=null,timer:ReturnType<typeof setTimeout>|undefined;
 const refresh=():Promise<void>=>{
  if(controller.signal.aborted)return Promise.resolve();
  if(pending)return pending;
  clearTimeout(timer);
  pending=Promise.resolve().then(()=>{controller.signal.throwIfAborted();return read(controller.signal)}).catch(error=>{
   if(!controller.signal.aborted)throw error;
  }).finally(()=>{pending=null;if(!controller.signal.aborted)timer=setTimeout(()=>{void refresh().catch(()=>{})},intervalMs)});
  return pending;
 };
 return {refresh,stop:()=>{controller.abort();clearTimeout(timer)}};
}
