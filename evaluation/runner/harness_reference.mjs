// Public harness registration and public transcript SDK only. No private imports.
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire('/runtime/node_modules/openclaw/package.json');
const sdk=async name=>import(pathToFileURL(require.resolve('openclaw/plugin-sdk/'+name)).href);
export const supportsOwnedHarness=ctx=>ctx.provider==='fixture'
 ?{supported:true,priority:100}:{supported:false,reason:'Owned fixture route only'};
export function createOwnedActiveRun(params,onAbort,isRunning){
 let aborted=false;
 return {kind:'embedded',runId:params.runId,startedAtMs:Date.now(),
  async queueMessage(){throw new Error('OWNED_TOOL_FREE_HARNESS_DOES_NOT_ACCEPT_STEERING');},
  isStreaming:()=>isRunning()&&!aborted,isCompacting:()=>false,isAborted:()=>aborted,
  isStopped:()=>aborted||!isRunning(),isAbortable:()=>isRunning()&&!aborted,
  abort(){if(aborted)return;aborted=true;onAbort();params.onAttemptAbort?.();},
 };
}
export default {id:'eval-external-harness',register(api){
 const record=async(kind,fields={})=>{
  const response=await fetch('http://127.0.0.1:18080/harness-event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,pid:process.pid,...fields})});
  if(!response.ok)throw new Error('OWNED_HARNESS_OBSERVER_FAILURE');
 };
 api.registerAgentHarness({id:'eval-external-harness',label:'Owned tool-free external reference harness',
  autoSelection:{providerIds:[]},
  executionEnvironment:'host-only',supportsTurnScopedToolRestrictions:true,conversationToolPolicySupport:'exact',
  supports:supportsOwnedHarness,
  async loadModelCatalog(){return [{id:'fixture-model',name:'Owned deterministic arithmetic fixture',provider:'fixture',nativeRuntime:'eval-external-harness',contextWindow:128000,reasoning:false,input:['text']}];},
  async runAttempt(params){
   const started=Date.now();const host=params.hostCapabilities;
   host.assertActive();
   const match=params.prompt.match(/HARNESS_TASK (\{[^\n]+\})/);
   const token=params.prompt.match(/PILOT_[A-Z0-9_]+/)?.[0];
   if(!match||!token)throw new Error('OWNED_PUBLIC_ARITHMETIC_TASK_REQUIRED');
   const task=JSON.parse(match[1]);
   const common={agentHarnessId:'eval-external-harness',sessionIdUsed:params.sessionId,
    toolMetas:[],didSendViaMessagingTool:false,messagingToolSentTexts:[],messagingToolSentMediaUrls:[],messagingToolSentTargets:[],cloudCodeAssistFormatError:false,
    replayMetadata:{hadPotentialSideEffects:false,replaySafe:true},itemLifecycle:{startedCount:0,completedCount:0,activeCount:0}};
   const recorder=params.userTurnTranscriptRecorder;
   if(!recorder)throw new Error('PUBLIC_USER_RECORDER_REQUIRED');
   const lifecycle=await sdk('agent-harness-runtime');host.assertActive();
   let child;let running=true;
   const terminate=()=>{if(!child)return;try{process.kill(-child.pid,'SIGKILL');}catch(error){if(error.code!=='ESRCH')throw error;}};
   const handle=createOwnedActiveRun(params,()=>{terminate();void record('native-harness-abort-observed',{run_id:params.runId,session_id:params.sessionId,child_pid:child?.pid}).catch(()=>{});},()=>running);
   const abort=()=>handle.abort();
   lifecycle.setActiveEmbeddedRun(params.sessionId,handle,params.sessionKey,params.sessionFile,params.agentId);
   params.abortSignal?.addEventListener('abort',abort,{once:true});
   try{
   if(params.abortSignal?.aborted)abort();
   if(handle.isAborted())return {...common,terminal:{kind:'aborted',source:'external'},messagesSnapshot:[],assistantTexts:[],lastAssistant:undefined};
   await recorder.persistApproved({expectedSessionId:params.sessionId,beforeFreshMessageCommit:()=>host.assertActive()});
   host.assertActive();
   const user=recorder.getPersistedMessage?.()??await recorder.resolveMessage();
   host.assertActive();
   await record('native-harness-attempt',{run_id:params.runId,session_id:params.sessionId,session_key:params.sessionKey,task_id:task.task_id,host_capability_version:host.version,model:params.modelId,provider:params.provider});
   host.assertActive();
   if(handle.isAborted())return {...common,terminal:{kind:'aborted',source:'external'},messagesSnapshot:user?[user]:[],assistantTexts:[],lastAssistant:undefined};
   child=spawn('/usr/bin/python3',['/driver/external_harness_worker.py','--attempt'],{stdio:['pipe','pipe','pipe'],detached:true});
   child.stdin.on('error',()=>{});
   let output='';let error='';
   child.stdout.on('data',part=>{output+=part;if(Buffer.byteLength(output)>65536)terminate();});
   child.stderr.on('data',part=>{error=(error+part).slice(-4096);});
   const timer=setTimeout(terminate,Math.min(params.timeoutMs??10000,10000));
   let exit;
   try{
    child.stdin.end(JSON.stringify({task,state_directory:api.pluginConfig.state_directory+'/'+params.sessionId,fail_once:task.fail_once===true}));
    exit=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',code=>resolve(code));});
   }finally{clearTimeout(timer);}
   await record('external-child-exited',{child_pid:child.pid,exit_code:exit,task_id:task.task_id,session_id:params.sessionId,error});
   if(handle.isAborted())return {...common,terminal:{kind:'aborted',source:'external'},messagesSnapshot:user?[user]:[],assistantTexts:[],lastAssistant:undefined};
   host.assertActive();
   if(exit!==0)return {...common,terminal:{kind:'failed',source:'prompt',error:new Error('OWNED_EXTERNAL_EXECUTOR_EXIT_'+exit)},messagesSnapshot:user?[user]:[],assistantTexts:[],lastAssistant:undefined};
   const actual=JSON.parse(output);
   const text='ACCEPTED:'+token+' ANSWER:'+actual.value;
   const assistant={role:'assistant',content:[{type:'text',text}],api:'openai-completions',provider:params.provider,model:params.modelId,
    usage:{input:0,output:0,totalTokens:0,cacheRead:0,cacheWrite:0,cost:{input:0,output:0,total:0,cacheRead:0,cacheWrite:0}},stopReason:'stop',timestamp:Date.now()};
   const transcript=await sdk('session-transcript-runtime');host.assertActive();
   const idempotencyKey=params.runId+':owned-external-answer';
   const appended=await transcript.appendSessionTranscriptMessageByIdentity({sessionId:params.sessionId,sessionKey:params.sessionKey,agentId:params.agentId,config:params.config,
    message:assistant,idempotencyKey,beforeFreshMessageCommit:()=>host.assertActive()});
   if(!appended)throw new Error('PUBLIC_ASSISTANT_TRANSCRIPT_APPEND_NOT_CONFIRMED');
   host.assertActive();
   const messages=user?[user,assistant]:[assistant];
   await lifecycle.runAgentEndSideEffectsAsync({event:{messages,success:true,durationMs:Date.now()-started},ctx:{agentId:params.agentId,sessionKey:params.sessionKey,sessionId:params.sessionId,workspaceDir:params.workspaceDir,provider:params.provider,model:params.modelId,runId:params.runId}});
   return {...common,terminal:{kind:'ok'},messagesSnapshot:messages,assistantTexts:[text],lastAssistant:assistant,
    assistantTranscriptOwned:true,assistantTranscriptIdempotencyKey:idempotencyKey};
   }finally{
    running=false;params.abortSignal?.removeEventListener('abort',abort);
    lifecycle.clearActiveEmbeddedRun(params.sessionId,handle,params.sessionKey,params.sessionFile);
   }
  }
 });
}};
