// Read-only local HTML rendering QA; no application or simulator writes.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const profile=await mkdtemp(join(tmpdir(),'carla-report-qa-'));
const output=await mkdtemp(resolve('runs/validation/report-render-'));
const chrome=spawn('/usr/bin/google-chrome',['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
let socket;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try{
 let port;
 for(let i=0;i<100;i++){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{await delay(100)}}
 assert(port);
 const tab=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
 socket=new WebSocket(tab.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
 let next=0;const pending=new Map();
 socket.addEventListener('message',event=>{const value=JSON.parse(event.data),item=pending.get(value.id);if(item){pending.delete(value.id);clearTimeout(item.timer);value.error?item.reject(Error(value.error.message)):item.resolve(value.result)}});
 const cdp=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error(method+' timed out'))},60000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value};
 await cdp('Page.enable');await cdp('Runtime.enable');
 await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await cdp('Page.navigate',{url:pathToFileURL(resolve(process.argv[2])).href});
 for(let i=0;i<200;i++){if(await evaluate(`document.querySelector('footer')!==null`))break;await delay(100)}
 const result=await evaluate(`(async()=>{const images=[...document.images];for(const i of images)i.loading='eager';const decoded=await Promise.all(images.map(i=>i.decode().then(()=>true,()=>false)));return {images:images.length,decoded:decoded.filter(Boolean).length,cases:document.querySelectorAll('section[id^="case-"]').length,brokenAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(a.hash.slice(1))).length,overflow:document.documentElement.scrollWidth>innerWidth}})()`);
 assert.equal(result.images,146);assert.equal(result.decoded,result.images);assert.equal(result.cases,26);assert.equal(result.brokenAnchors,0);assert.equal(result.overflow,false);
 for(const [name,selector] of [['overview','h1'],['capabilities','main>section:nth-of-type(2)'],['last-check','#case-26']]){
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);await delay(150);
  const shot=await cdp('Page.captureScreenshot',{format:'png'});await writeFile(join(output,name+'.png'),Buffer.from(shot.data,'base64'));
 }
 await writeFile(join(output,'report.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({output,...result}));
}finally{socket?.close();chrome.kill('SIGTERM')}
