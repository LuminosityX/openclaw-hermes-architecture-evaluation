// Reference component: generic whole-turn bounded assembly and an owned commit index.
import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
const hash=value=>createHash('sha256').update(value).digest('hex');
const estimate=messages=>Math.ceil(Buffer.byteLength(JSON.stringify(messages),'utf8')/4);
export default {id:'eval-context-reference',kind:'context-engine',register(api){
 const storePath=api.pluginConfig.state_path;
 const read=()=>{
  if(!fs.existsSync(storePath))return {schema_version:1,commits:{}};
  const raw=fs.readFileSync(storePath);
  if(raw.length>512*1024)throw new Error('OWNED_CONTEXT_STORE_BOUND');
  return JSON.parse(raw);
 };
 const record=async(kind,values={})=>{
  const response=await fetch('http://127.0.0.1:18080/context-event',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({engine_id:'eval-context-reference',kind,...values})});
  if(!response.ok)throw new Error('OWNED_CONTEXT_OBSERVER_FAILURE');
 };
 api.registerContextEngine('eval-context-reference',()=>({
  info:{id:'eval-context-reference',name:'Owned reference context',version:'1.0.0',ownsCompaction:false,
   acceptedHostParams:['sessionKey','runtimeSettings','runtimeContext'],
   transcriptSemantics:{currentTurnFence:'before-current-turn-entry-v1',turnAdvancementIdempotency:'atomic-idempotent-v1'}},
  async ingest(){return {ingested:false};},
  async assemble(params){
   const messages=params.messages;const groups=[];
   for(const message of messages){if(message.role==='user'||groups.length===0)groups.push([]);groups.at(-1).push(message);}
   const budget=Number.isFinite(params.tokenBudget)?params.tokenBudget:1000000;
   const chosen=[];const limit=Math.max(1024,Math.floor(budget*.65));
   for(let index=groups.length-1;index>=0;index--){
    const candidate=[groups[index],...chosen].flat();
    if(chosen.length&&estimate(candidate)>limit)break;
    chosen.unshift(groups[index]);
   }
   const assembled=chosen.flat();const state=read();
   await record('assemble',{session_key:params.sessionKey,session_id:params.sessionId,
    supplied_budget:budget,input_estimated_tokens:estimate(messages),output_estimated_tokens:estimate(assembled),
    input_messages:messages.length,output_messages:assembled.length,loaded_commit_count:Object.keys(state.commits).length,
    input_sha256:hash(JSON.stringify(messages)),output_sha256:hash(JSON.stringify(assembled))});
   return {messages:assembled,estimatedTokens:estimate(assembled),promptAuthority:'assembled'};
  },
  async compact(){await record('compact-no-transcript-rewrite');return {ok:true,compacted:false,reason:'Reference assembly bounds context without claiming transcript compaction'};},
  async commitTurn(params){
   const state=read();const existing=state.commits[params.advancementKey];
   if(existing){await record('commit-duplicate',{advancement_key:params.advancementKey});return {status:'duplicate'};}
   state.commits[params.advancementKey]={session_id:params.sessionId,session_key:params.sessionKey,messages:params.messages};
   const raw=JSON.stringify(state);if(Buffer.byteLength(raw)>512*1024)throw new Error('OWNED_CONTEXT_STORE_BOUND');
   const temporary=storePath+'.owned-'+randomUUID();
   const handle=fs.openSync(temporary,'wx',0o600);
   try{fs.writeFileSync(handle,raw);fs.fsyncSync(handle);}finally{fs.closeSync(handle);}
   fs.renameSync(temporary,storePath);const directory=fs.openSync(path.dirname(storePath),'r');
   try{fs.fsyncSync(directory);}finally{fs.closeSync(directory);}
   await record('commit',{advancement_key:params.advancementKey,session_key:params.sessionKey,
    committed_messages:params.messages.length,store_sha256:hash(raw),commit_count:Object.keys(state.commits).length});
   return {status:'committed'};
  },
 }));
}};
