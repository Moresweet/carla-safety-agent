"use client";
import {useRef,useState} from 'react';
import {axes,parseTransformFields,transformFields,type TransformFields,type TransformItem} from './transformDraft';

export default function TransformEditor({item,editable,busy,onApply}:{item:TransformItem;editable:boolean;busy:boolean;onApply:(value:NonNullable<ReturnType<typeof parseTransformFields>>)=>Promise<boolean>}){
 const [draft,setDraft]=useState<TransformFields|null>(null),[submitting,setSubmitting]=useState(false);
 const pending=useRef(false);
 const fields=draft??transformFields(item),parsed=parseTransformFields(fields);
 async function apply(){
  if(!parsed||!draft||busy||pending.current||!editable)return;
  pending.current=true;setSubmitting(true);
  try{if(await onApply(parsed))setDraft(null)}finally{pending.current=false;setSubmitting(false)}
 }
 return <div aria-label="对象位置草稿">
  <div className="transform-grid">{axes.map(key=><label key={key}>{key.toUpperCase()}<input aria-label={'对象位置 '+key} type="number" step="0.5" disabled={!editable||busy||submitting} value={fields[key]} onChange={e=>setDraft({...fields,[key]:e.target.value})}/></label>)}</div>
  {editable?<><p role="status">{draft?'未应用草稿：后台刷新不会覆盖输入；切换对象或离开页面会放弃草稿。':'显示场景最新位置，输入后才形成草稿。'}</p>
   {!parsed&&<p role="alert">位置和角度必须是有限数值，不能留空。</p>}
   <button disabled={!draft||!parsed||busy||submitting} onClick={()=>void apply()}>Apply transform</button>
   <button disabled={!draft||busy||submitting} onClick={()=>setDraft(null)}>放弃草稿，读取最新位置</button>
  </>:<p>环境对象位置只读，可编辑纹理或可见性。</p>}
 </div>;
}
