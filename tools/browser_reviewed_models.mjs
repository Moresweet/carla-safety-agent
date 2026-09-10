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
  const unknownActorFlag=process.argv.indexOf('--unknown-actor');
  if(unknownActorFlag>=0){
    const actorId=process.argv[unknownActorFlag+1];assert(/^\d+$/.test(actorId));
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Edit World').click()`);
    for(let i=0;i<100;i++){
      if(await evaluate(`!![...document.querySelectorAll('.catalog-groups button')].find(b=>b.textContent.includes('spawned props'))`))break;
      await delay(200);
    }
    await evaluate(`[...document.querySelectorAll('.catalog-groups button')].find(b=>b.textContent.includes('spawned props')).click()`);
    await evaluate(`(()=>{const e=document.querySelector('select[aria-label="对象来源"]');e.value='unknown';e.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    let found=false;
    for(let i=0;i<100;i++){
      found=await evaluate(`!![...document.querySelectorAll('.catalog-list select[size] option')].find(o=>o.value===${JSON.stringify('actor:'+actorId)}&&o.textContent.startsWith('[来源未知]'))`);
      if(found)break;await delay(200);
    }
    assert(found,'Untracked native actor must be shown as unknown');
    const originHeight=await evaluate(`document.querySelector('select[aria-label="对象来源"]').getBoundingClientRect().height`);
    assert(originHeight>=30&&originHeight<=50,'Origin dropdown must not inherit the tall object-list layout');
    assert(await evaluate(`![...document.querySelectorAll('.catalog-list select[size] option')].some(o=>o.textContent.includes('[场景原有]'))`));
    await evaluate(`document.querySelector('.object-manager').scrollIntoView()`);
    const shot=await cdp('Page.captureScreenshot',{format:'png'});
    await writeFile(join(output,'unknown-origin.png'),Buffer.from(shot.data,'base64'));
    interactions.push('native_unknown_origin_filter_visible');
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene').click()`);
  }
  let stoppedExecution=null;
  const bundleSceneFlag=process.argv.indexOf('--bundle-scene');
  if(bundleSceneFlag>=0){
    const sceneId=process.argv[bundleSceneFlag+1];assert(/^[a-zA-Z0-9_-]{1,80}$/.test(sceneId));
    await evaluate(`document.querySelector('.project-panel').open=true`);
    let selectorReady=false;
    for(let i=0;i<100;i++){
      selectorReady=await evaluate(`!![...document.querySelectorAll('.project-panel select option')].find(o=>o.value===${JSON.stringify(sceneId)})`);
      if(selectorReady)break;await delay(200);
    }
    assert(selectorReady,'Saved scene unavailable');
    await evaluate(`(()=>{const option=[...document.querySelectorAll('.project-panel select option')].find(o=>o.value===${JSON.stringify(sceneId)});const select=option.parentElement;select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await delay(100);
    assert(await evaluate(`!document.querySelector('.bundle-panel button').disabled`));
    if(process.argv.includes('--bundle-previews')){
      await evaluate(`document.querySelector('.bundle-panel input[type=checkbox]').click()`);await delay(100);
    }
    if(process.argv.includes('--bundle-sources')){
      await evaluate(`document.querySelectorAll('.bundle-panel input[type=checkbox]')[1].click()`);await delay(100);
    }
    const referenceFlag=process.argv.indexOf('--bundle-reference');
    if(referenceFlag>=0){
      const referencePath=resolve(process.argv[referenceFlag+1]);await readFile(referencePath);
      const root=await cdp('DOM.getDocument'),input=await cdp('DOM.querySelector',{nodeId:root.root.nodeId,selector:'input[aria-label="模型引用 JSON"]'});
      await cdp('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[referencePath]});
      let loaded=false;
      for(let i=0;i<100;i++){loaded=await evaluate(`[...document.querySelectorAll('.bundle-panel button')].some(b=>b.textContent==='移除模型引用'&&!b.disabled)`);if(loaded)break;await delay(100)}
      assert(loaded,'Runtime reference did not load');
    }
    await evaluate(`[...document.querySelectorAll('.bundle-panel button')].find(b=>b.textContent==='导出选中场景包').click()`);
    let download;
    for(let i=0;i<150;i++){download=await evaluate(`document.querySelector('.bundle-panel a')?.href`);if(download)break;await delay(200)}
    assert(download,'Export download was not provided');
    const exportedId=new URL(download).searchParams.get('bundle_id');
    const response=await fetch(download);assert(response.ok);
    const packagePath=join(output,'browser-export.zip');await writeFile(packagePath,Buffer.from(await response.arrayBuffer()));
    const documentNode=await cdp('DOM.getDocument'),input=await cdp('DOM.querySelector',{nodeId:documentNode.root.nodeId,selector:'input[aria-label="项目 ZIP"]'});
    await cdp('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[packagePath]});
    let uploadedId;
    for(let i=0;i<150;i++){
      const link=await evaluate(`document.querySelector('.bundle-panel a')?.href`);
      uploadedId=link&&new URL(link).searchParams.get('bundle_id');
      if(uploadedId&&uploadedId!==exportedId)break;await delay(200);
    }
    assert(uploadedId&&uploadedId!==exportedId,'Did not observe new validated upload');
    await evaluate(`[...document.querySelectorAll('.bundle-details button')].find(b=>b.textContent==='检查本机依赖（不切换地图）').click()`);
    let diagnostic;
    for(let i=0;i<100;i++){diagnostic=await evaluate(`document.querySelector('[aria-label="项目包依赖检查"]')?.textContent`);if(diagnostic)break;await delay(200)}
    assert(diagnostic,'Dependency observation unavailable');
    assert(await evaluate(`[...document.querySelectorAll('.bundle-details button')].find(b=>b.textContent==='隔离导入已检查项目包').disabled`),'Import must require confirmation');
    await evaluate(`document.querySelector('.bundle-details input[type=checkbox]').click()`);await delay(100);
    await evaluate(`[...document.querySelectorAll('.bundle-details button')].find(b=>b.textContent==='隔离导入已检查项目包').click()`);
    let imported;
    for(let i=0;i<150;i++){imported=await evaluate(`document.querySelector('.bundle-panel [role=status]').textContent`);if(imported.startsWith('已隔离导入到：'))break;await delay(200)}
    assert(imported.startsWith('已隔离导入到：'),imported);
    assert(imported.includes('导入目录尚未配置运行环境'));
    assert(!await evaluate(`!!document.querySelector('.bundle-panel [role=alert]')`));
    await evaluate(`document.querySelector('.bundle-panel').scrollIntoView({block:'start'})`);
    const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'project-bundle.png'),Buffer.from(shot.data,'base64'));
    let restoreStatus=null,registeredBundleId=null;
    if(process.argv.includes('--bundle-register')){
      assert(process.argv.includes('--bundle-sources'),'Registration test requires source packaging');
      await evaluate(`document.querySelector('[aria-label="项目包源资产注册"]').scrollIntoView({block:'center'})`);
      assert(await evaluate(`document.querySelector('[aria-label="项目包源资产注册"] button').disabled`));
      await evaluate(`document.querySelector('[aria-label="确认注册项目包源资产"]').click()`);await delay(100);
      await evaluate(`document.querySelector('[aria-label="项目包源资产注册"] button').click()`);
      let registration;
      for(let i=0;i<1200;i++){
        const requestId=await evaluate(`sessionStorage.getItem('bundle-registration:'+${JSON.stringify(uploadedId)})`);
        if(requestId){
          const r=await fetch('http://127.0.0.1:8765/projects/bundle/registration?request_id='+requestId);
          registration=await r.json();
          assert(registration.state!=='needs_attention',JSON.stringify(registration));
          if(registration.state==='registered')break;
        }
        const error=await evaluate(`document.querySelector('[aria-label="项目包源资产注册"] [role=alert]')?.textContent`);
        assert(!error,error);await delay(500);
      }
      assert.equal(registration?.state,'registered','Native registration did not finish');
      await writeFile(join(output,'bundle-registration-report.json'),JSON.stringify(registration,null,2));
      registeredBundleId=registration.output_bundle_id;
      let open=false;
      for(let i=0;i<50;i++){open=await evaluate(`[...document.querySelectorAll('[aria-label="项目包源资产注册"] button')].some(b=>b.textContent==='打开已注册的新项目包'&&!b.disabled)`);if(open)break;await delay(200)}
      assert(open,'New registered package action unavailable');
      const registered=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'bundle-registration-completed.png'),Buffer.from(registered.data,'base64'));
      await evaluate(`[...document.querySelectorAll('[aria-label="项目包源资产注册"] button')].find(b=>b.textContent==='打开已注册的新项目包').click()`);
      let opened=false;
      for(let i=0;i<50;i++){opened=await evaluate(`document.querySelector('.bundle-panel a')?.href.includes(${JSON.stringify(registeredBundleId)})`);if(opened)break;await delay(200)}
      assert(opened,'New remapped package was not opened');
      interactions.push('confirmed_native_source_registration_opened_new_remapped_package');
    }
    if(process.argv.includes('--bundle-restore')){
      await evaluate(`[...document.querySelectorAll('[aria-label="项目包实景恢复"] button')].find(b=>b.textContent==='预览实景恢复范围').click()`);
      let ready=false;
      for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('[aria-label="实景恢复范围"]')`);if(ready)break;await delay(200)}
      assert(ready,'World restore preview unavailable');
      assert(await evaluate(`[...document.querySelectorAll('[aria-label="项目包实景恢复"] button')].find(b=>b.textContent==='确认恢复当前实景').disabled`));
      await evaluate(`document.querySelector('[aria-label="项目包实景恢复"]').scrollIntoView({block:'start'})`);
      const preview=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'bundle-restore-preview.png'),Buffer.from(preview.data,'base64'));
      await evaluate(`document.querySelector('input[aria-label="确认实景恢复"]').click()`);await delay(100);
      await evaluate(`[...document.querySelectorAll('[aria-label="项目包实景恢复"] button')].find(b=>b.textContent==='确认恢复当前实景').click()`);
      for(let i=0;i<150;i++){restoreStatus=await evaluate(`document.querySelector('[aria-label="项目包实景恢复"] [role=status]').textContent`);if(restoreStatus.startsWith('实景已同地图合并恢复'))break;await delay(200)}
      assert(restoreStatus.startsWith('实景已同地图合并恢复'),restoreStatus);
      assert(!await evaluate(`!!document.querySelector('[aria-label="项目包实景恢复"] [role=alert]')`));
      const restored=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'bundle-restore-completed.png'),Buffer.from(restored.data,'base64'));
      interactions.push('reviewed_confirmed_same_map_world_restore_with_baseline_backup');
    }
    await writeFile(join(output,'bundle-report.json'),JSON.stringify({sceneId,exportedId,uploadedId,registeredBundleId,imported,diagnostic,restoreStatus},null,2));
    interactions.push('saved_scene_export_uploaded_validated_and_explicitly_imported_to_isolated_directory');
  }
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
    const name=process.argv[materialFlag+1];assert(['SM_GasStation01_13','SM_Bench01_123','Road_Road_Town04_1'].includes(name),'Only bounded material fixtures are supported');
    const textureFlag=process.argv.indexOf('--texture');assert(textureFlag>=0);
    const texture=resolve(process.argv[textureFlag+1]);await readFile(texture);
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Edit World').click()`);
    for(let i=0;i<100;i++){if(await evaluate(`!!document.querySelector('.catalog-list input')`))break;await delay(200)}
    if(name==='SM_Bench01_123'||name==='Road_Road_Town04_1'){
      const category=name==='SM_Bench01_123'?'static props':'roads';
      let categoryReady=false;
      for(let i=0;i<100;i++){
        categoryReady=await evaluate(`[...document.querySelectorAll('.catalog-groups button')].some(b=>b.querySelector('span')?.textContent===${JSON.stringify(category)})`);
        if(categoryReady)break;await delay(200);
      }
      assert(categoryReady,'Requested material category did not load');
      await evaluate(`[...document.querySelectorAll('.catalog-groups button')].find(b=>b.querySelector('span')?.textContent===${JSON.stringify(category)}).click()`);
    }
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
    if(name==='Road_Road_Town04_1'){
      await evaluate(`[...document.querySelectorAll('.material-slot-editor button')].find(b=>b.textContent==='cover surface').click()`);
    }
    if(process.argv.includes('--simulate-no-webgl')){
      assert(await evaluate(`document.querySelector('.preview [role=alert]')?.textContent.includes('WebGL unavailable')`));
      interactions.push('missing_webgl_is_local_preview_error');
    }
    await delay(300);
    const atlas=await evaluate(`document.querySelector('canvas.atlas-output').toDataURL('image/png')`);
    await writeFile(join(output,'material-atlas.png'),Buffer.from(atlas.split(',')[1],'base64'));
    if(name==='Road_Road_Town04_1'){
      const beforeZoom=await evaluate(`document.querySelector('.preview canvas').toDataURL()`);
      await evaluate(`(()=>{const input=document.querySelector('[aria-label="3D预览缩放"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'4');input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
      await delay(300);
      assert.equal(await evaluate(`document.querySelector('[aria-label="3D预览缩放"]').value`),'4');
      assert.notEqual(await evaluate(`document.querySelector('.preview canvas').toDataURL()`),beforeZoom,'Zoom must redraw real geometry');
      const enlarged=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'material-uv-zoom.png'),Buffer.from(enlarged.data,'base64'));
      await evaluate(`[...document.querySelectorAll('.preview button')].find(b=>b.textContent==='重置3D视图').click()`);
      await delay(300);
      assert.equal(await evaluate(`document.querySelector('[aria-label="3D预览缩放"]').value`),'1');
      assert.equal(await evaluate(`document.querySelector('canvas.atlas-output').toDataURL('image/png')`),atlas,'Preview zoom must not edit the applied atlas');
      interactions.push('road_preview_zoom_and_reset_without_texture_changes');
    }
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
    let dataset=process.argv[datasetFlag+1];
    assert(/^(capture-[A-Za-z0-9-]+|recovered-[a-f0-9]{32})$/.test(dataset),'Expected a capture dataset ID');
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
    if(process.argv.includes('--recover-capture')){
      assert(dataset.startsWith('capture-'),'Recovery must start from an original recording');
      await delay(3500);
      assert.equal(await evaluate(`document.querySelectorAll('[aria-label="恢复中断录制"]').length`),1,'Recovery panel must not duplicate after catalog polling');
      assert.equal(await evaluate(`document.querySelectorAll('[aria-label="原始数据质量检查"]').length`),1,'Quality panel must not duplicate');
      await evaluate(`document.querySelector('[aria-label="恢复中断录制"]').scrollIntoView({block:'center'})`);
      assert(await evaluate(`document.querySelector('[aria-label="恢复中断录制"] button').disabled`));
      await evaluate(`document.querySelector('[aria-label="确认创建恢复副本"]').click()`);
      for(let i=0;i<30;i++){
        if(await evaluate(`!document.querySelector('[aria-label="恢复中断录制"] button').disabled`))break;
        await delay(100);
      }
      assert(await evaluate(`!document.querySelector('[aria-label="恢复中断录制"] button').disabled`));
      await evaluate(`document.querySelector('[aria-label="恢复中断录制"] button').click()`);
      let requestId;
      for(let i=0;i<620;i++){
        requestId=await evaluate(`sessionStorage.getItem('capture-recovery:'+${JSON.stringify(dataset)})`);
        if(requestId){
          const response=await fetch('http://127.0.0.1:8765/datasets/recovery?request_id='+requestId);
          const recovery=await response.json();
          if(recovery.state==='recovered'){
            await writeFile(join(output,'capture-recovery-report.json'),JSON.stringify(recovery,null,2));
            dataset=recovery.recovered_run_id;break;
          }
          assert(!['failed','needs_attention'].includes(recovery.state),JSON.stringify(recovery));
        }
        await delay(500);
      }
      assert(dataset.startsWith('recovered-'),'Recovery did not finish');
      for(let i=0;i<30;i++){
        ready=await evaluate(`[...document.querySelectorAll('[aria-label="恢复中断录制"] button')].some(b=>b.textContent==='打开恢复副本回放')`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Verified recovery action not displayed');
      const recoveredShot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'capture-recovery-complete.png'),Buffer.from(recoveredShot.data,'base64'));
      await evaluate(`[...document.querySelectorAll('[aria-label="恢复中断录制"] button')].find(b=>b.textContent==='打开恢复副本回放').click()`);
      for(let i=0;i<100;i++){
        ready=await evaluate(`document.querySelector('select[aria-label="数据集"]').value===${JSON.stringify(dataset)}&&!!document.querySelector('[aria-label="中断采集恢复提示"]')&&!!document.querySelector('.replay-controls a[download]')`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Recovered copy not ready for playback');
      interactions.push('explicit_browser_recovery_created_and_opened_verified_copy');
    }
    if(dataset.startsWith('recovered-')){
      const warning=await evaluate(`document.querySelector('[aria-label="中断采集恢复提示"]')?.textContent`);
      assert(warning?.includes('不是完整录制')&&warning.includes('原始目录保留'));
      interactions.push('recovered_subset_warning_visible');
    }
    const replayIndexFlag=process.argv.indexOf('--replay-index');
    if(replayIndexFlag>=0){
      const position=Number(process.argv[replayIndexFlag+1]);assert(Number.isInteger(position)&&position>=0);
      const index=await (await fetch('http://127.0.0.1:8765/datasets/index?run_id='+encodeURIComponent(dataset))).json();
      assert(position<index.frames.length);
      const wanted=index.frames[position].frame;
      await evaluate(`(()=>{const slider=document.querySelector('input[aria-label="回放时间轴"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(slider,${position});slider.dispatchEvent(new Event('input',{bubbles:true}));slider.dispatchEvent(new Event('change',{bubbles:true}));})()`);
      for(let i=0;i<100;i++){ready=await evaluate(`document.querySelector('[aria-label="真实轨迹与预测对比"]')?.getAttribute('data-frame')===${JSON.stringify(String(wanted))}`);if(ready)break;await delay(200)}
      assert(ready,'Requested replay frame did not render');
    }
    const quality=await evaluate(`document.querySelector('[aria-label="回放索引质量"]').textContent`);
    assert(quality.includes('严格递增')&&quality.includes('不等于传感器丢帧数量'));
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
    await writeFile(join(output,'replay-quality.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('recorded_dataset_quality_visible');
    if(process.argv.includes('--prediction-overlay')||process.argv.includes('--legacy-prediction-no-overlay')||process.argv.includes('--warmup-no-prediction')){
      let trackText;
      for(let i=0;i<100;i++){
        trackText=await evaluate(`document.querySelector('[aria-label="真实轨迹与预测对比"]')?.textContent`);
        if(trackText&&(trackText.includes('绿色点线')||trackText.includes('不叠加模型预测')))break;
        await delay(200);
      }
      assert(trackText,'Trajectory comparison unavailable');
      const count=await evaluate(`document.querySelectorAll('[aria-label="真实轨迹与预测对比"] circle[fill="#5de2bc"]').length`);
      if(process.argv.includes('--prediction-overlay')){
        assert(count>0&&trackText.includes('不计算 ADE/FDE'),trackText);
        if(process.argv.includes('--expect-reused'))assert(trackText.includes('复用已有预测'),trackText);
      }else if(process.argv.includes('--warmup-no-prediction')){
        assert.equal(count,0);assert(trackText.includes('history warm-up'),trackText);
      }else{
        assert.equal(count,0);assert(trackText.includes('Legacy data has no explicit prediction coordinate contract'),trackText);
      }
      await evaluate(`document.querySelector('[aria-label="真实轨迹与预测对比"]').scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'prediction-overlay.png'),Buffer.from(shot.data,'base64'));
      await writeFile(join(output,'prediction-overlay.json'),JSON.stringify({count,trackText},null,2));
      interactions.push(count?'explicit_prediction_spatial_overlay_without_fake_timing':process.argv.includes('--warmup-no-prediction')?'warmup_does_not_fabricate_prediction':'legacy_prediction_not_silently_promoted');
    }
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
