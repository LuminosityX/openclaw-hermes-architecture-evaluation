"""Matched native tool, hook and context components with real plugin lifecycle."""
import json,os,subprocess,time,uuid,signal
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save,read_config
from controlled import Plan,shell
from gateway import Gateway
from run_state_ops import cli
OC=r'''
import fs from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
const V=VERSION;
const record=(kind,data={})=>fs.appendFileSync('/workspace/extension-events.jsonl',JSON.stringify({kind,version:V,pid:process.pid,...data})+'\n');
export default {id:'evalextension',name:'Matched evaluation extension',register(api){
 api.registerTool({name:'eval_transform',label:'Normalize',description:'Normalize a Unicode text value',parameters:{type:'object',properties:{text:{type:'string'}},required:['text']},async execute(id,args){const d={input:args.text,normalized:args.text.trim().toUpperCase(),version:V};record('tool',d);return {content:[{type:'text',text:JSON.stringify(d)}]};}});
 api.on('before_tool_call',async event=>{record('pre',{tool:event.toolName});if(String(event.params?.command||'').includes('BLOCKED_X02'))return {block:true,blockReason:'Matched extension policy'};});
 api.on('after_tool_call',async event=>{record('post',{tool:event.toolName});});
 api.registerContextEngine('evalextension',()=>({info:{id:'evalextension',name:'Matched filter',ownsCompaction:false,transcriptSemantics:{currentTurnFence:'before-current-turn-entry-v1',turnAdvancementIdempotency:'atomic-idempotent-v1'}},async ingest(){return {ingested:true};},async assemble(p){record('context');return {messages:p.messages.filter(m=>!(m.role==='assistant'&&JSON.stringify(m).includes('STALE_CONTEXT_MARKER'))),estimatedTokens:0,systemPromptAddition:'CONTEXT_ENGINE_CANARY'};},async compact(){return {ok:true,compacted:false};},async commitTurn(p){const db=new DatabaseSync('/state/evalextension-context.sqlite');try{db.exec('PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS commits (advancement_key TEXT PRIMARY KEY, payload TEXT NOT NULL)');const result=db.prepare('INSERT OR IGNORE INTO commits (advancement_key,payload) VALUES (?,?)').run(p.advancementKey,JSON.stringify(p.messages));record('context_commit',{advancementKey:p.advancementKey,duplicate:result.changes===0});return {status:result.changes===0?'duplicate':'committed'};}finally{db.close();}},async afterTurn(){record('after_turn');}}));
}};
'''
H=r'''
import json,os
from pathlib import Path
from agent.context_engine import ContextEngine
V=VERSION
def record(kind,**data):
 with Path('/workspace/extension-events.jsonl').open('a') as f:f.write(json.dumps({'kind':kind,'version':V,'pid':os.getpid(),**data},ensure_ascii=False)+'\n')
def transform(args,**kwargs):
 d=dict(input=args['text'],normalized=args['text'].strip().upper(),version=V);record('tool',**d);return json.dumps(d,ensure_ascii=False)
def before(tool_name,args,**kwargs):
 record('pre',tool=tool_name)
 if 'BLOCKED_X02' in str(args.get('command','')):return {'action':'block','message':'Matched extension policy'}
def after(tool_name,**kwargs):record('post',tool=tool_name)
class Engine(ContextEngine):
 @property
 def name(self):return 'evalextension'
 def update_from_response(self,usage):pass
 def should_compress(self,prompt_tokens=None):return False
 def compress(self,messages,current_tokens=None,focus_topic=None):return messages
 def select_context(self,request_messages,**kwargs):
  record('context');return [m for m in request_messages if not(m.get('role')=='assistant' and 'STALE_CONTEXT_MARKER' in str(m))]+[{'role':'system','content':'CONTEXT_ENGINE_CANARY'}]
 def on_turn_complete(self,*a,**kw):record('after_turn')
def register(ctx):
 ctx.register_tool(name='eval_transform',toolset='evalextension',schema={'name':'eval_transform','description':'Normalize a Unicode text value','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}},handler=transform)
 ctx.register_hook('pre_tool_call',before);ctx.register_hook('post_tool_call',after);ctx.register_context_engine(Engine())
'''
def install_source(run,family,version):
 state=run/'state';plugin=state/('plugins/evalextension' if family=='openclaw' else 'hermes/plugins/evalextension');plugin.mkdir(parents=True,exist_ok=True)
 if family=='openclaw':
  save(plugin/'package.json',{'name':'matched-evalextension','version':f'{version}.0.0','type':'module','openclaw':{'extensions':['./index.js']}});save(plugin/'openclaw.plugin.json',{'id':'evalextension','name':'Matched evaluation extension','kind':'context-engine','activation':{'onStartup':True},'contracts':{'tools':['eval_transform']},'configSchema':{'type':'object','properties':{},'additionalProperties':False}});(plugin/'index.js').write_text(OC.replace('VERSION',str(version)))
 else:
  save(plugin/'plugin.yaml',{'name':'evalextension','version':f'{version}.0.0','description':'Matched tool/hook/context extension','provides_tools':['eval_transform']});(plugin/'__init__.py').write_text(H.replace('VERSION',str(version)))
 return plugin

