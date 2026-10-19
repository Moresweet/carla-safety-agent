import {objectRestoreSelection,type ObjectRestoreSelection} from './deletionResult';
import {restoredObjectId} from './snapshotObjects';

export async function restoreObjectRequest(selection:ObjectRestoreSelection,confirmed:boolean,send:typeof fetch=fetch):Promise<number>{
 if(confirmed!==true||!objectRestoreSelection(selection))throw Error('必须确认有效的快照对象');
 try{
  const response=await send('http://127.0.0.1:8765/objects/restore-missing',{
   method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(30000),
   body:JSON.stringify({...selection,confirmed:true}),
  });
  const value=await response.json() as {ok?:boolean;error?:string};
  if(!response.ok||value?.ok!==true)throw Error(value?.error??'恢复未确认');
  return restoredObjectId(value,selection.stable_id);
 }catch(error){
  throw Error(String(error)+'；请检查当前场景对象后再决定是否重试，连接错误不证明操作未执行。');
 }
}
