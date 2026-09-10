"use client";
import {useRef,useState} from 'react';
import {axes,parseTransformFields,transformFields,transformReview,type TransformFields,type TransformItem,type TransformReview} from './transformDraft';

export default function TransformEditor({item,editable,busy,onApply}:{item:TransformItem;editable:boolean;busy:boolean;onApply:(value:NonNullable<ReturnType<typeof parseTransformFields>>,expected:TransformReview)=>Promise<boolean>}){
 const [draft,setDraft]=useState<{fields:TransformFields;expected:TransformReview}|null>(null),[submitting,setSubmitting]=useState(false);
 const pending=useRef(false);
 const fields=draft?.fields??transformFields(item),parsed=parseTransformFields(fields),identityReady=!!item.edit_identity;
 async function apply(){
  if(!parsed||!draft||busy||pending.current||!editable)return;
  pending.current=true;setSubmitting(true);
  try{if(await onApply(parsed,draft.expected))setDraft(null)}finally{pending.current=false;setSubmitting(false)}
 }
 return <div aria-label="对象位置草稿">
  <div className="transform-grid">{axes.map(key=><label key={key}>{key.toUpperCase()}<input aria-label={'对象位置 '+key} type="number" step="0.5" disabled={!editable||!identityReady||busy||submitting} value={fields[key]} onChange={e=>{const expected=draft?.expected??transformReview(item);if(expected)setDraft({fields:{...fields,[key]:e.target.value},expected})}}/></label>)}</div>
  {editable?<><p role="status">{draft?'未应用草稿：后台刷新不会覆盖输入；切换对象或离开页面会放弃草稿。':'显示场景最新位置，输入后才形成草稿。'}</p>
   {!parsed&&<p role="alert">位置和角度必须是有限数值，不能留空。</p>}
   {!identityReady&&<p role="alert">尚无当前世界对象身份，请等待新版目录刷新。</p>}
   {draft&&<p>提交绑定开始编辑时的世界、对象和位置；对象已经移动时会拒绝旧草稿，请放弃后重新编辑。</p>}
   <button disabled={!draft||!parsed||!identityReady||busy||submitting} onClick={()=>void apply()}>Apply transform</button>
   <button disabled={!draft||busy||submitting} onClick={()=>setDraft(null)}>放弃草稿，读取最新位置</button>
  </>:<p>环境对象位置只读，可编辑纹理或可见性。</p>}
 </div>;
}
