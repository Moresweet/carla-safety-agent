// Local isolated Chrome QA. Never launches a model. --stop-run explicitly stops
// one owned execution; --audit-dataset scans saved files without simulator RPC.
// --apply-pedestrian explicitly applies a texture to the supplied walker ID.
// Other modes only read UI/data or compile a plan.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import assert from 'node:assert/strict';
import {textureUploadFlipY} from './livery-designer/app/uvConvention.ts';

const profile=await mkdtemp(join(tmpdir(),'carla-browser-qa-'));
const output=resolve('runs/validation/browser-models-'+randomUUID());
await mkdir(output,{recursive:true});
const chrome=spawn('/usr/bin/google-chrome',['--headless=new','--disable-gpu','--no-first-run',
  '--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
let socket, diagnosticCDP;
const browserErrors=[];
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
  diagnosticCDP=cdp;
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.method==='Runtime.exceptionThrown')browserErrors.push(value.params)});
  await cdp('Runtime.enable');
  await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  if(process.argv.includes('--simulate-no-webgl')){
    await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(kind,...args){return kind==='webgl'?null:original.call(this,kind,...args)}})()`});
  }
  await cdp('Page.navigate',{url:'http://localhost:3000/'});
  if(process.argv.includes('--simulate-no-webgl')){
    for(let i=0;i<100;i++){if(await evaluate(`document.readyState==='complete'`))break;await delay(100)}
    assert(await evaluate(`document.createElement('canvas').getContext('webgl')===null`),'WebGL fault injection did not activate');
  }
  for(let i=0;i<100;i++){if(await evaluate(`!![...document.querySelectorAll('button')].find(b=>b.textContent==='Generate Scene')`))break;await delay(200)}
  const buttons=await evaluate(`[...document.querySelectorAll('nav button')].map(b=>b.textContent)`);
  assert(buttons.includes('Generate Scene'));
  await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene').click()`);
  let models=[];
  for(let i=0;i<100;i++){
    models=await evaluate(`[...document.querySelectorAll('select[aria-label="生成场景测试模型"] option')].map(o=>({id:o.value,disabled:o.disabled}))`);
    if(models.length===5)break;
    // Server-rendered navigation can precede React hydration. Re-selecting
    // this read-only tab is idempotent; never retry mutation buttons here.
    if(i%5===0)await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene')?.click()`);
    await delay(200);
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
  if(process.argv.includes('--uv-convention')){
    const pixels=await evaluate(`(()=>{
      const canvas=document.createElement('canvas');canvas.width=canvas.height=8;
      const gl=canvas.getContext('webgl');if(!gl)throw Error('WebGL unavailable');
      const make=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s};
      const p=gl.createProgram();gl.attachShader(p,make(gl.VERTEX_SHADER,'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'));
      gl.attachShader(p,make(gl.FRAGMENT_SHADER,'precision mediump float;uniform sampler2D t;uniform vec2 uv;void main(){gl_FragColor=texture2D(t,uv);}'));gl.linkProgram(p);gl.useProgram(p);
      const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
      const loc=gl.getAttribLocation(p,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
      const image=document.createElement('canvas');image.width=image.height=2;const ctx=image.getContext('2d');
      for(const [x,y,color] of [[0,0,'red'],[1,0,'lime'],[0,1,'blue'],[1,1,'yellow']]){ctx.fillStyle=color;ctx.fillRect(x,y,1,1)}
      const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,${JSON.stringify(textureUploadFlipY(true))});gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
      const values=[];for(const uv of [[.25,.25],[.75,.25],[.25,.75],[.75,.75]]){gl.uniform2fv(gl.getUniformLocation(p,'uv'),uv);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);const value=new Uint8Array(4);gl.readPixels(4,4,1,1,gl.RGBA,gl.UNSIGNED_BYTE,value);values.push([...value])}
      gl.deleteTexture(texture);gl.deleteBuffer(buffer);gl.deleteProgram(p);return values;
    })()`);
    assert.deepEqual(pixels,[[255,0,0,255],[0,255,0,255],[0,0,255,255],[255,255,0,255]]);
    await writeFile(join(output,'uv-pixel-probe.json'),JSON.stringify({pixels,scope:'Source UV samples match top-left canvas rows using production upload convention'},null,2));
    interactions.push('webgl_source_uv_samples_match_canvas_rows');
  }
  const pedestrianFlag=process.argv.indexOf('--pedestrian-id');
  const vehicleFlag=process.argv.indexOf('--vehicle-id');
  assert(!(pedestrianFlag>=0&&vehicleFlag>=0),'Choose one actor preview');
  if(pedestrianFlag>=0||vehicleFlag>=0){
    const vehicle=vehicleFlag>=0,kind=vehicle?'vehicle':'pedestrian';
    const actor=Number(process.argv[(vehicle?vehicleFlag:pedestrianFlag)+1]);assert(Number.isSafeInteger(actor)&&actor>0);
    const textureFlag=process.argv.indexOf('--texture');assert(textureFlag>=0);
    const texture=resolve(process.argv[textureFlag+1]);await readFile(texture);
    const scene=await (await fetch('http://127.0.0.1:8765/scene/state')).json();
    const target=scene.objects.find(item=>item.id===actor&&(vehicle?item.name==='vehicle.audi.a2':item.name==='walker.pedestrian.0001'));assert(target,'Requested supported actor is not in the current scene');
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Edit World').click()`);
    await evaluate(`[...document.querySelectorAll('.viewtabs button')].find(b=>b.textContent===${JSON.stringify(vehicle?'Vehicles':'Pedestrians')}).click()`);
    let ready=false;
    for(let i=0;i<100;i++){ready=await evaluate(`[...document.querySelectorAll('#target option')].some(o=>o.value===${JSON.stringify(target.key)})`);if(ready)break;await delay(200)}
    assert(ready,'Walker target option missing');
    await evaluate(`(()=>{const select=document.querySelector('#target');select.value=${JSON.stringify(target.key)};select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    for(let i=0;i<100;i++){ready=await evaluate(`!![...document.querySelectorAll('.previewbar b')].find(e=>e.textContent.includes(${JSON.stringify(vehicle?'vehicle.audi.a2':'裤装槽 14')}))&&!!document.querySelector('.projection canvas')`);if(ready)break;await delay(200)}
    assert(ready,'Actual pedestrian mesh preview missing');
    const documentNode=await cdp('DOM.getDocument');const input=await cdp('DOM.querySelector',{nodeId:documentNode.root.nodeId,selector:'.controls input[type=file]'});
    await cdp('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[texture]});
    for(let i=0;i<100;i++){ready=await evaluate(`!document.querySelector('.export button.primary').disabled`);if(ready)break;await delay(100)}
    assert(ready,'Texture upload did not enable the explicit walker action');
    await evaluate(`[...document.querySelectorAll('.texture-modes button')].find(b=>b.textContent==='cover').click()`);
    await delay(200);
    const atlas=await evaluate(`document.querySelector('canvas.atlas-output').toDataURL('image/png')`);
    await writeFile(join(output,kind+'-atlas.png'),Buffer.from(atlas.split(',')[1],'base64'));
    await evaluate(`document.querySelector('.visuals').scrollIntoView({block:'start'})`);
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,kind+'-uv.png'),Buffer.from(screenshot.data,'base64'));
    if(process.argv.includes('--apply-'+kind)){
      let sent=false,error=null;
      socket.addEventListener('message',async event=>{const value=JSON.parse(event.data);if(value.method!=='Fetch.requestPaused')return;
        const {requestId,request}=value.params;try{const url=new URL(request.url);
          if(url.pathname!==(vehicle?'/apply':'/apply/pedestrian')||url.searchParams.get('actor_id')!==String(actor)){
            await cdp('Fetch.failRequest',{requestId,errorReason:'Aborted'});throw Error('Unexpected texture target');}
          if(request.method==='POST')sent=true;await cdp('Fetch.continueRequest',{requestId});
        }catch(exc){error=String(exc)}});
      await cdp('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:8765/apply*',requestStage:'Request'}]});
      await evaluate(`document.querySelector('.export button.primary').click()`);
      for(let i=0;i<200;i++){ready=await evaluate(`document.querySelector('.export small').textContent.startsWith('Applied texture to ')`);if(ready||error)break;await delay(100)}
      assert(!error,error);assert(sent&&ready,'Explicit pedestrian texture did not complete');
      interactions.push(kind+'_texture_applied_to_explicit_actor_'+actor);
    }
    interactions.push(vehicle?'audi_a2_source_uv_preview_loaded':'real_pedestrian_slot14_uv_preview_loaded');
  }
  if(process.argv.includes('--texture-scope')){
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Edit World').click()`);
    await evaluate(`[...document.querySelectorAll('.viewtabs button')].find(b=>b.textContent==='Roads').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`document.querySelector('.export p')?.textContent.includes('道路集合')`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Road collection scope warning missing');
    assert(await evaluate(`document.querySelector('.export button.primary').disabled`),'Road collection must not silently edit all roads');
    await evaluate(`document.querySelector('.export').scrollIntoView({block:'start'})`);
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'texture-scope.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('road_collection_requires_exact_object_selection');
  }
  const materialFlag=process.argv.indexOf('--material-name');
  if(materialFlag>=0){
    const name=process.argv[materialFlag+1];assert(name==='SM_GasStation01_13','Only the verified fixture is supported');
    const textureFlag=process.argv.indexOf('--texture');assert(textureFlag>=0);
    const texture=resolve(process.argv[textureFlag+1]);await readFile(texture);
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Edit World').click()`);
    for(let i=0;i<100;i++){if(await evaluate(`!!document.querySelector('.catalog-list input')`))break;await delay(200)}
    await evaluate(`(()=>{const input=document.querySelector('.catalog-list input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(name)});input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    let ready=false;
    for(let i=0;i<100;i++){ready=await evaluate(`document.querySelector('.object-inspector h3')?.textContent.startsWith(${JSON.stringify(name)})`);if(ready)break;await delay(200)}
    assert(ready,'Requested material object not found');
    await evaluate(`[...document.querySelectorAll('.object-inspector button')].find(b=>b.textContent==='Edit texture').click()`);
    for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('.material-slot-editor select option:not([disabled])')&&!!document.querySelector('.material-slot-editor .preview canvas')`);if(ready)break;await delay(200)}
    assert(ready,'Material mesh selection unavailable');
    const documentNode=await cdp('DOM.getDocument'),input=await cdp('DOM.querySelector',{nodeId:documentNode.root.nodeId,selector:'.material-slot-editor input[type=file]'});
    await cdp('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[texture]});
    for(let i=0;i<100;i++){ready=await evaluate(`![...document.querySelectorAll('.material-slot-editor button')].find(b=>b.textContent==='应用到此材质槽').disabled`);if(ready)break;await delay(200)}
    assert(ready,'Material upload or mesh load failed');
    if(process.argv.includes('--simulate-no-webgl')){
      assert(await evaluate(`document.querySelector('.preview [role=alert]')?.textContent.includes('WebGL unavailable')`));
      interactions.push('missing_webgl_is_local_preview_error');
    }
    await delay(300);
    const atlas=await evaluate(`document.querySelector('canvas.atlas-output').toDataURL('image/png')`);
    await writeFile(join(output,'material-atlas.png'),Buffer.from(atlas.split(',')[1],'base64'));
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'material-uv.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('environment_source_uv_preview_loaded_without_apply');
  }
  const importJobFlag=process.argv.indexOf('--import-job');
  if(importJobFlag>=0){
    const job=process.argv[importJobFlag+1];assert(/^[a-zA-Z0-9]+$/.test(job));
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Asset Workshop').click()`);
    let ready=false;
    for(let i=0;i<100;i++){ready=await evaluate(`document.querySelector('.asset-import-history')?.textContent.includes(${JSON.stringify(job)})`);if(ready)break;await delay(200)}
    assert(ready,'Persisted import job not visible');
    const text=await evaluate(`document.querySelector('.asset-import-history').textContent`);
    assert(text.includes('已登记')&&text.includes('需要处理'),'Both success and rejected attempt should remain visible');
    await evaluate(`(()=>{const section=document.querySelector('.asset-import-history');for(const d of section.querySelectorAll('details'))if(d.textContent.includes(${JSON.stringify(job)}))d.open=true;section.scrollIntoView({block:'start'});})()`);
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'asset-import-history.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('persistent_import_success_and_failure_visible_without_mutation');
  }
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
    if(process.argv.includes('--depth-diagnostic')){
      await evaluate(`document.querySelector('input[aria-label="RGB点云投影"]').click()`);
      await delay(100);
      await evaluate(`document.querySelector('input[aria-label="点云深度交叉检查"]').click()`);
      let ready=false;
      for(let i=0;i<100;i++){
        ready=await evaluate(`document.querySelectorAll('svg[aria-label*="深度交叉检查，非遮挡真值"]').length===6`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Six depth diagnostics failed to load');
      await evaluate(`document.querySelector('input[aria-label="RGB点云投影"]').scrollIntoView({block:'start'})`);
      const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'depth-diagnostic.png'),Buffer.from(screenshot.data,'base64'));
      interactions.push('six_saved_camera_depth_cross_checks_visible');
    }
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
  await writeFile(join(output,'report.json'),JSON.stringify({models,state,interactions,stoppedExecution,scope:'No model start; optional stop/texture writes are restricted to the explicitly supplied execution/actor identity',profile},null,2));
  console.log(JSON.stringify({output,models,state,interactions}));
} catch(error) {
  await writeFile(join(output,'failure.json'),JSON.stringify({error:String(error),browserErrors},null,2));
  if(diagnosticCDP){
    try {
      const shot=await diagnosticCDP('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'failure.png'),Buffer.from(shot.data,'base64'));
      const body=await diagnosticCDP('Runtime.evaluate',{expression:'document.body.innerText',returnByValue:true});
      await writeFile(join(output,'failure-page.txt'),body.result.value||'');
    } catch(diagnosticError){console.error('Failure diagnostics:',String(diagnosticError))}
  }
  console.error('Failure evidence:',output);
  throw error;
} finally {
  socket?.close();
  if(chrome.exitCode===null)chrome.kill('SIGTERM');
}
