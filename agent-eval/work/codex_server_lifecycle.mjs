import fs from 'node:fs';
import net from 'node:net';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const WebSocket=require('/runtime/dsh/node_modules/ws');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const evidence={surface:'official Codex app-server JSON-RPC over native Unix control socket; integration surface, not physical Windows/iOS UI',events:[]};
const record=value=>{evidence.events.push({at:new Date().toISOString(),...value});fs.writeFileSync('/state/lifecycle_evidence.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(value));};
const pairs=['model="gpt-6.1-sol"','model_reasoning_effort="medium"','model_provider="evaluation_gateway"','model_providers.evaluation_gateway.name="Evaluation audit relay"','model_providers.evaluation_gateway.base_url="http://127.0.0.1:18080/cx/backend-api/codex"','model_providers.evaluation_gateway.wire_api="responses"','model_providers.evaluation_gateway.requires_openai_auth=true','features.apps=false','features.enable_request_compression=false','sandbox_mode="danger-full-access"','approval_policy="never"'];
const args=pairs.flatMap(pair=>['-c',pair]).concat(['app-server','--listen','unix:///state/native-appserver.sock']);
const log=fs.openSync('/state/native-appserver.log','w');
const server=spawn('codex',args,{cwd:'/workspace',stdio:['ignore',log,log]});
let client;
async function connect(){
 const ws=new WebSocket('ws://localhost/',{createConnection:()=>net.connect('/state/native-appserver.sock')});
 const pending=new Map();const notifications=[];let next=1;
 ws.on('message',bytes=>{
  const message=JSON.parse(bytes.toString());
  if(message.id!==undefined&&pending.has(message.id)){
   const {resolve,reject}=pending.get(message.id);pending.delete(message.id);message.error?reject(Error(JSON.stringify(message.error))):resolve(message.result);
  }else{
   notifications.push(message);
   if(message.id!==undefined&&message.method){record({event:'unexpected_native_interaction',method:message.method});}
  }
 });
 await new Promise((resolve,reject)=>{ws.once('open',resolve);ws.once('error',reject);});
 function rpc(method,params){return new Promise((resolve,reject)=>{const id=next++;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('RPC timeout: '+method));}},20000).unref();});}
 await rpc('initialize',{clientInfo:{name:'agent_eval_lifecycle',version:'1.0',title:'Controlled lifecycle evaluation'},capabilities:{experimentalApi:true}});
 ws.send(JSON.stringify({method:'initialized',params:{}}));
 return {ws,rpc,notifications};
}
function processes(){
 const output=[];
 for(const pid of fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x))){try{
  const args=fs.readFileSync('/proc/'+pid+'/cmdline','utf8').split('\0');
  if(!args[0]?.split('/').at(-1).startsWith('python')||!args.some(x=>x.split('/').at(-1)==='long_job.py'))continue;
  const values={};for(const flag of ['--run-id','--steps','--delay']){const at=args.indexOf(flag);if(at>=0)values[flag]=args[at+1];}
  output.push({pid_in_namespace:Number(pid),fixture_arguments:values});
 }catch{}}
 return output;
}
try{
 for(let i=0;i<120;i++){if(fs.existsSync('/state/native-appserver.sock'))break;if(server.exitCode!==null)throw Error('Native app-server exited before ready');await delay(250);}
 client=await connect();
 const created=await client.rpc('thread/start',{model:'gpt-6.1-sol',modelProvider:'evaluation_gateway',cwd:'/workspace',approvalPolicy:'never',sandbox:'danger-full-access',allowProviderModelFallback:false,ephemeral:false});
 const threadId=created.thread.id;
 record({event:'native_thread_created',thread_id:threadId,model:created.model,reasoning_effort:created.reasoningEffort});
 if(process.argv.includes('--preflight')){record({event:'preflight_no_prompt_no_model'});}
 else{
  const runId=fs.readFileSync('/workspace/RUN_ID.txt','utf8').trim();
  const journal='/workspace/job_output/'+runId+'.jsonl';
  const rows=()=>fs.existsSync(journal)?fs.readFileSync(journal,'utf8').trim().split('\n').filter(Boolean).map(x=>JSON.parse(x)):[];
  await client.rpc('turn/start',{threadId,input:[{type:'text',text:fs.readFileSync('/workspace/PROMPT.md','utf8')}],model:'gpt-6.1-sol',effort:'medium'});
  let closed=false,lastCount=0,lastProgress=Date.now();
  for(let i=0;i<900;i++){
   const entries=rows();const steps=entries.filter(x=>'step'in x).length;
   if(steps!==lastCount){lastCount=steps;lastProgress=Date.now();}
   if(!closed&&steps>=2){
    record({event:'before_client_close',thread_id:threadId,step_count:steps,job_processes:processes(),native_host_alive:server.exitCode===null});
    await new Promise(resolve=>{client.ws.once('close',resolve);client.ws.close(1000,'client-close fixture');});closed=true;
    record({event:'native_client_connection_closed',step_count:steps,native_host_alive:server.exitCode===null,job_processes:processes()});
   }
   if(closed&&entries.some(x=>x.completed===true))break;
   if(closed&&processes().length===0&&Date.now()-lastProgress>12000)break;
   if(server.exitCode!==null)throw Error('Native execution host stopped');
   await delay(2000);
  }
  if(!closed)throw Error('No two-step client-close trigger');
  client=await connect();
  const resumed=await client.rpc('thread/resume',{threadId,model:'gpt-6.1-sol',modelProvider:'evaluation_gateway',cwd:'/workspace',approvalPolicy:'never',sandbox:'danger-full-access'});
  if(resumed.thread.id!==threadId)throw Error('Native thread identity changed on return');
  record({event:'returned_to_same_native_thread',thread_id:resumed.thread.id,original_job_completed:rows().some(x=>x.completed===true),step_count:rows().filter(x=>'step'in x).length});
  let recovery=false;
  for(let i=0;i<120;i++){
   const current=await client.rpc('thread/read',{threadId,includeTurns:true});
   const thread=current.thread;
   const active=thread.status?.type==='active'||thread.status?.type==='inProgress'||thread.turns?.some(x=>x.status==='inProgress');
   if(!active&&fs.existsSync('/workspace/job_report.json')){record({event:'native_thread_idle_report_present',thread_id:threadId,status:thread.status,original_job_completed:rows().some(x=>x.completed===true),step_count:rows().filter(x=>'step'in x).length});evidence.completed=true;break;}
   if(!active&&!fs.existsSync('/workspace/job_report.json')&&!recovery){
    recovery=true;record({event:'native_same_thread_read_only_reverification_requested',thread_id:threadId});
    await client.rpc('turn/start',{threadId,input:[{type:'text',text:'返回同一任务。不要重跑 long_job.py 或覆盖原日志。只核对本次原执行的日志并如实生成 job_report.json，记录实际完成状态、run_id、step数和日志路径；未知或未完成须明确。'}],model:'gpt-6.1-sol',effort:'medium'});
   }
   await delay(2000);
  }
  record({event:'lifecycle_observation_end',completed:evidence.completed===true});
  if(!evidence.completed)process.exitCode=1;
 }
}catch(error){record({event:'controller_error',error:String(error)});process.exitCode=1;}
finally{
 if(client?.ws.readyState===WebSocket.OPEN)client.ws.close();
 await delay(2000);
 server.kill('SIGTERM');for(let i=0;i<40&&server.exitCode===null;i++)await delay(250);if(server.exitCode===null)server.kill('SIGKILL');
}