def tool_step(names,body):
 name=next((n for n in names if n.endswith('eval_transform')),None)
 if name:return [(name,{'text':'  Straße 中文  '})]
 # Missing plugin must not end the model plan before the native shell probes.
 return shell("python3 -c \"from pathlib import Path; Path('/workspace/BLOCKED_X02').write_text('bad')\"")(names,body)
def invoke(run,family,args,label,shared=None):
 if family=='hermes' and args[0]=='plugins':
  from native_hermes_mutation_support import prepare
  prepare(run)
 if shared and shared.get('gateway'):
  rec=shared['gateway'].harness('POST','/exec',{'command':cli(family,args),'timeout':90},timeout=95)
 else:
  p=subprocess.run(sandbox(run/'state',run/'workspace',family,cli(family,args)),capture_output=True,text=True,timeout=90);rec=dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
 save(run/(label+'.json'),rec)
 if rec['exit_code']:raise RuntimeError('Native plugin operation failed: '+label)
 return rec

def one_phase(root,family,label,mode='cli',shared=None):
 trace=root/label;trace.mkdir();steps=[tool_step,shell("python3 -c \"from pathlib import Path; Path('/workspace/BLOCKED_X02').write_text('bad')\""),shell("python3 -c \"from pathlib import Path; Path('/workspace/ALLOWED_X02').write_text('ok')\"")]
 if shared:
  fixture=shared['fixture'];fixture.run=trace;fixture.steps=steps;fixture.index=0;fixture.calls=[];fixture.faulted=False
 else:fixture=Plan(trace,family,steps)
 start=time.monotonic()
 try:
  if mode=='gateway':
   # A genuine prior native turn makes context removal observable. The seed
   # user marker must survive while only the stale assistant message is removed.
   fixture.steps.insert(0,lambda names,body:{'calls':[],'text':'STALE_CONTEXT_MARKER controlled obsolete assistant context'})
   gateway=Gateway(root,family,fixture,persistent_namespace=bool(shared))
   if shared:shared['gateway']=gateway
   try:
    gateway.start();seed_response=gateway.chat('SEED_CONTEXT_VISIBILITY Create the controlled history seed.','extension-'+label,timeout=60);save(trace/'seed-response.json',seed_response)
    response=gateway.chat('Run the controlled native extension plan '+label,'extension-'+label,timeout=60);code=0 if response.get('status')==200 else 1;save(trace/'response.json',response)
   finally:
    if shared:
     status=gateway.owner_status();targets=status.get('listening_owner_pids',[])
     if len(targets)!=1:raise RuntimeError('Cannot identify sole native owner for normal CLI handoff')
     gateway.owner_signal(signal.SIGTERM,targets[0]);until=time.monotonic()+30
     while time.monotonic()<until:
      status=gateway.owner_status()
      if status.get('owner_returncode') is not None and not status.get('listening_owner_pids'):break
      time.sleep(.1)
     else:raise RuntimeError('Native Gateway did not finish normal shutdown before exclusive CLI handoff')
     save(trace/'normal-owner-shutdown.json',status)
    else:gateway.stop()
  else:
   # This case evaluates full plugin/context capability. OpenClaw documents
   # agent exec as a separate bootstrap-free headless path; use the supported
   # full embedded CLI with plugin registry preload, and retain the exec-path
   # contrast separately rather than declaring the framework lacks an engine.
   cmd=cli(family,['agent','--local','--agent','main','--session-id',uuid.uuid4().hex,'--message',(root/'workspace/PROMPT.md').read_text(),'--json','--timeout','60']) if family=='openclaw' else command(family)
   if family=='hermes':cmd[-1]+=' --toolsets '+('terminal' if label in ['disabled-cli','uninstalled-cli'] else 'evalextension,terminal')
   if shared and shared.get('gateway'):
    result=shared['gateway'].harness('POST','/exec',{'command':cmd,'timeout':100},timeout=105);(trace/'stdout.jsonl').write_text(result['stdout']);(trace/'stderr.log').write_text(result['stderr']);code=result['exit_code']
   else:
    with (trace/'stdout.jsonl').open('w') as out,(trace/'stderr.log').open('w') as err:code=subprocess.run(sandbox(root/'state',root/'workspace',family,cmd,fixture.socket_dir),stdout=out,stderr=err,timeout=100).returncode
  path=root/'workspace/extension-events.jsonl';events=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else [];(trace/'extension-events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2));path.unlink(missing_ok=True)
  rec=dict(phase=label,entry=mode,exit_code=code,seconds=time.monotonic()-start,tool_events=[x for x in events if x['kind']=='tool'],hook_pre=sum(x['kind']=='pre' for x in events),hook_post=sum(x['kind']=='post' for x in events),context_executed=any(x['kind']=='context' for x in events),context_on_wire=any('CONTEXT_ENGINE_CANARY' in json.dumps(c['request'].get('messages',[])) for c in fixture.calls if c['main']),blocked_side_effect=(root/'workspace/BLOCKED_X02').exists(),allowed_side_effect=(root/'workspace/ALLOWED_X02').exists(),tool_advertised=any(any(x.get('function',{}).get('name','').endswith('eval_transform') for x in c['request'].get('tools',[])) for c in fixture.calls))
  if mode=='gateway':
   follow=[c for c in fixture.calls if c['main'] and c['index']>0];first=follow[0]['request'].get('messages',[]) if follow else [];text=json.dumps(first,ensure_ascii=False)
   rec.update(native_seed_response_delivered=seed_response.get('status')==200 and 'STALE_CONTEXT_MARKER' in json.dumps(seed_response.get('response',{})),prior_user_context_retained='SEED_CONTEXT_VISIBILITY' in text,stale_assistant_context_removed='STALE_CONTEXT_MARKER' not in text,context_filter_proven=bool(follow) and 'SEED_CONTEXT_VISIBILITY' in text and 'STALE_CONTEXT_MARKER' not in text)
  save(trace/'result.json',rec)
  for name in ['BLOCKED_X02','ALLOWED_X02']:(root/'workspace'/name).unlink(missing_ok=True)
  return rec
 finally:
  if not shared:fixture.close()
def run_case(unit,family):
 root=R/'runs-extensions'/f'u{unit}'/family
 if (root/'result.json').exists():return json.loads((root/'result.json').read_text())
 if root.exists():
  failure=root/'disable-native.json';cache=[root/name/'result.json' for name in ['registered-cli','registered-gateway','updated-cli']]
  if family=='hermes' and failure.exists() and all(p.exists() for p in cache):
   rejected=json.loads(failure.read_text());cfg=read_config(root/'state/hermes/config.yaml');phases=[json.loads(p.read_text()) for p in cache]
   if rejected.get('exit_code')!=0 and 'config.yaml and the active environment are unchanged' in rejected.get('stdout','') and 'evalextension' in cfg.get('plugins',{}).get('enabled',[]) and all(p['tool_advertised'] and p['tool_events'] and p['context_executed'] for p in phases):
    failure.rename(root/'disable-native-before-preparing-pm.json');print('EXTENSIONS_RESUME_VALID_PHASES',unit,family,flush=True);return finish_case(root,family,unit,root/'state/hermes/config.yaml',None,phases)
   if rejected.get('exit_code')==0 and 'evalextension' not in cfg.get('plugins',{}).get('enabled',[]) and all(p['tool_advertised'] and p['tool_events'] and p['context_executed'] for p in phases):
    print('EXTENSIONS_RESUME_AFTER_NATIVE_DISABLE',unit,family,flush=True);return finish_case(root,family,unit,root/'state/hermes/config.yaml',None,phases,True)
  raise RuntimeError('Partial extension attempt retained '+str(root))
 root.mkdir(parents=True);configuration(family,root/'state');(root/'workspace').mkdir();(root/'workspace/PROMPT.md').write_text('Matched native extension integration test.');install_source(root,family,1)
 p=root/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text())
 if family=='openclaw':c['plugins']={'allow':['evalextension'],'load':{'paths':['/state/plugins/evalextension']},'entries':{'evalextension':{'enabled':True}},'slots':{'contextEngine':'evalextension'}};c['tools']={'toolSearch':False,'exec':{'mode':'full'},'alsoAllow':['eval_transform']}
 else:c['plugins']={'enabled':['evalextension'],'isolation':'in_process'};c['context']={'engine':'evalextension'};c['tools']={'tool_search':{'enabled':'off'}};c['platform_toolsets']={'api_server':['evalextension','terminal']};c['approvals']={'mode':'off','single_query_mode':'approve','unattended_mode':'approve'}
 save(p,c);print('EXTENSIONS_START',unit,family,flush=True)
 shared=None
 if family=='openclaw':
  provider=root/'native-provider';provider.mkdir();shared={'fixture':Plan(provider,family,[])}
 try:return finish_case(root,family,unit,p,shared)
 finally:
  if shared:
   if shared.get('gateway'):shared['gateway'].stop()
   shared['fixture'].close()

