import fs from 'node:fs';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
const require = createRequire(import.meta.url);
const WebSocket = require('/runtime/dsh/node_modules/ws');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const root = 'http://127.0.0.1:3080';
const evidence = {surface:'native DSH Web server and its documented HTTP/Remote-mux WebSocket client protocol', host_stopped_during_observation:false, events:[]};
const record = value => {evidence.events.push({at:new Date().toISOString(),...value});fs.writeFileSync('/state/lifecycle_evidence.json',JSON.stringify(evidence,null,2));};
function jobProcesses(){
 const output=[];
 for(const pid of fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x))){
  try{
   const args=fs.readFileSync('/proc/'+pid+'/cmdline','utf8').split('\0');
   if(!args[0]?.split('/').at(-1).startsWith('python'))continue;
   if(!args.some(arg=>arg.split('/').at(-1)==='long_job.py'))continue;
   const fixture_arguments={};for(const flag of ['--run-id','--steps','--delay']){const at=args.indexOf(flag);if(at>=0)fixture_arguments[flag]=args[at+1];}
   output.push({pid_in_namespace:Number(pid),fixture_arguments});
  }catch{}
 }
 return output;
}
const log = fs.openSync('/state/dsh-web-server.log','w');
const server = spawn('node',['/runtime/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js','web','--no-open','--port','3080'],{stdio:['ignore',log,log],cwd:'/workspace'});
let viewer;
try {
 let tokenUrl;
 for(let i=0;i<120;i++){
  const text=fs.readFileSync('/state/dsh-web-server.log','utf8');
  tokenUrl=text.match(/http:\/\/127\.0\.0\.1:3080\/\S+/)?.[0];
  if(tokenUrl)break;
  if(server.exitCode!==null)throw Error('Native Web server exited: '+server.exitCode);
  await delay(250);
 }
 if(!tokenUrl)throw Error('Native Web listener readiness timeout');
 const exchange=await fetch(tokenUrl,{redirect:'manual'});
 const cookie=exchange.headers.getSetCookie().map(x=>x.split(';')[0]).join('; ');
 if(!cookie)throw Error('Native Web authentication cookie missing');
 async function rpc(method, request){
  const message={type:'client-request',rpcId:randomUUID(),method,payload:{args:request===undefined?{}:{[method==='session/list'?'_request':'request']:request}}};
  const response=await fetch(root+'/api/'+method,{method:'POST',headers:{'Content-Type':'application/json','Cookie':cookie,'Origin':root},body:JSON.stringify(message)});
  const decoded=await response.json();
  if(!decoded.result?.ok)throw Error(JSON.stringify(decoded.result?.error??decoded));
  return decoded.result.value;
 }
 const created=await rpc('session/create',{cwd:'/workspace'});
 const sessionId=created.sessionId;
 const selected=await rpc('session/selectModel',{sessionId,provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'high'});
 record({event:'native_session_created',sessionId,model_selection:selected});
 async function connectViewer(label){
  const ws=new WebSocket(root.replace('http:','ws:')+'/api/remote.mux',{headers:{Cookie:cookie,Origin:root}});
  const frames=[];
  ws.on('message',buffer=>{try{frames.push(JSON.parse(buffer.toString()));}catch{}});
  await new Promise((resolve,reject)=>{ws.once('open',resolve);ws.once('error',reject);});
  ws.send(JSON.stringify({type:'open',streamId:label,endpoint:'session/control',payload:{args:{}}}));
  for(let i=0;i<20&&frames.length===0;i++)await delay(100);
  return {ws,frames};
 }
 viewer=await connectViewer('initial-client');
 record({event:'native_viewer_connected',opening_frames:viewer.frames});
 if(process.argv.includes('--preflight')){
  const sessions=await rpc('session/list',{});
  record({event:'preflight_complete_without_prompt',sessions});
  console.log(JSON.stringify({preflight:true,sessionId,viewer_frames:viewer.frames.length,model_calls_expected:0}));
 }else{
  const runId=fs.readFileSync('/workspace/RUN_ID.txt','utf8').trim();
  await rpc('session/prompt',{sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:fs.readFileSync('/workspace/PROMPT.md','utf8')}],clientTimeZone:'Asia/Shanghai'});
  record({event:'public_task_submitted',run_id:runId,sessionId});
  const journal='/workspace/job_output/'+runId+'.jsonl';
  const readJournal=()=>fs.existsSync(journal)?fs.readFileSync(journal,'utf8').trim().split('\n').filter(Boolean).map(x=>JSON.parse(x)):[];
  let closed=false,everRunning=false;
  for(let i=0;i<900;i++){
   const rows=readJournal();
   const stepCount=rows.filter(x=>Number.isInteger(x.step)).length;
   const list=await rpc('session/list',{});
   const session=list.items.find(x=>x.sessionId===sessionId||x.id===sessionId);
   everRunning ||= session?.running===true;
   if(!closed&&stepCount>=2){
    record({event:'before_client_close',step_count:stepCount,native_host_pid:server.pid,native_host_alive:server.exitCode===null,session,job_processes:jobProcesses()});
    await new Promise(resolve=>{viewer.ws.once('close',resolve);viewer.ws.close(1000,'lifecycle fixture client close');});
    record({event:'native_client_connection_closed',step_count:stepCount,native_host_alive:server.exitCode===null,job_processes:jobProcesses(),independent_observer:'read-only session/list polling; never activates or resumes Agent'});closed=true;
   }
   const completed=rows.some(x=>x.completed===true&&x.steps===12&&x.run_id===runId);
   if(closed&&completed&&session?.running===false&&fs.existsSync('/workspace/job_report.json')){
    viewer=await connectViewer('returning-client');
    const returned=await rpc('session/list',{});
    const same=returned.items.find(x=>x.sessionId===sessionId||x.id===sessionId);
    record({event:'returned_to_same_native_session',sessionId,session:same,opening_frames:viewer.frames,original_job_completed:completed,step_count:stepCount});
    evidence.completed=true;break;
   }
   if(everRunning&&session?.running===false&&i>5&&!completed){record({event:'native_agent_idle_without_complete_original_job',session,step_count:stepCount});break;}
   if(server.exitCode!==null)throw Error('Execution host server exited during client test');
   await delay(2000);
  }
  record({event:'lifecycle_observation_end',completed:evidence.completed===true});
  if(!evidence.completed)process.exitCode=1;
 }
}catch(error){record({event:'controller_error',error:String(error)});console.error(String(error));process.exitCode=1;}
finally{
 if(viewer?.ws.readyState===WebSocket.OPEN)viewer.ws.close();
 server.kill('SIGTERM');
 for(let i=0;i<40&&server.exitCode===null;i++)await delay(250);
 if(server.exitCode===null)server.kill('SIGKILL');
}
