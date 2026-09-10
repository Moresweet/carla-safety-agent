// Local isolated Chrome QA. Never launches a model. --stop-run explicitly stops
// one owned execution; --audit-dataset scans saved files without simulator RPC.
// Other modes only read UI/data or compile a plan.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import assert from 'node:assert/strict';

const profile=await mkdtemp(join(tmpdir(),'carla-browser-qa-'));
const output=resolve('runs/validation/browser-models-'+randomUUID());
await mkdir(output,{recursive:true});
const chrome=spawn('/usr/bin/google-chrome',['--headless=new','--disable-gpu','--no-first-run',
  '--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
let socket;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try {
  let port;
  for(let i=0;i<100;i++){
    if(chrome.exitCode!==null)throw new Error('Chrome exited before debugging became ready');
    try {port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{await delay(100)}
  }
  assert(port,'Chrome debugging port unavailable');
  const tab=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  socket=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
  let next=0;const pending=new Map();
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data);const item=pending.get(value.id);if(item){pending.delete(value.id);clearTimeout(item.timer);value.error?item.reject(Error(value.error.message)):item.resolve(value.result)}});
  const cdp=(method,params={})=>new Promise((resolve,reject)=>{const id=++next;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method))},20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))});
  const evaluate=async expression=>{const response=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.exceptionDetails)throw Error(JSON.stringify(response.exceptionDetails));return response.result.value};
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:'http://localhost:3000/'});
  for(let i=0;i<100;i++){if(await evaluate(`!![...document.querySelectorAll('button')].find(b=>b.textContent==='Generate Scene')`))break;await delay(200)}
  const buttons=await evaluate(`[...document.querySelectorAll('nav button')].map(b=>b.textContent)`);
  assert(buttons.includes('Generate Scene'));
  await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene').click()`);
  let models=[];
  for(let i=0;i<100;i++){
    models=await evaluate(`[...document.querySelectorAll('select[aria-label="生成场景测试模型"] option')].map(o=>({id:o.value,disabled:o.disabled}))`);
    if(models.length===5)break;await delay(200);
  }
  assert.deepEqual(models.map(m=>m.id).sort(),['admlp','tcp','uniad-base','uniad-tiny','vad']);
  const state=await evaluate(`(()=>{const section=document.querySelector('[aria-label="确认计划并选择模型"]');return {buttons:[...section.querySelectorAll('button')].map(b=>({text:b.textContent,disabled:b.disabled})),checkboxes:[...section.querySelectorAll('input')].map(b=>({checked:b.checked,disabled:b.disabled}))}})()`);
  assert(state.buttons[0].disabled,'Unreviewed plan must not start');
  const interactions=[];
  let stoppedExecution=null;
  if(process.argv.includes('--idle-controls')){
    const current=await (await fetch('http://127.0.0.1:8765/e2e/status')).json();
    assert(!['running','stopping'].includes(current.job.state),'Idle-only control test must not run during evaluation');
    await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Compile & preview').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`(()=>{const inputs=document.querySelectorAll('[aria-label="确认计划并选择模型"] input');return inputs.length===2&&!inputs[1].disabled})()`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Compiled plan did not enable review');
    await evaluate(`document.querySelectorAll('[aria-label="确认计划并选择模型"] input')[1].click()`);
    await delay(100);
    assert(await evaluate(`!document.querySelector('[aria-label="确认计划并选择模型"] button').disabled`));
    await evaluate(`(()=>{const s=document.querySelector('select[aria-label="生成场景测试模型"]');s.value='vad';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await delay(100);
    assert(await evaluate(`!document.querySelectorAll('[aria-label="确认计划并选择模型"] input')[1].checked&&document.querySelector('[aria-label="确认计划并选择模型"] button').disabled`));
    interactions.push('compile_enables_review','confirmation_enables_start','model_change_invalidates_confirmation');
  }
  const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await writeFile(join(output,'model-selection.png'),Buffer.from(screenshot.data,'base64'));
  if(process.argv.includes('--idle-controls')){
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='End-to-End Test').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`!![...document.querySelectorAll('button.algorithm-card')].find(b=>b.querySelector('strong')?.textContent==='VAD'&&!b.disabled)`);
      if(ready)break;await delay(200);
    }
    assert(ready,'VAD model card unavailable');
    await evaluate(`[...document.querySelectorAll('button.algorithm-card')].find(b=>b.querySelector('strong')?.textContent==='VAD').click()`);
    await delay(100);
    assert(await evaluate(`![...document.querySelectorAll('button')].find(b=>b.textContent==='Run generated scene').disabled`));
    interactions.push('vad_generated_scene_button_enabled');
  }
  const batchFlag=process.argv.indexOf('--batch');
  const stopFlag=process.argv.indexOf('--stop-run');
  if(stopFlag>=0){
    const execution=process.argv[stopFlag+1];
    assert(/^[a-f0-9]{32}$/.test(execution),'Expected an owned execution ID');
    assert(!process.argv.includes('--idle-controls'),'Do not combine idle controls and active stop');
    const current=await (await fetch('http://127.0.0.1:8765/e2e/status')).json();
    assert(current.stop_requires_run_id&&current.session.run_id===execution&&current.session.state==='running');
    let sent=null,interceptError=null;
    socket.addEventListener('message',async event=>{
      const value=JSON.parse(event.data);
      if(value.method!=='Fetch.requestPaused')return;
      const {requestId,request}=value.params;
      try{
        if(request.method==='OPTIONS'){
          await cdp('Fetch.continueRequest',{requestId});return;
        }
        const body=JSON.parse(request.postData||'{}');
        if(request.method!=='POST'||Object.keys(body).length!==1||body.run_id!==execution){
          await cdp('Fetch.failRequest',{requestId,errorReason:'Aborted'});
          throw Error('Browser attempted to stop a different execution');
        }
        sent=body;
        await cdp('Fetch.continueRequest',{requestId});
      }catch(error){interceptError=String(error)}
    });
    await cdp('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:8765/e2e/stop',requestStage:'Request'}]});
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='End-to-End Test').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`!![...document.querySelectorAll('.e2e-actions button')].find(b=>b.textContent==='Stop'&&!b.disabled)`);
      if(ready&&current.job.kind==='run'){
        ready=await evaluate(`document.querySelector('.e2e-control select').value===${JSON.stringify(current.job.route)}`);
      }
      if(ready)break;await delay(200);
    }
    assert(ready,'Owned model Stop button unavailable');
    await evaluate(`[...document.querySelectorAll('.e2e-actions button')].find(b=>b.textContent==='Stop').click()`);
    for(let i=0;i<100&&!sent&&!interceptError;i++)await delay(100);
    assert(!interceptError,interceptError);assert.deepEqual(sent,{run_id:execution});
    stoppedExecution=execution;
    await delay(500);
    await evaluate(`document.querySelector('.e2e-control').scrollIntoView({block:'center'})`);
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'owned-stop.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('owned_run_stop_button_sent_exact_identity');
  }
  if(batchFlag>=0){
    const batch=process.argv[batchFlag+1];
    assert(/^[a-f0-9]{32}$/.test(batch),'Expected a batch ID');
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='End-to-End Test').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`[...document.querySelectorAll('select[aria-label="选择批次"] option')].some(o=>o.value===${JSON.stringify(batch)})`);
      if(ready)break;
      await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent==='加载更多批次');if(b&&!b.disabled)b.click()})()`);
      await delay(200);
    }
    assert(ready,'Batch not listed');
    await evaluate(`(()=>{const s=document.querySelector('select[aria-label="选择批次"]');s.value=${JSON.stringify(batch)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    for(let i=0;i<100;i++){
      ready=await evaluate(`document.querySelectorAll('.batch-panel tbody tr').length===2&&document.querySelector('[aria-label="后台批量调度"]').textContent.includes('空配置保持当前编辑状态')`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Texture capability or paired batch rows missing');
    assert(await evaluate(`[...document.querySelectorAll('.algorithm-card>div:nth-child(2)')].every(e=>e.scrollWidth<=e.clientWidth+1)`),'Model descriptions overflow their sidebar cards');
    assert(await evaluate(`[...document.querySelectorAll('.batch-panel button')].find(b=>b.textContent==='开始后台串行测试').disabled`),'Read-only viewing must not authorize a start');
    await evaluate(`document.querySelector('.batch-panel').scrollIntoView({block:'start'})`);
    await delay(150);
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'batch-textures.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('texture_batch_capability_and_two_rows_visible','batch_start_remains_unconfirmed');
  }
  const datasetFlag=process.argv.indexOf('--dataset');
  if(datasetFlag>=0){
    const dataset=process.argv[datasetFlag+1];
    assert(/^capture-[A-Za-z0-9-]+$/.test(dataset),'Expected a capture dataset ID');
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Collect Data').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`[...document.querySelectorAll('select[aria-label="数据集"] option')].some(o=>o.value===${JSON.stringify(dataset)})`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Recorded dataset not listed');
    await evaluate(`(()=>{const s=document.querySelector('select[aria-label="数据集"]');s.value=${JSON.stringify(dataset)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    for(let i=0;i<100;i++){
      ready=await evaluate(`!!document.querySelector('[aria-label="回放索引质量"]')&&!!document.querySelector('.replay-controls a[download]')`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Replay metadata did not load');
    const quality=await evaluate(`document.querySelector('[aria-label="回放索引质量"]').textContent`);
    assert(quality.includes('严格递增')&&quality.includes('不等于传感器丢帧数量'));
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
    await writeFile(join(output,'replay-quality.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('recorded_dataset_quality_visible');
    if(process.argv.includes('--audit-dataset')){
      let available=false;
      for(let i=0;i<100;i++){
        available=await evaluate(`!!document.querySelector('[aria-label="原始数据质量检查"] button:not(:disabled)')`);
        if(available)break;await delay(200);
      }
      assert(available,'Raw dataset quality control unavailable');
      const auditStarted=Date.now()/1000;
      await evaluate(`document.querySelector('[aria-label="原始数据质量检查"] button').click()`);
      let report;
      for(let i=0;i<620;i++){
        report=await (await fetch('http://127.0.0.1:8765/datasets/quality?run_id='+encodeURIComponent(dataset))).json();
        if(['passed','failed','incomplete'].includes(report.state)&&report.finished_at_unix>=auditStarted)break;
        await delay(500);
      }
      assert.equal(report.run_id,dataset);
      assert.equal(report.state,'passed',JSON.stringify(report));
      assert(report.finished_at_unix>=auditStarted,'Did not observe the new scan');
      for(let i=0;i<30;i++){
        if(await evaluate(`document.querySelector('[aria-label="原始数据质量检查"]').textContent.includes('本次检查通过')`))break;
        await delay(200);
      }
      assert(await evaluate(`document.querySelector('[aria-label="原始数据质量检查"]').textContent.includes('本次检查通过')`));
      await evaluate(`document.querySelector('[aria-label="原始数据质量检查"]').scrollIntoView({block:'center'})`);
      const image=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'raw-quality.png'),Buffer.from(image.data,'base64'));
      await writeFile(join(output,'raw-quality-report.json'),JSON.stringify(report,null,2));
      interactions.push('raw_quality_button_scanned_saved_dataset_and_reported_pass');
    }
  }
  await writeFile(join(output,'report.json'),JSON.stringify({models,state,interactions,stoppedExecution,scope:'No model start; optional --stop-run only permits the explicitly supplied execution identity',profile},null,2));
  console.log(JSON.stringify({output,models,state,interactions}));
} finally {
  socket?.close();
  if(chrome.exitCode===null)chrome.kill('SIGTERM');
}
