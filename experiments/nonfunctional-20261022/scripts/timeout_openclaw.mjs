import fs from'node:fs';import path from'node:path';import{pathToFileURL}from'node:url';
const R=path.resolve(import.meta.dirname,'..'),S='/root/output/openclaw-hermes-benchmark-20261022/sources/openclaw';process.env.OPENCLAW_STATE_DIR=R+'/runtime/control-openclaw';fs.mkdirSync(process.env.OPENCLAW_STATE_DIR,{recursive:true});
const{registerSealedRuntimeProcessEntrypoint}=await import(pathToFileURL(S+'/src/infra/runtime-process-url.ts'));registerSealedRuntimeProcessEntrypoint('serviceChildGroupAnchor',pathToFileURL(S+'/dist/process/supervisor/service-child-group-anchor.js'));
const{createExecTool}=await import(pathToFileURL(S+'/src/agents/bash-tools.exec-run.ts'));
const tool=createExecTool({host:'gateway',security:'full',ask:'off',allowBackground:false,timeoutSec:1});
await tool.execute('warmup',{command:'printf READY',workdir:R,timeoutSeconds:5});const records=[];
const alive=pid=>{try{const s=fs.readFileSync(`/proc/${pid}/stat`,'utf8');return s.slice(s.lastIndexOf(')')+2)[0]!=='Z';}catch{return false;}};
for(let i=0;i<5;i++){
 const prefix=R+'/runtime/control-openclaw/beat-'+i;const start=performance.now();let result,error;
 try{result=await tool.execute('timeout-'+i,{command:`/usr/bin/python3 ${R}/scripts/heartbeat.py ${prefix}`,workdir:R,timeoutSeconds:1});}catch(e){error=e.message;}
 const returned=performance.now();await new Promise(r=>setTimeout(r,300));const pids=fs.existsSync(prefix+'.pids')?JSON.parse(fs.readFileSync(prefix+'.pids')):[];const survivors=pids.filter(alive);let before=fs.existsSync(prefix+'.beat')?fs.readFileSync(prefix+'.beat','utf8'):null;
 await new Promise(r=>setTimeout(r,250));let after=fs.existsSync(prefix+'.beat')?fs.readFileSync(prefix+'.beat','utf8'):null;
 for(const pid of survivors){try{process.kill(pid,'SIGKILL');}catch{}}
 const rec={framework:'openclaw',sample:i,wall_ms:returned-start,configured_timeout_ms:1000,started:pids.length===2,pids,surviving_processes:survivors.length,heartbeat_continued:before!==after,result,error};records.push(rec);fs.writeFileSync(R+'/raw/timeout-openclaw.json',JSON.stringify(records,null,2));console.log(JSON.stringify({sample:i,wall_ms:rec.wall_ms,started:rec.started,survivors:survivors.length}));
}process.exit(0);
