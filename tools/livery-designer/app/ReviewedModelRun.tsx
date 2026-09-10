"use client";
import {useEffect, useRef, useState} from 'react';
import {supportsGeneratedScene} from './generatedModels';
import ExecutionProgress from './ExecutionProgress';

type Model = {id:string; name:string; enabled:boolean; status:string};
const bridge = 'http://127.0.0.1:8765';
export default function ReviewedModelRun({plan, disabled, onStarted}:{
  plan:Record<string,unknown>|null; disabled:boolean; onStarted?:()=>void;
}) {
  const [models,setModels] = useState<Model[]>([]);
  const [algorithm,setAlgorithm] = useState('uniad-tiny');
  const [confirmed,setConfirmed] = useState(false), [capture,setCapture] = useState(false);
  const [busy,setBusy] = useState(false), [active,setActive] = useState(true);
  const [error,setError] = useState(''), [readError,setReadError] = useState('');
  const locked = useRef(false);
  useEffect(()=>{setConfirmed(false)},[plan,algorithm,capture]);
  useEffect(()=>{
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>;
    let controller:AbortController;
    async function poll(){
      controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),10000);
      try {
        const response=await fetch(bridge+'/e2e/status',{signal:controller.signal});
        if(!response.ok)throw new Error('无法读取模型和任务状态');
        const value=await response.json() as {algorithms:Model[];job:{state:string;algorithm?:string}};
        if(!disposed){
          setModels(value.algorithms.filter(model=>supportsGeneratedScene(model.id)));
          setActive(['running','stopping','starting'].includes(value.job.state));
          if(['running','stopping','starting'].includes(value.job.state)&&value.job.algorithm&&supportsGeneratedScene(value.job.algorithm))setAlgorithm(value.job.algorithm);
          setReadError('');
        }
      } catch(e) {if(!disposed){setModels([]);setActive(true);setConfirmed(false);setReadError(String(e))}}
      finally {clearTimeout(timeout);if(!disposed)timer=setTimeout(poll,2000)}
    }
    void poll();
    return()=>{disposed=true;clearTimeout(timer);controller?.abort()};
  },[]);
  const selected=models.find(model=>model.id===algorithm);
  const ready=typeof plan?.scenario_path==='string'&&typeof plan?.scenario_sha256==='string';
  const unavailable=disabled||busy||active||!selected?.enabled||!ready;
  async function start(){
    if(locked.current||unavailable||!confirmed)return;
    locked.current=true;setBusy(true);setError('');setConfirmed(false);
    try {
      const response=await fetch(bridge+'/scenario/execute-plan',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({confirmed:true,algorithm,unified_capture:capture,
          scenario_path:plan!.scenario_path,scenario_sha256:plan!.scenario_sha256})});
      const result=await response.json() as {ok?:boolean;error?:string};
      if(!response.ok||result.ok===false)throw new Error(result.error||'启动失败');
      setActive(true);onStarted?.();
    } catch(e) {setError(`${String(e)}。请核对任务状态，不要重复启动。`)}
    finally {locked.current=false;setBusy(false)}
  }
  return <section aria-label="确认计划并选择模型" style={{fontSize:'1rem',margin:'16px 0'}}>
    <label>测试模型 <select aria-label="生成场景测试模型" value={algorithm} disabled={disabled||busy||active}
      onChange={event=>{setAlgorithm(event.target.value);setConfirmed(false)}}>
      {!models.length&&<option value="uniad-tiny">正在读取模型…</option>}
      {models.map(model=><option key={model.id} value={model.id} disabled={!model.enabled}>
        {model.name}{!model.enabled?'（依赖未就绪）':''}
      </option>)}
    </select></label>
    <p style={{fontSize:'14px'}}>模型文件就绪不等于启动预检通过。实际输入按所选模型保留，辅助传感器单独记录。</p>
    <label style={{display:'block'}}><input type="checkbox" checked={capture} disabled={disabled||busy||active}
      onChange={event=>{setCapture(event.target.checked);setConfirmed(false)}}/>测试时保存统一采集数据</label>
    <label style={{display:'block'}}><input type="checkbox" checked={confirmed} disabled={unavailable}
      onChange={event=>setConfirmed(event.target.checked)}/>我已检查当前计划，确认使用 {selected?.name||'所选模型'} 运行</label>
    <button className="primary" disabled={unavailable||!confirmed} onClick={()=>void start()}>
      {busy?'正在启动…':`确认计划并启动 ${selected?.name||'模型'}`}
    </button>
    {active&&!readError&&<p role="status">正在检查或等待当前任务结束。</p>}
    {readError&&<p role="alert">{readError}；暂不可启动，正在重新检查。</p>}
    {error&&<p role="alert">{error}</p>}
    <ExecutionProgress/>
  </section>;
}
