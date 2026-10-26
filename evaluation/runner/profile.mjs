// Read-only Node/V8 diagnostics for an owned Gateway in the private namespace.
import fs from 'node:fs';
import readline from 'node:readline';
import {createHash} from 'node:crypto';
const targets=await (await fetch('http://127.0.0.1:9229/json/list')).json();
if(!targets.length)throw new Error('No owned inspector target');
const socket=new WebSocket(targets[0].webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let next=1;const pending=new Map();
socket.addEventListener('message',event=>{const data=JSON.parse(String(event.data));const waiter=pending.get(data.id);if(waiter){pending.delete(data.id);data.error?waiter.reject(new Error(JSON.stringify(data.error))):waiter.resolve(data.result);}});
function rpc(method,params={}){return new Promise((resolve,reject)=>{const id=next++;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});}
const modules=new Map();
function frame(node){
 const f=node.callFrame;let region=null,sha256=null;
 if(f.url.startsWith('file:///runtime/node_modules/openclaw/dist/')){
  let item=modules.get(f.url);
  if(!item){const bytes=fs.readFileSync(new URL(f.url));item={lines:bytes.toString().split('\n'),sha256:createHash('sha256').update(bytes).digest('hex')};modules.set(f.url,item);}
  sha256=item.sha256;
  for(let i=Math.min(f.lineNumber,item.lines.length-1);i>=0;i--){const match=item.lines[i].match(/^\/\/#region\s+(.+)$/);if(match){region=match[1];break;}}
 }
 return {function:f.functionName||'(anonymous)',url:f.url,line:f.lineNumber+1,column:f.columnNumber+1,source_region:region,module_sha256:sha256};
}
function summarize(profile){
 const byId=new Map(profile.nodes.map(n=>[n.id,n]));const parents=new Map();for(const n of profile.nodes)for(const child of n.children||[])parents.set(child,n.id);
 const counts=new Map();for(const id of profile.samples||[])counts.set(id,(counts.get(id)||0)+1);
 const ranked=[...counts].sort((a,b)=>b[1]-a[1]).slice(0,12);
 const stacks=ranked.map(([id,count])=>{const frames=[];let current=id;for(let i=0;i<5&&byId.has(current);i++){frames.push(frame(byId.get(current)));current=parents.get(current);}return {samples:count,frames};});
 return {kind:'main-thread-v8-sampling',sample_count:profile.samples?.length||0,duration_us:profile.endTime-profile.startTime,
  top_leaf_frames:ranked.map(([id,count])=>({samples:count,...frame(byId.get(id))})),top_stacks:stacks,
  profile_sha256:createHash('sha256').update(JSON.stringify(profile)).digest('hex'),raw_profile_retained:false,
  limitation:'Instrumented main-thread sample counts, not per-function billed CPU or an uninstrumented performance baseline. Source regions come from published bundle markers, not exact source-map line translation.'};
}
console.log(JSON.stringify({ready:true}));
for await(const line of readline.createInterface({input:process.stdin})){
 try{
  const command=JSON.parse(line);
  if(command.method==='start'){await rpc('Profiler.enable');await rpc('Profiler.setSamplingInterval',{interval:1000});await rpc('Profiler.start');console.log(JSON.stringify({ok:true}));}
  else if(command.method==='stop'){const {profile}=await rpc('Profiler.stop');console.log(JSON.stringify(summarize(profile)));}
  else if(command.method==='close'){socket.close();break;}
 }catch(error){console.log(JSON.stringify({error:String(error)}));}
}
socket.close();
process.stdin.destroy();