def finish_case(root,family,unit,p,shared,cached_phases=None,disable_already_done=False):
 if cached_phases is not None:phases=cached_phases
 else:
  if family=='openclaw':invoke(root,family,['plugins','install','--force','--accept-capabilities','--link','/state/plugins/evalextension'],'install-native',shared)
  phases=[one_phase(root,family,'registered-cli',shared=shared),one_phase(root,family,'registered-gateway','gateway',shared)]
  if not all(x['tool_advertised'] and x['tool_events'] and x['context_executed'] and x['context_on_wire'] for x in phases):raise RuntimeError('Plugin/context component was not actually called; inspect before grading')
  install_source(root,family,2)
  if family=='openclaw':invoke(root,family,['plugins','install','--force','--accept-capabilities','--link','/state/plugins/evalextension'],'update-native',shared)
  phases.append(one_phase(root,family,'updated-cli',shared=shared))
 if not disable_already_done:invoke(root,family,['plugins','disable','evalextension'],'disable-native',shared)
 if family=='hermes':
  c=read_config(p);c['context']={'engine':'compressor'};save(p,c);save(root/'disable-context-selection.json',{'action':'Set context.engine=compressor as required by the separate config-driven engine loader; plugins.enabled alone does not select/deactivate that loader.','source':'plugins/context_engine/__init__.py:1-5'})
 phases.append(one_phase(root,family,'disabled-cli',shared=shared))
 if family=='openclaw':invoke(root,family,['plugins','uninstall','evalextension','--force'],'uninstall-native',shared)
 else:invoke(root,family,['plugins','remove','evalextension'],'uninstall-native',shared)
 # Ensure configuration no longer selects a removed context engine, as required by both contracts.
 c=read_config(p)
 if family=='openclaw':c.setdefault('plugins',{}).setdefault('slots',{})['contextEngine']='legacy'
 else:c['context']={'engine':'compressor'}
 save(p,c);phases.append(one_phase(root,family,'uninstalled-cli',shared=shared))
 registered=phases[:2];updated=phases[2];disabled=phases[3];uninstalled=phases[4]
 rec=dict(unit=unit,family=family,phases=phases,tool_contract=all(any(x.get('normalized')=='STRASSE 中文' for x in phase['tool_events']) for phase in registered),hook_contract=all(not x['blocked_side_effect'] and x['allowed_side_effect'] for x in registered),context_contract=all(x['context_executed'] and x['context_on_wire'] for x in registered) and registered[1].get('native_seed_response_delivered',False) and registered[1].get('context_filter_proven',False),update_contract=any(x['version']==2 for x in updated['tool_events']),disable_contract=not disabled['tool_advertised'] and not disabled['context_executed'] and disabled['blocked_side_effect'],uninstall_contract=not uninstalled['tool_advertised'] and not uninstalled['context_executed'] and uninstalled['blocked_side_effect'],core_modified=False,interfaces='Public native plugin registration, pre/post hooks and replaceable context-engine contract. Full executor replacement audited separately.')
 save(root/'result.json',rec);print('EXTENSIONS_DONE',unit,family,{k:v for k,v in rec.items() if k.endswith('_contract')},flush=True);return rec

def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,family));save(R/'results/extensions.json',results)
 print('EXTENSIONS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
