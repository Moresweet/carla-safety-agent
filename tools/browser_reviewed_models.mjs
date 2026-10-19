// Local isolated Chrome QA. Never launches a model. --stop-run explicitly stops
// one owned execution; --audit-dataset scans saved files without simulator RPC.
// --apply-pedestrian explicitly applies a texture to the supplied walker ID.
// --transform-draft explicitly moves the supplied fixture unless baseline-only.
// Handoff, bundle restore/registration, excerpt and recovery flags explicitly
// execute their named workflow; default mode only inspects UI/model selection.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {textureUploadFlipY} from './livery-designer/app/uvConvention.ts';

const profile=await mkdtemp(join(tmpdir(),'carla-browser-qa-'));
const output=resolve('runs/validation/browser-models-'+randomUUID());
await mkdir(output,{recursive:true});
const chrome=spawn('/usr/bin/google-chrome',['--headless=new','--disable-gpu','--no-first-run',
  '--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
let socket, diagnosticCDP;
const browserErrors=[];
const networkFailures=[];
const pendingRequests=new Map();
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
  await cdp('Network.enable');
  socket.addEventListener('message',event=>{const {method,params}=JSON.parse(event.data);
    if(method==='Network.requestWillBeSent')pendingRequests.set(params.requestId,{url:params.request.url,method:params.request.method,timestamp:params.timestamp});
    if(method==='Network.responseReceived'&&pendingRequests.has(params.requestId))Object.assign(pendingRequests.get(params.requestId),{status:params.response.status,protocol:params.response.protocol,timing:params.response.timing});
    if(method==='Network.dataReceived'&&pendingRequests.has(params.requestId)){const request=pendingRequests.get(params.requestId);request.receivedBytes=(request.receivedBytes??0)+params.dataLength;}
    if(method==='Network.loadingFailed')networkFailures.push({...params,request:pendingRequests.get(params.requestId)});
    if(method==='Network.loadingFailed'||method==='Network.loadingFinished')pendingRequests.delete(params.requestId);
  });
  await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  let imageFaultMode='transient';const imageFaultCounts=new Map();
  if(process.argv.includes('--replay-faults')){
    await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{
      const original=window.fetch;window.__readFaults={mode:'transient',counts:{}};
      window.fetch=async function(input,init){const url=new URL(typeof input==='string'?input:input.url,location.href),state=window.__readFaults;
        if(url.pathname==='/scene/state'&&state.sceneOffline)return Response.json({ok:false,error:'Injected old world rejection',retryable:true},{status:503});
        if(url.pathname==='/datasets/index'||url.pathname==='/datasets/frame'){
          const key=url.pathname;state.counts[key]=(state.counts[key]||0)+1;
          if(state.mode==='offline'||(state.mode==='transient'&&state.counts[key]<=2))throw new TypeError('Injected read-only connection failure');
        }
        return original.call(this,input,init);
      };
    })()`});
    socket.addEventListener('message',event=>{
      const message=JSON.parse(event.data);if(message.method!=='Fetch.requestPaused')return;
      const {requestId,request}=message.params,url=new URL(request.url);url.searchParams.delete('read_retry');url.searchParams.delete('read_reload');
      const count=(imageFaultCounts.get(url.href)||0)+1;imageFaultCounts.set(url.href,count);
      const fail=imageFaultMode==='offline'||(imageFaultMode==='transient'&&count<=2);
      void cdp(fail?'Fetch.failRequest':'Fetch.continueRequest',fail?{requestId,errorReason:'ConnectionFailed'}:{requestId}).catch(error=>browserErrors.push(String(error)));
    });
    await cdp('Fetch.enable',{patterns:[{urlPattern:'*://127.0.0.1:8765/datasets/file*',resourceType:'Image',requestStage:'Request'}]});
  }
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
    if(models.length===5||(process.argv.includes('--offline-replay')&&models.length>0))break;
    // Server-rendered navigation can precede React hydration. Re-selecting
    // this read-only tab is idempotent; never retry mutation buttons here.
    if(i%5===0)await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene')?.click()`);
    await delay(200);
  }
  if(!process.argv.includes('--offline-replay'))assert.deepEqual(models.map(m=>m.id).sort(),['admlp','tcp','uniad-base','uniad-tiny','vad']);
  else assert(process.argv.includes('--dataset'),'Offline replay requires an explicit saved dataset');
  const state=await evaluate(`(()=>{const section=document.querySelector('[aria-label="确认计划并选择模型"]');return {buttons:[...section.querySelectorAll('button')].map(b=>({text:b.textContent,disabled:b.disabled})),checkboxes:[...section.querySelectorAll('input')].map(b=>({checked:b.checked,disabled:b.disabled}))}})()`);
  assert(state.buttons[0].disabled,'Unreviewed plan must not start');
  const interactions=[];
  if(process.argv.includes('--offline-replay'))interactions.push('offline_replay_only_model_readiness_not_validated');
  if(process.argv.includes('--overview')){
    const pages=[];
    for(const [index,title] of buttons.entries()){
      await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent===${JSON.stringify(title)}).click()`);
      await delay(1800);
      await evaluate(`window.scrollTo(0,0)`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      const file=`overview-${String(index+1).padStart(2,'0')}.png`;
      await writeFile(join(output,file),Buffer.from(shot.data,'base64'));
      pages.push({title,file,text:await evaluate('document.body.innerText')});
    }
    await writeFile(join(output,'overview.json'),JSON.stringify(pages,null,2));
    interactions.push('navigation_screenshots_only_not_feature_acceptance');
  }
  if(process.argv.includes('--integration-status')){
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='End-to-End Test').click()`);
    let cards=[];
    for(let i=0;i<100;i++){cards=await evaluate(`[...document.querySelectorAll('.algorithm-card')].map(b=>({name:b.querySelector('strong').textContent,label:b.querySelector('span').textContent,disabled:b.disabled,title:b.title}))`);if(cards.length===7)break;await delay(200)}
    assert.equal(cards.length,7);
    for(const name of ['DriveAdapter','ThinkTwice']){const card=cards.find(c=>c.name===name);assert(card?.disabled);assert.equal(card.label,'NOT INTEGRATED');assert(card.title.includes('尚未接入'))}
    assert.equal(cards.filter(c=>c.label==='READY').length,5);
    await evaluate(`document.querySelector('.algorithm-card:last-child').scrollIntoView({block:'center'})`);
    const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'integration-status.png'),Buffer.from(shot.data,'base64'));
    await writeFile(join(output,'integration-status.json'),JSON.stringify(cards,null,2));
    interactions.push('five_existing_models_ready_two_external_models_not_integrated_not_unreleased');
  }
  if(process.argv.includes('--natural-asset')){
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Asset Workshop').click()`);
    let ready=false;
    for(let i=0;i<200;i++){ready=await evaluate(`!!document.querySelector('[aria-label="自然语言 Blender 计划"] button')&&!document.querySelector('[aria-label="自然语言 Blender 计划"] button').disabled`);if(ready)break;await delay(200)}assert(ready);
    await evaluate(`document.querySelector('[aria-label="自然语言 Blender 计划"] button').click()`);
    for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('[aria-label="自然语言 Blender 计划"] pre')`);if(ready)break;await delay(100)}assert(ready);
    assert(await evaluate(`[...document.querySelectorAll('[aria-label="自然语言 Blender 计划"] button')].find(b=>b.textContent==='按确认计划生成并导出').disabled`));
    const preview=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'natural-asset-preview.png'),Buffer.from(preview.data,'base64'));
    const before=(await(await fetch('http://127.0.0.1:8765/blender/generations')).json()).attempts;
    await evaluate(`document.querySelector('[aria-label="自然语言 Blender 计划"] input[type=checkbox]').click()`);
    await evaluate(`[...document.querySelectorAll('[aria-label="自然语言 Blender 计划"] button')].find(b=>b.textContent==='按确认计划生成并导出').click()`);
    for(let i=0;i<1000;i++){ready=await evaluate(`document.querySelector('[aria-label="自然语言 Blender 计划"] [role=status]').textContent.includes('已按归档计划导出')`);if(ready)break;await delay(200)}assert(ready);
    const attempts=(await(await fetch('http://127.0.0.1:8765/blender/generations')).json()).attempts.filter(r=>!before.some(b=>b.job_id===r.job_id));
    assert.equal(attempts.length,1);assert.equal(attempts[0].state,'exported');assert.match(attempts[0].plan_sha256,/^[a-f0-9]{64}$/);
    const request=JSON.parse(await readFile(join(attempts[0].destination,'request.json'),'utf8'));
    assert.deepEqual(request.dimensions,[2,.4,.8]);assert.equal(request.roughness,.6);
    await evaluate(`document.querySelector('.blender-result').scrollIntoView({block:'center'})`);
    const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'natural-asset-exported.png'),Buffer.from(shot.data,'base64'));
    await writeFile(join(output,'natural-asset.json'),JSON.stringify({attempt:attempts[0],request},null,2));
    interactions.push('natural_asset_explicit_plan_confirmation_real_blender_export_bound_to_sha');
  }
  if(process.argv.includes('--asset-search')){
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Create Objects').click()`);
    const settled=async()=>{let ready=false;for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('[aria-label="资产检索统计"]')&&!document.querySelector('[aria-label="资产检索统计"]').textContent.includes('检索中')`);if(ready)break;await delay(200)}assert(ready)};
    await delay(250);await settled();
    const first=await evaluate(`[...document.querySelectorAll('.asset-card b')].map(b=>b.textContent)`);
    assert.equal(first.length,48);
    await evaluate(`[...document.querySelectorAll('.asset-browser button')].find(b=>b.textContent==='下一页').click()`);await delay(250);await settled();
    const second=await evaluate(`[...document.querySelectorAll('.asset-card b')].map(b=>b.textContent)`);
    assert(second.length>0);assert(!second.some(id=>first.includes(id)));
    const setQuery=async text=>{await evaluate(`(()=>{const e=document.querySelector('[aria-label="检索资产"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(text)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`);await delay(250);await settled()};
    await setQuery('车辆 奥迪');
    const audi=await evaluate(`[...document.querySelectorAll('.asset-card b')].map(b=>b.textContent)`);
    assert(audi.length>0&&audi.every(id=>id.includes('audi')));
    await setQuery('');await evaluate(`[...document.querySelectorAll('.asset-tabs button')].find(b=>b.textContent==='Generated').click()`);await delay(250);await settled();
    const generated=await evaluate(`({count:document.querySelectorAll('.asset-card').length,images:document.querySelectorAll('.asset-card img').length,text:document.querySelector('[aria-label="资产检索统计"]').textContent})`);
    assert(generated.count>0);assert.equal(generated.images,0);
    const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'asset-search.png'),Buffer.from(shot.data,'base64'));
    await setQuery('definitely_missing_asset_7931');assert.equal(await evaluate(`document.querySelectorAll('.asset-card').length`),0);
    await writeFile(join(output,'asset-search.json'),JSON.stringify({first,second,audi,generated},null,2));
    interactions.push('full_catalog_pagination_chinese_name_aliases_generated_without_false_thumbnail_empty_results');
  }
  if(process.argv.includes('--blender-generation')){
    // Explicitly exports one primitive and attempts an invalid-source retexture;
    // never imports into Unreal or spawns into CARLA. Retain both job directories.
    const fixture=process.argv[process.argv.indexOf('--blender-generation')+1];
    assert(fixture?.startsWith('/'),'Supply an explicit invalid GLB fixture path');
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Asset Workshop').click()`);
    let ready=false;
    for(let i=0;i<200;i++){ready=await evaluate(`!!document.querySelector('.blender-form .primary')&&!document.querySelector('.blender-form .primary').disabled`);if(ready)break;await delay(200)}
    assert(ready,'Blender must become available');
    await evaluate(`(()=>{const e=document.querySelector('input[placeholder="/absolute/path/to/asset.fbx"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(fixture)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`);
    await delay(100);
    const before=(await(await fetch('http://127.0.0.1:8765/blender/generations')).json()).attempts;
    await evaluate(`(()=>{const b=document.querySelector('.blender-form .primary');b.click();b.click()})()`);
    for(let i=0;i<1000;i++){ready=await evaluate(`document.querySelector('.blender-status').textContent==='Asset exported successfully.'`);if(ready)break;await delay(200)}
    assert(ready,'Real Blender primitive export must succeed despite retexture source field');
    const exported=(await(await fetch('http://127.0.0.1:8765/blender/generations')).json()).attempts.filter(r=>!before.some(b=>b.job_id===r.job_id));
    assert.equal(exported.length,1,'Double click must launch only once');assert.equal(exported[0].state,'exported');
    const request=JSON.parse(await readFile(join(exported[0].destination,'request.json'),'utf8'));
    assert.equal(request.source_path,undefined);
    const success=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'blender-export.png'),Buffer.from(success.data,'base64'));
    await evaluate(`[...document.querySelectorAll('.blender-form button')].find(b=>b.textContent==='Replace texture & export').click()`);
    for(let i=0;i<1000;i++){ready=await evaluate(`document.querySelector('.blender-status').textContent.includes('Blender generation did not complete')`);if(ready)break;await delay(200)}
    assert(ready,'Malformed source must fail with a retained generation report');
    assert(await evaluate(`[...document.querySelectorAll('.pipeline-actions button')].every(b=>b.disabled)`),'Failed new job must not leave old import/spawn actions enabled');
    await delay(3300);
    const attempts=(await(await fetch('http://127.0.0.1:8765/blender/generations')).json()).attempts.filter(r=>!before.some(b=>b.job_id===r.job_id));
    assert.equal(attempts.length,2);assert(attempts.some(r=>r.state==='needs_attention'));
    await evaluate(`document.querySelector('.asset-import-history').scrollIntoView({block:'center'});document.querySelector('.asset-import-history details').open=true`);
    const failed=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'blender-generation-failure.png'),Buffer.from(failed.data,'base64'));
    await writeFile(join(output,'blender-generation.json'),JSON.stringify({attempts},null,2));
    interactions.push('real_blender_export_single_launch_create_ignores_retexture_source_failed_retexture_retained_no_stale_actions');
  }
  if(process.argv.includes('--plan-revision')){
    const initialSession=(await(await fetch('http://127.0.0.1:8765/session/status')).json()).session;
    await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Compile & preview').click()`);
    let ready=false;
    for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('[aria-label="自然语言局部修改计划"]')`);if(ready)break;await delay(200)}
    assert(ready);const parent=await evaluate(`JSON.parse(document.querySelector('.scenario-json pre').textContent)`);
    const parentBytes=await readFile(parent.scenario_path);
    for(let i=0;i<100;i++){ready=await evaluate(`!document.querySelectorAll('[aria-label="确认计划并选择模型"] input')[1].disabled`);if(ready)break;await delay(200)}
    assert(ready);await evaluate(`document.querySelectorAll('[aria-label="确认计划并选择模型"] input')[1].click()`);await delay(100);
    const enter=async value=>evaluate(`(()=>{const e=document.querySelector('[aria-label="计划局部修改指令"]');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`);
    await enter('雨量改为20；添加一辆飞车');await delay(100);
    await evaluate(`[...document.querySelectorAll('.plan-revision button')].find(b=>b.textContent==='预览局部修改').click()`);
    for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('.plan-revision [role=alert]')`);if(ready)break;await delay(100)}
    assert(ready);assert.equal(await evaluate(`JSON.parse(document.querySelector('.scenario-json pre').textContent).scenario_sha256`),parent.scenario_sha256);
    assert(await evaluate(`document.querySelector('[aria-label="确认计划并选择模型"] button').disabled`));
    await evaluate(`[...document.querySelectorAll('.plan-revision button')].find(b=>b.textContent==='取消修订，保留原计划').click()`);await delay(100);
    await enter('自车速度改为5 m/s；天气改为晴天；光照改为白天；运行时长改为1秒；其余保持不变');await delay(100);
    await evaluate(`[...document.querySelectorAll('.plan-revision button')].find(b=>b.textContent==='预览局部修改').click()`);
    for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('.plan-revision table')`);if(ready)break;await delay(100)}
    assert(ready);assert.equal(await evaluate(`JSON.parse(document.querySelector('.scenario-json pre').textContent).scenario_sha256`),parent.scenario_sha256,'Preview adopted itself');
    assert(await evaluate(`document.querySelector('[aria-label="确认计划并选择模型"] button').disabled`));
    await evaluate(`document.querySelector('.plan-revision').scrollIntoView({block:'center'})`);
    const preview=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'plan-revision-preview.png'),Buffer.from(preview.data,'base64'));
    await evaluate(`[...document.querySelectorAll('.plan-revision button')].find(b=>b.textContent==='采纳修订计划（不运行）').click()`);await delay(300);
    const child=await evaluate(`JSON.parse(document.querySelector('.scenario-json pre').textContent)`);
    assert.notEqual(child.scenario_sha256,parent.scenario_sha256);assert.equal(child.parent_sha256,parent.scenario_sha256);
    assert.equal(child.scenario.ego.speed_mps,5);assert.equal(child.scenario.environment.precipitation,0);assert.equal(child.scenario.oracle.max_duration_s,1);
    assert.deepEqual(child.scenario.adversaries,parent.scenario.adversaries);assert.deepEqual(await readFile(parent.scenario_path),parentBytes);
    assert(await evaluate(`!document.querySelectorAll('[aria-label="确认计划并选择模型"] input')[1].checked&&document.querySelector('[aria-label="确认计划并选择模型"] button').disabled`));
    assert.equal((await(await fetch('http://127.0.0.1:8765/session/status')).json()).session.run_id,initialSession.run_id,'Plan adoption launched an execution');
    await writeFile(join(output,'plan-revision-result.json'),JSON.stringify({parent,child},null,2));
    const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'plan-revision-adopted.png'),Buffer.from(shot.data,'base64'));
    interactions.push('unsupported_revision_rejected_cancel_preserves_parent_diff_adopt_requires_new_confirmation_no_execution');
  }
  const draftFlag=process.argv.indexOf('--transform-draft');
  const inspectHistoryFlag=process.argv.indexOf('--inspect-position-history');
  if(draftFlag>=0||inspectHistoryFlag>=0){
    const actor=Number(process.argv[(draftFlag>=0?draftFlag:inspectHistoryFlag)+1]);assert(Number.isSafeInteger(actor)&&actor>0);
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Edit World').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`!![...document.querySelectorAll('.catalog-groups button')].find(b=>b.querySelector('span')?.textContent==='spawned props')`);
      if(ready)break;await delay(200);
    }
    assert(ready);await evaluate(`[...document.querySelectorAll('.catalog-groups button')].find(b=>b.querySelector('span')?.textContent==='spawned props').click()`);
    for(let i=0;i<100;i++){
      ready=await evaluate(`[...document.querySelectorAll('.catalog-list select[size] option')].some(o=>o.value==='actor:${actor}')`);
      if(ready)break;await delay(200);
    }
    assert(ready);await evaluate(`(()=>{const s=document.querySelector('.catalog-list select[size]');s.value='actor:${actor}';s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    await delay(400);
    if(inspectHistoryFlag>=0){
      await evaluate(`document.querySelector('[aria-label="对象位置历史"]').open=true`);
      for(let i=0;i<100;i++){ready=await evaluate(`!!document.querySelector('[aria-label="对象位置历史"] input[type=checkbox]')`);if(ready)break;await delay(200)}
      assert(ready,'Pending history inspection not shown');
      assert(await evaluate(`[...document.querySelectorAll('[aria-label="对象位置历史"] button')].find(b=>b.textContent==='确认检查并开始空历史').disabled`));
      await evaluate(`document.querySelector('[aria-label="对象位置历史"] input[type=checkbox]').click()`);await delay(100);
      await evaluate(`[...document.querySelectorAll('[aria-label="对象位置历史"] button')].find(b=>b.textContent==='确认检查并开始空历史').click()`);
      for(let i=0;i<100;i++){const h=await(await fetch('http://127.0.0.1:8765/objects/transform-history?actor_id='+actor)).json();ready=h.eligible&&!h.pending&&h.undo_count===0&&h.redo_count===0;if(ready)break;await delay(200)}
      assert(ready,'Inspection did not archive the uncertain chain');
      await delay(1800);await evaluate(`document.querySelector('[aria-label="对象位置历史"]').scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,'position-history-inspected.png'),Buffer.from(shot.data,'base64'));
      interactions.push('explicit_position_history_inspection_archives_without_moving_actor');
    }else{
    const original=await evaluate(`Number(document.querySelector('.transform-grid input').value)`);
    const wanted=String(original+1.25);
    const enter=async value=>evaluate(`(()=>{const e=document.querySelector('.transform-grid input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`);
    await enter(wanted);await delay(100);
    assert.equal(await evaluate(`document.querySelector('.transform-grid input').value`),wanted,'Input was not entered');
    await delay(4600);
    const observed=await evaluate(`document.querySelector('.transform-grid input').value`);
    if(process.argv.includes('--expect-draft-reset'))assert.equal(Number(observed),original,'Expected baseline reset was not reproduced');
    else {
      assert.equal(observed,wanted,'Polling overwrote unsaved transform');
      await enter('');await delay(100);
      assert(await evaluate(`[...document.querySelectorAll('.object-inspector button')].find(b=>b.textContent==='Apply transform').disabled`),'Empty coordinate must not become zero');
      await enter(wanted);await delay(100);
      let updateRequests=0,injected=false;
      await cdp('Network.enable');
      socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.method==='Network.requestWillBeSent'&&value.params.request.method==='POST'&&value.params.request.url.endsWith('/objects/update-reviewed'))updateRequests++});
      await cdp('Fetch.enable',{patterns:[{urlPattern:'*://127.0.0.1:8765/objects/update-reviewed',requestStage:'Request'}]});
      const intercept=async event=>{const value=JSON.parse(event.data);if(value.method!=='Fetch.requestPaused')return;const p=value.params;
        if(p.request.method==='POST'&&!injected){injected=true;await cdp('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:400,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:'*'}],body:Buffer.from(JSON.stringify({error:'Injected transform rejection for draft regression'})).toString('base64')})}
        else await cdp('Fetch.continueRequest',{requestId:p.requestId});
      };
      socket.addEventListener('message',intercept);
      await evaluate(`[...document.querySelectorAll('.object-inspector button')].find(b=>b.textContent==='Apply transform').click()`);
      for(let i=0;i<100;i++){ready=await evaluate(`document.querySelector('.manager-head').textContent.includes('Injected transform rejection')`);if(ready)break;await delay(100)}
      assert(ready&&injected,'Injected rejection was not reported');
      await cdp('Fetch.disable');socket.removeEventListener('message',intercept);
      await delay(2500);
      assert.equal(await evaluate(`document.querySelector('.transform-grid input').value`),wanted,'Failure lost draft');
      assert(await evaluate(`document.querySelector('.manager-head').textContent.includes('Injected transform rejection')`),'Polling hid operation failure');
      assert.equal(updateRequests,1,'Failure retried without explicit action');
      await evaluate(`(()=>{const b=[...document.querySelectorAll('.object-inspector button')].find(b=>b.textContent==='Apply transform');b.click();b.click()})()`);
      for(let i=0;i<100;i++){
        const catalog=await(await fetch('http://127.0.0.1:8765/catalog/objects?category=spawned_props')).json();
        ready=Math.abs(catalog.objects.find(o=>o.id===actor)?.location.x-Number(wanted))<.01;
        if(ready)break;await delay(200);
      }
      assert(ready,'Explicit transform was not applied');await delay(2500);
      assert.equal(updateRequests,2,'Double click submitted more than one retry');
      await enter(String(original+2.5));await delay(100);
      await evaluate(`[...document.querySelectorAll('.object-inspector button')].find(b=>b.textContent==='放弃草稿，读取最新位置').click()`);
      await delay(100);assert.equal(Number(await evaluate(`document.querySelector('.transform-grid input').value`)),Number(wanted));
      if(process.argv.includes('--position-history')){
        const h=await(await fetch('http://127.0.0.1:8765/objects/transform-history?actor_id='+actor)).json();
        assert(h.eligible&&h.undo_count>0&&!h.pending);const before=h.entries.at(-1).before.location.x;
        await evaluate(`document.querySelector('[aria-label="对象位置历史"]').open=true`);
        for(const [label,x,count] of [['撤销上次位置修改',before,h.undo_count-1],['重做位置修改',Number(wanted),h.undo_count]]){
          for(let i=0;i<100;i++){ready=await evaluate(`![...document.querySelectorAll('[aria-label="对象位置历史"] button')].find(b=>b.textContent===${JSON.stringify(label)})?.disabled`);if(ready)break;await delay(200)}
          assert(ready);await evaluate(`[...document.querySelectorAll('[aria-label="对象位置历史"] button')].find(b=>b.textContent===${JSON.stringify(label)}).click()`);
          for(let i=0;i<100;i++){const current=await(await fetch('http://127.0.0.1:8765/objects/transform-history?actor_id='+actor)).json();ready=current.undo_count===count&&!current.pending&&Math.abs(current.observed.location.x-x)<.01;if(ready)break;await delay(200)}
          assert(ready,'Position history did not perform '+label);await delay(1800);
        }
        interactions.push('explicit_browser_position_undo_and_redo_verified');
      }
    }
    await evaluate(`document.querySelector('.object-inspector').scrollIntoView({block:'center'})`);
    const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'transform-draft.png'),Buffer.from(shot.data,'base64'));
    await writeFile(join(output,'transform-draft.json'),JSON.stringify({actor,original,wanted,observed,baseline:process.argv.includes('--expect-draft-reset')},null,2));
    interactions.push(process.argv.includes('--expect-draft-reset')?'baseline_polling_draft_loss_reproduced':'draft_survives_polling_empty_and_failed_apply_preserved_no_auto_retry_double_click_guard_and_discard_verified');
    }
  }
  const handoffFlag=process.argv.indexOf('--handoff-scene');
  if(handoffFlag>=0){
    const sceneId=process.argv[handoffFlag+1];assert(/^[a-f0-9]{32}$/.test(sceneId));
    await evaluate(`document.querySelector('.project-panel').open=true`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`[...document.querySelectorAll('.project-panel select option')].some(o=>o.value===${JSON.stringify(sceneId)})`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Handoff scene not listed');
    await evaluate(`(()=>{const s=document.querySelector('.project-panel select');s.value=${JSON.stringify(sceneId)};s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    for(let i=0;i<100;i++){
      ready=await evaluate(`!document.querySelector('[aria-label="跨地图场景恢复"] button').disabled`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Handoff preview unavailable');
    await evaluate(`document.querySelector('[aria-label="跨地图场景恢复"] button').click()`);
    for(let i=0;i<100;i++){
      ready=await evaluate(`!!document.querySelector('[aria-label="确认销毁当前世界并恢复目标地图"]')`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Destructive map review not shown');
    assert(await evaluate(`[...document.querySelectorAll('[aria-label="跨地图场景恢复"] button')].find(b=>b.textContent==='确认备份、换图并恢复').disabled`));
    await evaluate(`document.querySelector('[aria-label="跨地图场景恢复"]').scrollIntoView({block:'center'})`);
    const preview=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'map-handoff-review.png'),Buffer.from(preview.data,'base64'));
    await evaluate(`document.querySelector('[aria-label="确认销毁当前世界并恢复目标地图"]').click()`);
    await delay(150);const startedAt=Date.now()/1000;
    await evaluate(`[...document.querySelectorAll('[aria-label="跨地图场景恢复"] button')].find(b=>b.textContent==='确认备份、换图并恢复').click()`);
    let result;
    for(let i=0;i<360;i++){
      result=await (await fetch('http://127.0.0.1:8765/scenes/handoff')).json();
      if(result.selection?.scene_id===sceneId&&result.started_at>=startedAt){
        assert(!['needs_attention','failed_before_switch'].includes(result.state),JSON.stringify(result));
        if(result.state==='restored')break;
      }
      await delay(500);
    }
    assert.equal(result?.state,'restored');assert.equal(result.selection.scene_id,sceneId);assert(result.started_at>=startedAt);
    await writeFile(join(output,'map-handoff-result.json'),JSON.stringify(result,null,2));
    for(let i=0;i<100;i++){
      ready=await evaluate(`document.querySelector('[aria-label="跨地图场景恢复"]').textContent.includes(${JSON.stringify(result.request_id)})&&document.querySelector('[aria-label="跨地图场景恢复"]').textContent.includes('切图状态：restored')`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Completed handoff not shown');
    await evaluate(`document.querySelector('[aria-label="跨地图场景恢复"]').scrollIntoView({block:'center'})`);
    const completed=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'map-handoff-complete.png'),Buffer.from(completed.data,'base64'));
    interactions.push('explicit_browser_map_handoff_preview_confirmation_and_backup_visible');
  }
  const phaseFlag=process.argv.indexOf('--expect-execution-phase');
  if(phaseFlag>=0){
    const phase=process.argv[phaseFlag+1],execution=process.argv[phaseFlag+2];
    assert(/^[a-z_]+$/.test(phase)&&/^[a-f0-9]{32}$/.test(execution));
    if(process.argv.includes('--phase-end-to-end'))await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='End-to-End Test').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`(()=>{const e=document.querySelector('[aria-label="执行阶段"]');return e?.getAttribute('data-phase')===${JSON.stringify(phase)}&&e?.getAttribute('data-execution')===${JSON.stringify(execution)}})()`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Expected owned execution phase was not shown');
    const text=await evaluate(`document.querySelector('[aria-label="执行阶段"]').textContent`);
    if(phase==='preview')assert(text.includes('实景保留约剩')&&text.includes('仍占用仿真会话'),text);
    await evaluate(`document.querySelector('[aria-label="执行阶段"]').scrollIntoView({block:'center'})`);
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,'execution-phase.png'),Buffer.from(screenshot.data,'base64'));
    await writeFile(join(output,'execution-phase.json'),JSON.stringify({phase,execution,text},null,2));
    interactions.push(phase==='preview'?'owned_live_execution_phase_and_preview_countdown_visible':'owned_execution_last_phase_visible');
    if(process.argv.includes('--phase-end-to-end'))await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene').click()`);
  }
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
    const importHistory=`[...document.querySelectorAll('.asset-import-history')].find(section=>section.querySelector('h3')?.textContent==='持久化导入记录')`;
    let ready=false;
    for(let i=0;i<100;i++){ready=await evaluate(`${importHistory}?.textContent.includes(${JSON.stringify(job)})`);if(ready)break;await delay(200)}
    assert(ready,'Persisted import job not visible');
    const text=await evaluate(`${importHistory}.textContent`);
    assert(text.includes('已登记')&&text.includes('需要处理'),'Both success and rejected attempt should remain visible');
    const attempts=await evaluate(`[...${importHistory}.querySelectorAll('details')].filter(d=>d.textContent.includes(${JSON.stringify(job)})).map(d=>d.textContent)`);
    assert(attempts.some(text=>text.includes('已登记'))&&attempts.some(text=>text.includes('需要处理')),'Both states must belong to the selected import job');
    await evaluate(`(()=>{const section=${importHistory};for(const d of section.querySelectorAll('details'))if(d.textContent.includes(${JSON.stringify(job)}))d.open=true;section.scrollIntoView({block:'start'});})()`);
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
    if(process.argv.includes('--expect-batch-retry')){
      const rows=await evaluate(`[...document.querySelectorAll('.batch-panel tbody tr')].map(row=>({state:row.cells[2].textContent,attempts:row.cells[4].querySelector('[data-attempt-count]').textContent,retryDisabled:row.cells[5].querySelector('button').disabled}))`);
      assert.deepEqual(rows.map(row=>row.attempts),['2','1']);
      assert(rows.every(row=>row.state.startsWith('completed')&&row.retryDisabled));
      await evaluate(`document.querySelector('.attempt-history').open=true`);
      const history=await evaluate(`[...document.querySelector('.attempt-history').querySelectorAll('li')].map(item=>item.textContent)`);
      assert.equal(history.length,2);
      assert(history[0].includes('stopped')&&history[1].includes('completed'));
      assert(history.every(text=>text.includes('执行 ID：')&&!text.includes('尚未绑定')));
      await evaluate(`document.querySelector('.batch-panel table').scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,'batch-retry-rows.png'),Buffer.from(shot.data,'base64'));
      interactions.push('completed_batch_retry_counts_preserved_without_requeue');
    }
  }
  const datasetFlag=process.argv.indexOf('--dataset');
  if(datasetFlag>=0){
    let dataset=process.argv[datasetFlag+1];
    assert(/^(capture-[A-Za-z0-9-]+|(?:recovered|excerpt)-[a-f0-9]{32})$/.test(dataset),'Expected a capture dataset ID');
    await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Collect Data').click()`);
    let ready=false;
    for(let i=0;i<100;i++){
      ready=await evaluate(`[...document.querySelectorAll('select[aria-label="数据集"] option')].some(o=>o.value===${JSON.stringify(dataset)})`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Recorded dataset not listed');
    await evaluate(`(()=>{const s=document.querySelector('select[aria-label="数据集"]');s.value=${JSON.stringify(dataset)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    for(let i=0;i<100;i++){
      ready=await evaluate(`!!document.querySelector('[aria-label="回放索引质量"]')&&${process.argv.includes('--expect-empty-quota')?'true':"!!document.querySelector('.replay-controls a[download]')"}`);
      if(ready)break;await delay(200);
    }
    assert(ready,'Replay metadata did not load');
    if(process.argv.includes('--quality-read-fault')||process.argv.includes('--quality-read-timeout')||process.argv.includes('--quality-read-malformed')){
      const timeoutMode=process.argv.includes('--quality-read-timeout');
      const malformedMode=process.argv.includes('--quality-read-malformed');
      await evaluate(`(()=>{const original=window.fetch;window.__qualityReadCount=0;window.__qualityAbortCount=0;window.__restoreQualityRead=()=>{window.fetch=original};window.fetch=async function(input,init){const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.pathname==='/datasets/quality'&&(!init?.method||init.method==='GET')){window.__qualityReadCount++;if(${malformedMode})return Response.json({ok:true,run_id:${JSON.stringify(dataset)},state:'passed',detail:{invalid:'object'}});if(${timeoutMode})return new Promise((resolve,reject)=>{const abort=()=>{window.__qualityAbortCount++;reject(init.signal.reason)};if(init.signal.aborted)abort();else init.signal.addEventListener('abort',abort,{once:true})});throw new TypeError('Injected quality read failure')}return original.call(this,input,init)}})()`);
      const panel=`document.querySelector('[aria-label="原始数据质量检查"]')`;
      let failed=false;
      for(let i=0;i<180;i++){failed=await evaluate(`${panel}.textContent.includes('自动读取已停止')`);if(failed)break;await delay(100)}
      assert(failed,'Quality read failure must stop polling');
      await delay(2300);
      assert.equal(await evaluate('window.__qualityReadCount'),1,'Failed quality read must not retry automatically');
      if(timeoutMode)assert.equal(await evaluate('window.__qualityAbortCount'),1,'Timeout must abort the outstanding read');
      assert(await evaluate(`${panel}.querySelector('button').disabled`),'Unknown report must block new audit');
      if(malformedMode){
        const text=await evaluate(`${panel}.textContent`);
        assert(text.includes('校验日志格式异常')&&!text.includes('本次检查通过'),text);
      }
      await evaluate(`window.__restoreQualityRead();[...${panel}.querySelectorAll('button')].find(b=>b.textContent==='重新查询质量任务').click()`);
      let restored=false;
      for(let i=0;i<100;i++){restored=await evaluate(`!${panel}.textContent.includes('自动读取已停止')&&!${panel}.querySelector('button').disabled`);if(restored)break;await delay(100)}
      assert(restored,'Explicit read should restore current report');
      interactions.push(malformedMode?'quality_http200_malformed_report_rejected_no_retry_recovered':timeoutMode?'quality_read_timeout_aborted_single_request_explicit_recovery':'quality_read_failure_no_auto_retry_explicit_recovery');
    }
    if(process.argv.includes('--expect-empty-quota')){
      const state=await evaluate(`(()=>{const controls=document.querySelector('.replay-controls');return {text:controls.textContent,buttons:[...controls.querySelectorAll('button')].map(b=>({text:b.textContent,disabled:b.disabled})),download:!!controls.querySelector('a[download]'),notice:document.querySelector('[aria-label="录制完成状态提示"]')?.textContent}})()`);
      assert(state.text.includes('0 / 0 帧'),state.text);
      assert(state.buttons.every(button=>button.disabled),'Empty capture playback must be disabled');
      assert(!state.download,'No raw-frame download without samples');
      const quality=await evaluate(`document.querySelector('[aria-label="回放索引质量"]').textContent`);
      assert(quality.includes('没有可回放样本，无法验证时序')&&!quality.includes('严格递增'),quality);
      assert(state.notice?.includes('capture_quota')&&state.notice.includes('不代表预定采集全部完成'),state.notice);
      if(process.argv.includes('--expect-empty-quality-failed')){
        let explained=false;
        for(let i=0;i<100;i++){
          explained=await evaluate(`document.querySelector('[aria-label="原始数据质量检查"]')?.textContent.includes('没有已录制样本，无法验证原始数据质量')`);
          if(explained)break;await delay(100);
        }
        assert(explained,'Saved empty-sample quality failure must be explained');
      }
      interactions.push('empty_quota_recording_explained_playback_disabled_no_download');
    }
    const quotaFlag=process.argv.indexOf('--expect-quota-gib');
    if(quotaFlag>=0){
      const amount=process.argv[quotaFlag+1];assert(/^[1-9][0-9]*$/.test(amount));
      const text=await evaluate(`document.querySelector('[aria-label="录制配额策略"]')?.textContent`);
      assert(text?.includes(amount+' GiB')&&text.includes('不是文件系统硬配额'),text);
      await evaluate(`document.querySelector('[aria-label="录制配额策略"]').scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,'capture-quota-policy.png'),Buffer.from(shot.data,'base64'));
      interactions.push('recorded_quota_policy_visible_not_current_free_space');
    }
    if(process.argv.includes('--archive-capture')){
      // Explicit mutation: one real archive; hide its POST response only after
      // the server accepted it, then recover via the same persisted request ID.
      const panel=`document.querySelector('[aria-label="录制归档"]')`;
      const waitFor=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression))return;await delay(200)}throw Error('Archive UI condition timeout: '+expression)};
      await waitFor(`!!${panel}`);
      assert(await evaluate(`${panel}.querySelector('button').disabled`),'Archive must require confirmation');
      await evaluate(`(()=>{const original=window.fetch;window.__archivePosts=[];window.__restoreArchiveFetch=()=>{window.fetch=original};window.fetch=async function(input,init){
        const url=new URL(typeof input==='string'?input:input.url,location.href);
        if(url.pathname==='/datasets/archive'&&init?.method==='POST'){
          window.__archivePosts.push(JSON.parse(init.body));
          const response=await original.call(this,input,init);
          if(response.ok){await response.text();throw new TypeError('Injected accepted archive response loss')}
          return response;
        }
        return original.call(this,input,init);
      }})()`);
      await evaluate(`${panel}.querySelector('input[type="checkbox"]').click()`);
      await waitFor(`!${panel}.querySelector('button').disabled`);
      await evaluate(`(()=>{const button=${panel}.querySelector('button');button.click();button.click()})()`);
      await waitFor(`${panel}.textContent.includes('Injected accepted archive response loss')`);
      await delay(1600);
      const posts=await evaluate('window.__archivePosts');
      assert.equal(posts.length,1,'Double click or lost response must not duplicate submission');
      assert.equal(posts[0].run_id,dataset);
      assert(await evaluate(`${panel}.querySelector('button').disabled`),'Retry needs fresh confirmation');
      await evaluate(`${panel}.scrollIntoView({block:'center'})`);
      const lost=await cdp('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,'archive-response-lost.png'),Buffer.from(lost.data,'base64'));
      await evaluate(`window.__restoreArchiveFetch();[...${panel}.querySelectorAll('button')].find(b=>b.textContent==='查询原归档任务').click()`);
      await waitFor(`!!${panel}.querySelector('a[download]')`);
      const id=posts[0].request_id;
      const status=await (await fetch('http://127.0.0.1:8765/datasets/archive?request_id='+id)).json();
      assert.equal(status.state,'archived');assert.equal(status.source_removed,false);
      const repeat=await (await fetch('http://127.0.0.1:8765/datasets/archive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(posts[0])})).json();
      assert.deepEqual(repeat,status,'Same-ID submission must return the existing finished job');
      const href=await evaluate(`${panel}.querySelector('a[download]').href`);
      assert.equal(new URL(href).searchParams.get('request_id'),id);
      const response=await fetch(href);assert.equal(response.status,200);
      let bytes=0;const digest=createHash('sha256');
      for await(const chunk of response.body){bytes+=chunk.length;digest.update(chunk)}
      assert.equal(bytes,status.archive_bytes);assert.equal(digest.digest('hex'),status.archive_sha256);
      // Remount the data page: sessionStorage must recover the same job, not
      // create a second archive. No new POST is made by this navigation.
      await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Generate Scene').click()`);
      await waitFor(`!${panel}`);
      await evaluate(`[...document.querySelectorAll('nav button')].find(b=>b.textContent==='Collect Data').click()`);
      await waitFor(`[...document.querySelectorAll('select[aria-label="数据集"] option')].some(o=>o.value===${JSON.stringify(dataset)})`);
      await evaluate(`(()=>{const s=document.querySelector('select[aria-label="数据集"]');s.value=${JSON.stringify(dataset)};s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
      await waitFor(`!!${panel}?.querySelector('a[download]')`);
      assert.equal(await evaluate(`${panel}.querySelector('a[download]').href`),href);
      await evaluate(`${panel}.scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,'archive-completed.png'),Buffer.from(shot.data,'base64'));
      await writeFile(join(output,'archive-result.json'),JSON.stringify({passed:true,status,download_bytes:bytes,response_loss_recovered:true,remount_same_request:true,source_removed:false},null,2));
      interactions.push('real_archive_confirmation_response_loss_query_dedup_download_hash_remount_verified');
    }
    if(process.argv.includes('--storage-review')){
      await evaluate(`document.querySelector('[aria-label="录制空间盘点"] button').click()`);
      for(let i=0;i<200;i++){
        ready=await evaluate(`document.querySelectorAll('[aria-label="录制空间盘点"] tbody tr').length>0`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Storage review did not render');
      const storage=await evaluate(`(()=>{const panel=document.querySelector('[aria-label="录制空间盘点"]');return {text:panel.textContent,rows:[...panel.querySelectorAll('tbody tr')].map(row=>({id:row.cells[0].textContent,size:parseFloat(row.cells[1].textContent)})),overflow:panel.scrollWidth>panel.clientWidth+1}})()`);
      assert(storage.text.includes('未标记或未发现引用不代表可以删除'));
      assert(storage.text.includes('项目引用'),'Project reference counts missing');
      assert(storage.text.includes('已登记划分引用'),'Registered split counts missing');
      if(process.argv.includes('--expect-project-review-incomplete')){
        assert(storage.text.includes('扫描不完整，请勿据此清理'),storage.text);
        assert(storage.text.includes('Dependency manifest mismatch'),storage.text);
      }
      await writeFile(join(output,'storage-review.json'),JSON.stringify(storage,null,2));
      assert(storage.rows.length>0&&!storage.overflow,'Storage table overflows page');
      assert(storage.rows.every((row,i)=>!i||row.size<=storage.rows[i-1].size),'Storage not sorted descending');
      await evaluate(`document.querySelector('[aria-label="录制空间盘点"]').scrollIntoView({block:'start'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'storage-review.png'),Buffer.from(shot.data,'base64'));
      interactions.push('storage_review_manual_read_sorted_rows_without_deletion');
      if(process.argv.includes('--storage-filters')){
        const panel=`document.querySelector('[aria-label="录制空间盘点"]')`;
        const setSearch=async value=>{
          await evaluate(`(()=>{const input=${panel}.querySelector('[aria-label="空间盘点搜索"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event('input',{bubbles:true}))})()`);
          await delay(150);
        };
        await setSearch(dataset);
        assert.equal(await evaluate(`${panel}.querySelectorAll('tbody tr').length`),1);
        await evaluate(`${panel}.querySelector('tbody button').click()`);
        await delay(150);
        assert.equal(await evaluate(`document.querySelector('[aria-label="数据集"]').value`),dataset);
        await setSearch('no-recording-matches-this-filter');
        assert.equal(await evaluate(`${panel}.querySelectorAll('tbody tr').length`),0);
        await setSearch('');
        await evaluate(`${panel}.querySelector('input[type="checkbox"]').click()`);
        await delay(150);
        const kept=await evaluate(`[...${panel}.querySelectorAll('tbody tr')].map(row=>row.cells[3].textContent)`);
        assert(kept.length>0&&kept.every(text=>!text.includes('未显式保留')));
        await evaluate(`(()=>{const select=${panel}.querySelector('[aria-label="空间盘点状态"]');select.value='recording';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
        await delay(150);
        const combined=await evaluate(`[...${panel}.querySelectorAll('tbody tr')].map(row=>({status:row.cells[2].textContent,keep:row.cells[3].textContent}))`);
        assert(combined.every(row=>row.status==='recording'&&!row.keep.includes('未显式保留')));
        await evaluate(`(()=>{const select=${panel}.querySelector('[aria-label="空间盘点状态"]');select.value='saved';select.dispatchEvent(new Event('change',{bubbles:true}))})()`);
        await delay(150);
        const other=await evaluate(`[...${panel}.querySelectorAll('tbody button')].find(button=>button.textContent!==${JSON.stringify(dataset)})?.textContent`);
        assert(other,'Need a different saved protected recording for navigation');
        await evaluate(`[...${panel}.querySelectorAll('tbody button')].find(button=>button.textContent===${JSON.stringify(other)}).click()`);
        for(let i=0;i<100;i++){
          ready=await evaluate(`document.querySelector('[aria-label="数据集"]').value===${JSON.stringify(other)}&&document.querySelector('.replay-controls a[download]')?.href.includes(${JSON.stringify(other)})`);
          if(ready)break;await delay(100);
        }
        assert(ready,'Cross-recording selection did not load matching replay link');
        await evaluate(`${panel}.scrollIntoView({block:'start'})`);
        const filteredShot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        await writeFile(join(output,'storage-filters.png'),Buffer.from(filteredShot.data,'base64'));
        await evaluate(`${panel}.querySelector('input[type="checkbox"]').click()`);
        await evaluate(`(()=>{const select=${panel}.querySelector('[aria-label="空间盘点状态"]');select.value='';select.dispatchEvent(new Event('change',{bubbles:true}));const datasetSelect=document.querySelector('[aria-label="数据集"]');datasetSelect.value=${JSON.stringify(dataset)};datasetSelect.dispatchEvent(new Event('change',{bubbles:true}))})()`);
        await delay(150);
        assert.equal(await evaluate(`${panel}.querySelectorAll('tbody tr').length`),storage.rows.length);
        for(let i=0;i<100;i++){
          ready=await evaluate(`document.querySelector('.replay-controls a[download]')?.href.includes(${JSON.stringify(dataset)})`);
          if(ready)break;await delay(100);
        }
        assert(ready,'Original recording did not reload');
        interactions.push('storage_search_empty_result_kept_filter_and_selection_verified');
      }
      if(process.argv.includes('--storage-malformed')){
        await evaluate(`(()=>{const original=window.fetch;window.__storageRequests=0;window.__restoreStorageFetch=()=>{window.fetch=original};window.fetch=async function(input,init){const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.pathname==='/datasets/storage'){window.__storageRequests++;return new Response(JSON.stringify({ok:true,recordings:[null],free_bytes:0}),{status:200,headers:{'Content-Type':'application/json'}})}return original.call(this,input,init)};const button=document.querySelector('[aria-label="录制空间盘点"] button');button.click();button.click()})()`);
        for(let i=0;i<50;i++){
          ready=await evaluate(`document.querySelector('[aria-label="录制空间盘点"] [role="alert"]')?.textContent.includes('格式异常')`);
          if(ready)break;await delay(100);
        }
        assert(ready,'Malformed storage response did not show error');
        assert.equal(await evaluate(`document.querySelectorAll('[aria-label="录制空间盘点"] tbody tr').length`),0,'Stale storage rows retained');
        await delay(1200);
        assert.equal(await evaluate('window.__storageRequests'),1,'Unexpected double request or automatic retry');
        const faultShot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        await writeFile(join(output,'storage-malformed.png'),Buffer.from(faultShot.data,'base64'));
        await evaluate(`window.__restoreStorageFetch();document.querySelector('[aria-label="录制空间盘点"] button').click()`);
        for(let i=0;i<200;i++){
          ready=await evaluate(`document.querySelectorAll('[aria-label="录制空间盘点"] tbody tr').length>0`);
          if(ready)break;await delay(200);
        }
        assert(ready,'Manual storage refresh did not recover');
        interactions.push('malformed_storage_clears_stale_rows_no_retry_manual_recovery');
      }
    }
    if(process.argv.includes('--capture-error-notice')){
      assert(!process.argv.includes('--recover-capture'),'Simulated notice must not start real recovery');
      await evaluate(`(()=>{const original=window.fetch;window.__restoreCaptureNotice=()=>{window.fetch=original};window.__captureNoticePosts=0;window.fetch=async function(input,init){
        const url=new URL(typeof input==='string'?input:input.url,location.href);
        if(url.pathname==='/datasets/recovery'&&(init?.method??'GET')==='POST'){window.__captureNoticePosts++;throw Error('Test forbids recovery writes')}
        const response=await original.call(this,input,init);
        if(url.pathname!=='/datasets')return response;
        const doc=await response.clone().json();doc.datasets=doc.datasets.map(d=>d.run_id===${JSON.stringify(dataset)}?{...d,status:'saved_capture_error',error:'模拟磁盘写入失败',stop_reason:'capture_io_error'}:d);
        return new Response(JSON.stringify(doc),{status:response.status,headers:{'Content-Type':'application/json'}});
      };[...document.querySelectorAll('button')].find(b=>b.textContent==='刷新清单').click()})()`);
      for(let i=0;i<50;i++){
        ready=await evaluate(`document.querySelector('[aria-label="录制完成状态提示"]')?.textContent.includes('模拟磁盘写入失败')`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Capture error notice absent');
      assert(await evaluate(`document.querySelector('[aria-label="录制完成状态提示"]').textContent.includes('不是完整成功数据')`));
      assert(await evaluate(`document.querySelector('[aria-label="恢复中断录制"] button').disabled`));
      assert.equal(await evaluate('window.__captureNoticePosts'),0);
      await evaluate(`document.querySelector('[aria-label="录制完成状态提示"]').scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'capture-error-notice.png'),Buffer.from(shot.data,'base64'));
      await evaluate('window.__restoreCaptureNotice()');
      interactions.push('simulated_capture_error_notice_and_unconfirmed_recovery_gate_no_writes');
    }
    if(process.argv.includes('--retention-faults')){
      assert(!process.argv.includes('--retention-toggle'),'Do not combine retention write and fault tests');
      const before=await (await fetch('http://127.0.0.1:8765/datasets/retention')).json();
      const panel=`document.querySelector('[aria-label="录制保留设置"]')`;
      const waitFor=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression))return;await delay(100)}throw Error('Retention fault condition timeout: '+expression)};
      await waitFor(`${panel}&&!${panel}.textContent.includes('保留状态未确认')`);
      await evaluate(`(()=>{const original=window.fetch;window.__retentionFault={posts:0,reads:0,offline:false};window.__restoreRetentionFetch=()=>{window.fetch=original};window.fetch=async function(input,init){
        const url=new URL(typeof input==='string'?input:input.url,location.href),state=window.__retentionFault;
        if(url.pathname==='/datasets/retention'){
          if((init?.method??'GET')==='POST'){state.posts++;return Response.json({ok:false,error:'Retention revision changed; refresh before editing'},{status:400})}
          state.reads++;if(state.offline)throw new TypeError('Injected retention network failure');
        }
        return original.call(this,input,init);
      }})()`);
      await evaluate(`(()=>{const i=document.querySelector('[aria-label="录制保留原因"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,'故障回归原因保留');i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
      await waitFor(`!${panel}.querySelector('button').disabled`);
      await evaluate(`(()=>{const b=${panel}.querySelector('button');b.click();b.click()})()`);
      await waitFor(`${panel}.textContent.includes('revision changed')&&${panel}.querySelector('button').disabled`);
      assert.equal(await evaluate(`document.querySelector('[aria-label="录制保留原因"]').value`),'故障回归原因保留');
      await delay(1200);
      assert.equal(await evaluate('window.__retentionFault.posts'),1,'Failed writes must not retry');
      if(process.argv.includes('--storage-review')){
        assert.equal(await evaluate(`document.querySelectorAll('[aria-label="录制空间盘点"] tbody tr').length`),0);
        assert(await evaluate(`document.querySelector('[aria-label="录制空间盘点"]').textContent.includes('旧盘点已清除')`));
        interactions.push('retention_write_attempt_invalidates_storage_even_on_conflict');
      }
      await evaluate(`${panel}.scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,'retention-conflict.png'),Buffer.from(shot.data,'base64'));
      await evaluate(`window.__retentionFault.offline=true;${panel}.querySelectorAll('button')[1].click()`);
      await waitFor(`${panel}.textContent.includes('Injected retention network failure')&&!${panel}.querySelectorAll('button')[1].disabled`);
      assert(await evaluate(`${panel}.querySelector('button').disabled`));
      await delay(1200);
      assert.equal(await evaluate('window.__retentionFault.reads'),1,'Failed reads require explicit refresh');
      await evaluate(`window.__retentionFault.offline=false;${panel}.querySelectorAll('button')[1].click()`);
      await waitFor(`!${panel}.textContent.includes('保留状态未确认')&&!${panel}.querySelector('button').disabled`);
      assert.equal(await evaluate(`document.querySelector('[aria-label="录制保留原因"]').value`),'故障回归原因保留');
      assert.deepEqual(await (await fetch('http://127.0.0.1:8765/datasets/retention')).json(),before,'Fault tests must not mutate real state');
      await evaluate('window.__restoreRetentionFetch()');
      interactions.push('retention_conflict_offline_no_retry_reason_preserved_explicit_refresh_verified');
    }
    if(process.argv.includes('--retention-toggle')){
      const waitFor=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(100)}throw Error('Retention condition timeout')};
      const before=await (await fetch('http://127.0.0.1:8765/datasets/retention')).json();
      assert(!Object.hasOwn(before.records,dataset),'Retention fixture must initially be unmarked');
      const panel=`document.querySelector('[aria-label="录制保留设置"]')`;
      await waitFor(`${panel}?.textContent.includes('未设置显式保留')`);
      assert(await evaluate(`${panel}.querySelector('button').disabled`),'Empty reason must not submit');
      for(const keep of [true,false]){
        await evaluate(`(()=>{const input=document.querySelector('[aria-label="录制保留原因"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'浏览器保留标记回归');input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
        await waitFor(`!${panel}.querySelector('button').disabled`);
        await evaluate(`(()=>{const button=${panel}.querySelector('button');button.click();button.click()})()`);
        await waitFor(`${panel}.textContent.includes(${JSON.stringify(keep?'已标记保留：':'未设置显式保留')})&&!${panel}.querySelectorAll('button')[1].disabled`);
        const state=await (await fetch('http://127.0.0.1:8765/datasets/retention')).json();
        assert.equal(Object.hasOwn(state.records,dataset),keep);
        assert.equal(state.revision,before.revision+(keep?1:2),'Duplicate click must not issue another mutation');
        await evaluate(`${panel}.scrollIntoView({block:'center'})`);
        const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        await writeFile(join(output,keep?'retention-kept.png':'retention-released.png'),Buffer.from(shot.data,'base64'));
      }
      interactions.push('retention_reason_required_keep_unkeep_double_click_and_revision_verified');
    }
    if(process.argv.includes('--replay-faults')){
      const waitFor=async(expression)=>{for(let i=0;i<150;i++){if(await evaluate(expression))return;await delay(100)}throw Error('Fault condition timeout: '+expression)};
      const loaded=`[...document.querySelectorAll('.sensor-workbench .sensor-image img')].length===8&&[...document.querySelectorAll('.sensor-workbench .sensor-image img')].every(i=>i.complete&&i.naturalWidth>0&&i.style.visibility==='visible')`;
      await waitFor(loaded);
      assert.deepEqual(await evaluate('window.__readFaults.counts'),{'/datasets/index':3,'/datasets/frame':3});
      assert.equal(imageFaultCounts.size,8);assert([...imageFaultCounts.values()].every(n=>n===3));
      const shot=async name=>{const selector=name.startsWith('images-')?'.sensor-workbench':'.collection-selection';await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);const value=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(output,name+'.png'),Buffer.from(value.data,'base64'))};
      await shot('replay-transient-recovered');
      await evaluate(`window.__readFaults={mode:'offline',counts:{}}`);
      await evaluate(`(()=>{const s=document.querySelector('select[aria-label="数据集"]');s.value='';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);await delay(100);
      await evaluate(`(()=>{const s=document.querySelector('select[aria-label="数据集"]');s.value=${JSON.stringify(dataset)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
      await waitFor(`document.querySelector('[aria-label="回放连接状态"]')?.textContent.includes('已停止自动重试')`);
      await delay(1500);assert.deepEqual(await evaluate('window.__readFaults.counts'),{'/datasets/index':3});
      assert.equal(await evaluate(`document.querySelectorAll('.sensor-workbench .sensor-image img').length`),0,'Failed index must not reveal old images');
      await shot('replay-retry-exhausted');
      imageFaultMode='normal';
      await evaluate(`window.__readFaults.mode='normal';[...document.querySelectorAll('button')].find(b=>b.textContent==='重新读取回放').click()`);
      await waitFor(loaded);await shot('replay-manual-recovered');
      imageFaultMode='offline';imageFaultCounts.clear();
      await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='重新加载图像').click()`);
      await waitFor(`document.querySelectorAll('.sensor-workbench .recoverable-image [role=alert]').length===8`);
      await delay(1500);assert.equal(imageFaultCounts.size,8);assert([...imageFaultCounts.values()].every(n=>n===3));
      await shot('images-retry-exhausted');
      imageFaultMode='normal';
      await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='重新加载图像').click()`);
      await waitFor(loaded);await shot('images-manual-recovered');
      await evaluate('window.__readFaults.sceneOffline=true');
      await waitFor(`document.querySelector('[aria-label="场景连接状态"]')?.textContent.includes('HTTP 503')`);
      assert.equal(await evaluate(`document.querySelectorAll('nav button').length`),6,'Scene errors must not crash the page');
      await evaluate('window.scrollTo(0,0)');
      const sceneShot=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(output,'scene-read-unavailable.png'),Buffer.from(sceneShot.data,'base64'));
      await evaluate('window.__readFaults.sceneOffline=false');
      await waitFor(`!document.querySelector('[aria-label="场景连接状态"]')`);
      interactions.push('bounded_transient_GET_and_image_recovery','persistent_read_and_image_failure_stops_after_three_attempts','explicit_retry_recovers_without_old_frame_or_model_start');
      interactions.push('scene_503_does_not_replace_valid_world_or_crash_ui_and_poll_recovers');
      await writeFile(join(output,'fault-checks.json'),JSON.stringify({imageCounts:[...imageFaultCounts],reads:await evaluate('window.__readFaults.counts'),scope:'Injected read-only browser network faults against saved data; simulator not restarted'},null,2));
    }
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
    if(process.argv.includes('--export-window')){
      assert(await evaluate(`document.querySelector('[aria-label="诊断片段归档"] button').disabled`));
      await evaluate(`(()=>{for(const label of ['片段向前秒数','片段向后秒数']){const e=document.querySelector('input[aria-label="'+label+'"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,.1);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}})()`);
      await delay(300);
      await evaluate(`document.querySelector('[aria-label="确认保存诊断片段"]').click()`);
      await delay(100);
      await evaluate(`document.querySelector('[aria-label="诊断片段归档"] button').click()`);
      let result,requestId;
      for(let i=0;i<620;i++){
        requestId=await evaluate(`sessionStorage.getItem('capture-excerpt:'+${JSON.stringify(dataset)})`);
        if(requestId){
          result=await (await fetch('http://127.0.0.1:8765/datasets/excerpt?request_id='+requestId)).json();
          assert(!['failed','needs_attention'].includes(result.state),JSON.stringify(result));
          if(result.state==='ready')break;
        }
        await delay(500);
      }
      assert.equal(result?.state,'ready',JSON.stringify(result));
      assert.equal(result.selection.before_s,.1);assert.equal(result.selection.after_s,.1);
      await writeFile(join(output,'excerpt-report.json'),JSON.stringify(result,null,2));
      for(let i=0;i<30;i++){
        ready=await evaluate(`!!document.querySelector('[aria-label="诊断片段归档"] a[download]')`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Excerpt download not displayed');
      const url=await evaluate(`document.querySelector('[aria-label="诊断片段归档"] a[download]').href`);
      const response=await fetch(url);assert(response.ok);
      const digest=createHash('sha256');let bytes=0;
      for await(const chunk of response.body){digest.update(chunk);bytes+=chunk.length}
      assert.equal(bytes,result.archive.bytes);assert.equal(digest.digest('hex'),result.archive.sha256);
      await evaluate(`document.querySelector('[aria-label="诊断片段归档"]').scrollIntoView({block:'center'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'excerpt-complete.png'),Buffer.from(shot.data,'base64'));
      await evaluate(`[...document.querySelectorAll('[aria-label="诊断片段归档"] button')].find(b=>b.textContent==='打开诊断片段回放').click()`);
      dataset=result.excerpt_run_id;
      for(let i=0;i<100;i++){
        ready=await evaluate(`document.querySelector('select[aria-label="数据集"]').value===${JSON.stringify(dataset)}&&!!document.querySelector('[aria-label="诊断片段提示"]')&&!!document.querySelector('.replay-controls a[download]')`);
        if(ready)break;await delay(200);
      }
      assert(ready,'Excerpt playback unavailable');
      assert.equal(await evaluate(`document.querySelectorAll('[aria-label="诊断片段归档"]').length`),0,'Recursive excerpt is not supported');
      interactions.push('explicit_window_export_download_hash_and_subset_playback_verified');
    }
    const quality=await evaluate(`document.querySelector('[aria-label="回放索引质量"]').textContent`);
    assert(quality.includes(process.argv.includes('--expect-empty-quota')?'没有可回放样本':'严格递增')&&quality.includes('不等于传感器丢帧数量'));
    const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
    await writeFile(join(output,'replay-quality.png'),Buffer.from(screenshot.data,'base64'));
    interactions.push('recorded_dataset_quality_visible');
    if(process.argv.includes('--expect-interrupted-warning')){
      const notice=await evaluate(`document.querySelector('[aria-label="录制完成状态提示"]')?.textContent`);
      assert(notice?.includes('recording 标记不能证明任务仍在运行'),String(notice));
      await evaluate(`document.querySelector('[aria-label="录制完成状态提示"]').scrollIntoView({block:'center'})`);
      const warningShot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'capture-outcome-warning.png'),Buffer.from(warningShot.data,'base64'));
      interactions.push('interrupted_recording_warning_visible_without_recovery_write');
    }
    if(process.argv.includes('--model-four-views')){
      let loaded=false;
      for(let i=0;i<100;i++){
        loaded=await evaluate(`(()=>{const images=[...document.querySelectorAll('[aria-label="模型原始四视角"] img')];return images.length===4&&images.every(image=>image.complete&&image.naturalWidth>0)})()`);
        if(loaded)break;
        await delay(200);
      }
      assert(loaded,'Original four-view model images did not load');
      await evaluate(`document.querySelector('[aria-label="模型原始四视角"]').scrollIntoView({block:'start'})`);
      const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'model-four-views.png'),Buffer.from(shot.data,'base64'));
      await evaluate(`document.querySelector('[aria-label="模型原始四视角"] button').click()`);
      let enlarged=false;
      for(let i=0;i<100;i++){
        enlarged=await evaluate(`(()=>{const image=document.querySelector('[aria-label="传感器大图"] img');return !!image&&image.alt==='rgb_front'&&image.complete&&image.naturalWidth===1600})()`);
        if(enlarged)break;await delay(200);
      }
      assert(enlarged,'Original front image did not enlarge at recorded resolution');
      const enlargedShot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(output,'model-front-enlarged.png'),Buffer.from(enlargedShot.data,'base64'));
      await evaluate(`document.querySelector('[aria-label="传感器大图"] button').click()`);
      interactions.push('four_original_model_images_loaded_separately_from_auxiliary_views');
    }
    const sampleFlag=process.argv.indexOf('--sample-index');
    if(sampleFlag>=0){
      const sample=Number(process.argv[sampleFlag+1]);assert(Number.isSafeInteger(sample)&&sample>=0);
      const index=await (await fetch('http://127.0.0.1:8765/datasets/index?run_id='+encodeURIComponent(dataset))).json();
      assert(sample<index.frames.length,'Requested sample outside recorded index');
      const expectedFrame=index.frames[sample].frame;
      await evaluate(`(()=>{const slider=document.querySelector('input[aria-label="回放时间轴"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(slider,${sample});slider.dispatchEvent(new Event('input',{bubbles:true}));slider.dispatchEvent(new Event('change',{bubbles:true}))})()`);
      let selected=false;
      for(let i=0;i<100;i++){
        selected=await evaluate(`(()=>{const a=document.querySelector('.replay-controls a[download]');return !!a&&new URL(a.href).searchParams.get('frame')===${JSON.stringify(String(expectedFrame))}})()`);
        if(selected)break;await delay(200);
      }
      assert(selected,'Requested sample did not finish loading');
      interactions.push('explicit_recorded_sample_selected_'+sample);
    }
    if(process.argv.includes('--prediction-overlay')||process.argv.includes('--legacy-prediction-no-overlay')||process.argv.includes('--warmup-no-prediction')){
      let trackText;
      for(let i=0;i<100;i++){
        trackText=await evaluate(`document.querySelector('[aria-label="真实轨迹与预测对比"]')?.textContent`);
        if(trackText&&(process.argv.includes('--prediction-overlay')?trackText.includes('绿色点线'):trackText.includes('不叠加模型预测')))break;
        await delay(200);
      }
      assert(trackText,'Trajectory comparison unavailable');
      const count=await evaluate(`document.querySelectorAll('[aria-label="真实轨迹与预测对比"] circle[fill="#5de2bc"]').length`);
      if(process.argv.includes('--prediction-overlay')){
        assert(count>0&&trackText.includes('不计算 ADE/FDE'),trackText);
        if(process.argv.includes('--expect-map-projection')){
          assert.equal(count,4);
          assert(trackText.includes('已使用录制归档地图逐点转换预测轨迹'),trackText);
          assert(trackText.includes('投影后导航原点与真值相差'),trackText);
          assert(!trackText.includes('当前绿线仅为原有规则参照'),trackText);
          assert(!trackText.includes('原版导航坐标与真值坐标的数值差'),trackText);
        }
        if(process.argv.includes('--expect-missing-navigation')){
          assert(trackText.includes('DriveAdapter 使用运动补偿和平滑后的 GPS'),trackText);
          assert(trackText.includes('没有有效的导航位姿观测'),trackText);
          assert(trackText.includes('不按零偏差处理'),trackText);
        }
        if(process.argv.includes('--expect-navigation-diagnostic')){
          assert(trackText.includes('预测生成时原版导航坐标与真值坐标的数值差'),trackText);
          assert(trackText.includes('不能将此数值差解释为实际定位误差或预测轨迹误差'),trackText);
          assert(!trackText.includes('没有有效的导航位姿观测'),trackText);
        }
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
      if(process.argv.includes('--trajectory-backpressure')){
        await evaluate(`(()=>{const original=window.fetch;window.__trajectoryProbe={mode:'hold',calls:0};window.fetch=async function(input,init){const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.pathname==='/datasets/trajectory'){const probe=window.__trajectoryProbe;probe.calls++;if(probe.mode==='hold'){probe.mode='held';await new Promise(resolve=>{probe.release=resolve})}else if(probe.mode==='fail'){probe.mode='failed';throw new TypeError('Injected trajectory read failure')}}return original.call(this,input,init)}})()`);
        await evaluate(`[...document.querySelectorAll('.replay-controls button')].find(b=>b.textContent==='播放').click()`);
        for(let i=0;i<100;i++){if(await evaluate(`window.__trajectoryProbe.mode==='held'`))break;await delay(100)}
        assert(await evaluate(`window.__trajectoryProbe.mode==='held'`),'Next trajectory was not requested');
        const held=await evaluate(`document.querySelector('[aria-label="回放时间轴"]').value`);
        await delay(1200);
        assert.equal(await evaluate(`document.querySelector('[aria-label="回放时间轴"]').value`),held,'Playback skipped unread trajectory');
        await evaluate(`window.__trajectoryProbe.mode='fail';window.__trajectoryProbe.release()`);
        for(let i=0;i<100;i++){if(await evaluate(`window.__trajectoryProbe.mode==='failed'&&!![...document.querySelectorAll('.replay-controls button')].find(b=>b.textContent==='播放')`))break;await delay(100)}
        assert(await evaluate(`window.__trajectoryProbe.mode==='failed'&&!![...document.querySelectorAll('.replay-controls button')].find(b=>b.textContent==='播放')`),'Trajectory failure did not pause');
        const stopped=await evaluate(`document.querySelector('[aria-label="回放时间轴"]').value`);
        await delay(500);
        assert.equal(await evaluate(`document.querySelector('[aria-label="回放时间轴"]').value`),stopped);
        await evaluate(`document.querySelector('[aria-label="真实轨迹与预测对比"]').scrollIntoView({block:'center'})`);
        const failedShot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        await writeFile(join(output,'trajectory-read-paused.png'),Buffer.from(failedShot.data,'base64'));
        // The injected failure is one-shot; subsequent requests use real data.
        await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='重试轨迹读取').click()`);
        let recovered=false;
        for(let i=0;i<100;i++){
          recovered=await evaluate(`!!document.querySelector('[aria-label="归档地图投影"]')&&!document.querySelector('[aria-label="真实轨迹与预测对比"] [role="alert"]')`);
          if(recovered)break;await delay(100);
        }
        assert(recovered,'Explicit trajectory retry did not recover real map projection');
        assert.equal(await evaluate(`document.querySelector('[aria-label="回放时间轴"]').value`),stopped,'Retry must not resume playback implicitly');
        await evaluate(`[...document.querySelectorAll('.replay-controls button')].find(b=>b.textContent==='播放').click()`);
        for(let i=0;i<100;i++){if(await evaluate(`Number(document.querySelector('[aria-label="回放时间轴"]').value)>${Number(stopped)}`))break;await delay(100)}
        assert(await evaluate(`Number(document.querySelector('[aria-label="回放时间轴"]').value)>${Number(stopped)}`),'Playback did not resume after explicit retry');
        await evaluate(`[...document.querySelectorAll('.replay-controls button')].find(b=>b.textContent==='暂停').click()`);
        await writeFile(join(output,'trajectory-backpressure.json'),JSON.stringify({held,stopped,heldMilliseconds:1200,readFailurePaused:true},null,2));
        interactions.push('trajectory_delay_blocks_progress_and_read_failure_pauses');
        interactions.push('explicit_trajectory_retry_recovers_then_manual_play_resumes');
      }
    }
    if(process.argv.includes('--six-views')){
      for(const mode of ['RGB','深度']){
        await evaluate(`[...document.querySelectorAll('.sensor-toolbar button')].find(b=>b.textContent===${JSON.stringify(mode==='RGB'?'六视角 RGB':'六视角深度')}).click()`);
        let loaded=false;
        for(let i=0;i<100;i++){
          loaded=await evaluate(`(()=>{const images=[...document.querySelectorAll('.surround-grid .sensor-tile img')].filter(i=>!i.closest('[aria-label="模型原始四视角"]'));return images.length===6&&images.every(i=>i.complete&&i.naturalWidth>0&&i.naturalHeight>0)})()`);
          if(loaded)break;await delay(200);
        }
        assert(loaded,'Six saved '+mode+' views must load');
        await evaluate(`[...document.querySelectorAll('.surround-grid .sensor-tile')].find(i=>!i.closest('[aria-label="模型原始四视角"]')).parentElement.scrollIntoView({block:'start'})`);
        const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
        await writeFile(join(output,mode==='RGB'?'six-rgb.png':'six-depth.png'),Buffer.from(shot.data,'base64'));
      }
      interactions.push('six_rgb_and_six_depth_images_loaded_and_visually_captured');
      await evaluate(`[...document.querySelectorAll('.sensor-toolbar button')].find(b=>b.textContent==='六视角 RGB').click()`);
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
  await writeFile(join(output,'failure.json'),JSON.stringify({error:String(error),browserErrors,networkFailures,pendingRequests:[...pendingRequests.values()]},null,2));
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
