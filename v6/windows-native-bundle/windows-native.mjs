// Fixed local-protocol native Windows platform matrix; zero paid inference.
// Installation/version evidence and native payload evidence are separate.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import os from 'node:os';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import {spawn,spawnSync} from 'node:child_process';
import {DatabaseSync} from 'node:sqlite';

const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const save=(p,v)=>fs.writeFileSync(p,JSON.stringify(v,null,2),'utf8');
const sha=v=>crypto.createHash('sha256').update(v).digest('hex');
const DUMMY='sk-local-portability-fixture-not-a-real-key';
function cleanEnv(input) {
  const out={};
  for(const [k,v] of Object.entries(input)) {
    if(/(KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL|AUTH|ASKPASS|COOKIE)/i.test(k))continue;
    out[k]=v;
  }
  Object.assign(out,{DEEPSEEK_API_KEY:DUMMY,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',OPENCLAW_SKIP_CHANNELS:'1'});
  return out;
}
async function run(exe,args,env,cwd,base,timeout=300000) {
  const out=fs.openSync(base+'.stdout.log','w'),err=fs.openSync(base+'.stderr.log','w');
  const child=spawn(exe,args,{env,cwd,stdio:['ignore',out,err],windowsHide:true});
  let timedOut=false;
  const timer=setTimeout(()=>{timedOut=true;if(child.exitCode===null&&child.pid) {
    if(process.platform==='win32')spawnSync('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true});
    else child.kill('SIGTERM');
  }},timeout);
  return await new Promise(resolve=>{
    let done=false;
    const finish=(code,error)=>{if(done)return;done=true;clearTimeout(timer);fs.closeSync(out);fs.closeSync(err);resolve({exit_code:code,error:error?.message,timed_out:timedOut});};
    child.on('error',e=>finish(null,e));child.on('close',code=>finish(code));
  });
}
function walk(p) {
  if(!fs.existsSync(p))return [];
  return fs.readdirSync(p,{withFileTypes:true}).flatMap(d=>d.isDirectory()?(new Set(['installs','node_modules','cache','tools','skills','logs']).has(d.name)?[]:walk(path.join(p,d.name))):[path.join(p,d.name)]);
}
function history(home,family,canary) {
  const hits=[];
  for(const file of walk(home).filter(x=>/\.(sqlite|db|sqlite3)$/.test(x))) {
    let db;
    try {
      db=new DatabaseSync(file,{readOnly:true});
      const tables=new Set(db.prepare("select name from sqlite_master where type='table'").all().map(x=>x.name));
      if(family==='hermes'&&tables.has('messages'))for(const row of db.prepare("select id,content from messages where role='user'").all()) {
        if(String(row.content).includes(canary))hits.push({file:path.relative(cfg.root,file),table:'messages',locator:row.id});
      }
      if(family==='openclaw'&&tables.has('transcript_events'))for(const row of db.prepare('select session_id,seq,event_json,event_zstd from transcript_events').all()) {
        const raw=row.event_zstd?zlib.zstdDecompressSync(row.event_zstd).toString('utf8'):row.event_json;
        const m=JSON.parse(raw).message;
        if(m?.role==='user'&&JSON.stringify(m).includes(canary))hits.push({file:path.relative(cfg.root,file),table:'transcript_events',locator:[row.session_id,row.seq]});
      }
    } finally {db?.close();}
  }
  return hits;
}

async function caseRun(family,unit) {
  if(fs.statfsSync(cfg.root).bavail*fs.statfsSync(cfg.root).bsize<6*1024**3)throw Error('Capacity guard before new native profile');
  const root=path.join(cfg.root,'cases',`u${unit}`,family),home=path.join(root,'profile'),workspace=path.join(root,'workspace');
  fs.mkdirSync(workspace,{recursive:true});fs.mkdirSync(home,{recursive:true});
  const token=`WINDOWS_NATIVE_${unit}_${family}_中文_é_😀`;
  const canary=`WINDOWS_USER_STATE_${unit}_${family}`;
  const filename=path.join(workspace,'原生 文件.txt');
  const records=[],native=[];let phase=0,index=0,readReceived=false,fixtureError=null;
  const server=http.createServer(async(req,res)=>{
    try {
      if(req.method==='GET'){res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({object:'list',data:[{id:'deepseek-flash',object:'model'}]}));return;}
      const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>8*1024**2)throw Error('Fixture body limit');chunks.push(chunk);}
      const body=JSON.parse(Buffer.concat(chunks));
      const names=(body.tools??[]).map(x=>x.function?.name);
      let calls=[];
      if(names.length) {
        const callId=`win${unit}${family}p${phase}call0`;
        if(phase===1)for(const m of body.messages??[])if(m.role==='tool'&&m.tool_call_id===callId&&JSON.stringify(m.content).includes(token))readReceived=true;
        if(index++===0){
          const name=phase===0?names.find(n=>['write','write_file'].includes(n)):names.find(n=>['read','read_file'].includes(n));
          if(!name)throw Error('Expected native file tool absent: '+names.join(','));
          calls=[{id:callId,type:'function',function:{name,arguments:JSON.stringify(phase===0?{path:filename,content:token}:{path:filename})}}];
        }
      }
      records.push({phase,main:names.length>0,tool_names:names,returned_calls:calls,received_tool_results:(body.messages??[]).filter(m=>m.role==='tool'),request_sha256:sha(JSON.stringify(body))});
      save(path.join(root,'fixture-records.json'),records);
      const message={role:'assistant',content:calls.length?null:(names.length?'PLATFORM_COMPLETE':'controlled auxiliary'),reasoning_content:''};
      if(calls.length)message.tool_calls=calls;
      const finish=calls.length?'tool_calls':'stop';
      if(!body.stream){res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({id:'win-fixed',object:'chat.completion',created:Math.floor(Date.now()/1000),model:'deepseek-flash',choices:[{index:0,message,finish_reason:finish}],usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0}}));return;}
      res.writeHead(200,{'content-type':'text/event-stream'});
      const delta={role:'assistant',reasoning_content:''};
      if(calls.length)delta.tool_calls=calls.map((c,i)=>({index:i,...c}));else delta.content=message.content;
      for(const [d,f] of [[delta,null],[{},finish]])res.write('data: '+JSON.stringify({id:'win-fixed',object:'chat.completion.chunk',created:Math.floor(Date.now()/1000),model:'deepseek-flash',choices:[{index:0,delta:d,finish_reason:f}]})+'\n\n');
      res.end('data: [DONE]\n\n');
    }catch(e){fixtureError=e.message;res.writeHead(500,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:'Evaluator fixture error; inspect fixture-error.json'}}));save(path.join(root,'fixture-error.json'),{error:e.message});}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const endpoint=`http://127.0.0.1:${server.address().port}/v1`;
  let env=cleanEnv(process.env),exe,args,workcwd=workspace;
  try {
    if(family==='openclaw') {
      env.OPENCLAW_STATE_DIR=home;env.OPENCLAW_CONFIG_PATH=path.join(root,'openclaw.json');
      save(env.OPENCLAW_CONFIG_PATH,{models:{providers:{deepseek:{baseUrl:endpoint,apiKey:DUMMY,api:'openai-completions',models:[{id:'deepseek-flash',name:'fixed local fixture',reasoning:true,input:['text'],contextWindow:1000000,maxTokens:65536,compat:{thinkingFormat:'deepseek',supportsDeveloperRole:false,maxTokensField:'max_tokens'}}]}}},agents:{defaults:{workspace,model:{primary:'deepseek/deepseek-flash',fallbacks:[]},models:{'deepseek/deepseek-flash':{params:{maxTokens:65536}}}}},tools:{exec:{mode:'full'}}});
      exe=cfg.node;
    } else {
      const prep=spawnSync(cfg.bootstrap_python,['-m','pm.environments','--format','json'],{cwd:cfg.hermes_source,env:{...env,HERMES_HOME:cfg.hermes_owner,HERMES_RUNTIME_DIR:cfg.hermes_tools},encoding:'utf8',timeout:60000});
      if(prep.status!==0)throw Error('Native activation failed: '+String(prep.stderr).slice(-1500));
      env=cleanEnv(JSON.parse(prep.stdout));env.HERMES_HOME=home;env.HERMES_RUNTIME_DIR=cfg.hermes_tools;env.DEEPSEEK_BASE_URL=endpoint;
      const q=spawnSync(cfg.bootstrap_python,['-c','from pathlib import Path; from pm.environments import project_python; print(project_python(Path.cwd()))'],{cwd:cfg.hermes_source,env:{...env,HERMES_HOME:cfg.hermes_owner},encoding:'utf8',timeout:30000});
      if(q.status!==0)throw Error('Native selected interpreter lookup failed');exe=q.stdout.trim();workcwd=cfg.hermes_source;
      const c={model:{default:'deepseek-flash',provider:'deepseek',base_url:endpoint,context_length:1000000},agent:{reasoning_effort:'high',max_turns:16},max_tokens:32768,terminal:{backend:'local',cwd:workspace},tools:{tool_search:{enabled:'off'}},approvals:{single_query_mode:'approve'},fallback_providers:[],auxiliary:{}};
      for(const s of ['vision','compression','title_generation','session_search','curator','background_review','approval','skills_hub','mcp','web_extract'])c.auxiliary[s]={provider:'deepseek',model:'deepseek-flash',base_url:endpoint,fallback_chain:[]};
      fs.writeFileSync(path.join(home,'config.yaml'),JSON.stringify(c,null,2),'utf8');
    }
    for(phase=0;phase<2;phase++) {
      index=0;const prompt=path.join(root,`prompt-${phase}.txt`);
      fs.writeFileSync(prompt,phase===0?`${canary}: Perform the fixed native file write and then finish.`:'Read the already-created native file and then finish.','utf8');
      args=family==='openclaw'?[cfg.openclaw_entry,'agent','exec','--config',env.OPENCLAW_CONFIG_PATH,'--model','deepseek/deepseek-flash','--thinking','high','--timeout','180','--cwd',workspace,'--state-dir',home,'--message-file',prompt,'--json']:[path.join(cfg.hermes_source,'hermes'),'chat','--provider','deepseek','--model','deepseek-flash','--reasoning','high','--query-file',prompt,'--format','stream-json','--in',workspace];
      native.push(await run(exe,args,env,workcwd,path.join(root,`native-${phase}`)));
      if(native.at(-1).exit_code!==0||fixtureError)break;
    }
    const content=fs.existsSync(filename)?fs.readFileSync(filename,'utf8'):null;
    const hits=history(home,family,canary);
    const result={family,unit,platform:process.platform,entry:'native CLI',native,fixture_error:fixtureError,file_exact:content===token,read_result_from_native_tool:readReceived,prior_user_history_retained:hits.length>0,native_history:hits,paid_model_calls:0,scope:'Fresh native Windows CLI profiles, same installed dependencies, real file-tool write/read across two client processes and native history persistence. Does not certify Windows GUI/Gateway/services, plugins, or Linux-to-Windows state migration.'};
    result.passed=result.platform==='win32'&&native.length===2&&native.every(x=>x.exit_code===0&&!x.timed_out)&&!fixtureError&&result.file_exact&&readReceived&&hits.length>0;
    save(path.join(root,'result.json'),result);return result;
  }finally{await new Promise(resolve=>server.close(resolve));}
}

const results=[];
try {
  const linuxControl=process.argv.includes('--linux-positive-control');
  const planned=linuxControl?[[0,'openclaw']]:[1,2,3].flatMap(u=>(u%2?['openclaw','hermes']:['hermes','openclaw']).map(f=>[u,f]));
  for(const [u,f] of planned) {
    console.log('PLATFORM_CASE_START',process.platform,u,f);
    try{results.push(await caseRun(f,u));}catch(e){results.push({family:f,unit:u,classification:'needs_harness_and_environment_review',error:e.message,passed:null});}
    save(path.join(cfg.root,'platform-results.json'),{platform:process.platform,architecture:process.arch,node:process.version,results,scope:'Actual native execution required. null/unexecuted is not a product failure; the evaluator must review preparation, dependency and fixture failures before grading.'});
  }
}catch(e){save(path.join(cfg.root,'controller-error.json'),{error:e.message});process.exitCode=1;}
