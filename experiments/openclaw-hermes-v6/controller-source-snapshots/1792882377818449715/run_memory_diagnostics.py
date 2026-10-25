"""Native memory composition and explicit collection counterfactual, not product baseline grading.
Shows initialization/heap/context components; cannot turn a default peak into a minimum RAM requirement.
"""
import json,os,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan
from resources import create,read,wrap
from run_state_ops import cli
OC=r'''
import fs from 'node:fs';import v8 from 'node:v8';let collected=false;
const snap=(stage)=>fs.appendFileSync('/workspace/native-memory.jsonl',JSON.stringify({stage,pid:process.pid,time:Date.now(),modules:process.moduleLoadList.length,...process.memoryUsage(),v8:v8.getHeapStatistics()})+'\n');
export default {id:'memobserver',register(api){snap('register');api.on('llm_input',()=>{snap('before_model');if(FORCE&&!collected){collected=true;snap('before_explicit_gc');global.gc?.();snap('after_explicit_gc');}});api.on('after_tool_call',()=>snap('after_tool'));}};
'''
H=r'''
import json,os,resource,sys,gc,time
from pathlib import Path
collected=False
def snap(stage):
 with Path('/workspace/native-memory.jsonl').open('a') as f:f.write(json.dumps(dict(stage=stage,pid=os.getpid(),time=time.time(),modules=len(sys.modules),peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,allocated_blocks=sys.getallocatedblocks()))+'\n')
def before(**kw):
 global collected
 snap('before_model')
 if FORCE and not collected:collected=True;snap('before_explicit_gc');gc.collect();snap('after_explicit_gc')
def after(**kw):snap('after_tool')
def register(ctx):snap('register');ctx.register_hook('pre_llm_call',before);ctx.register_hook('post_tool_call',after)
'''
def one(unit,family,force):
 run=R/'runs-memory-diagnostics'/('explicit-gc' if force else 'native-auto-gc')/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial memory diagnostic retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled file context pressure. Read the local context fixture through native file tools32times.');(work/'context.txt').write_text('MEMORY_CONTEXT_TOKEN\n'+'\n'.join(f'{i:04} '+('abcdefghijklmno0123456789'*12) for i in range(1000)))
 p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text())
 if family=='openclaw':
  plugin=run/'state/plugins/memobserver';plugin.mkdir(parents=True);save(plugin/'package.json',{'name':'memobserver','version':'1.0.0','type':'module','openclaw':{'extensions':['./index.js']}});save(plugin/'openclaw.plugin.json',{'id':'memobserver','activation':{'onStartup':True},'configSchema':{'type':'object','properties':{},'additionalProperties':False}});(plugin/'index.js').write_text(OC.replace('FORCE','true' if force else 'false'));c['plugins']={'load':{'paths':['/state/plugins/memobserver']},'entries':{'memobserver':{'enabled':True}}}
 else:
  plugin=run/'state/hermes/plugins/memobserver';plugin.mkdir(parents=True);save(plugin/'plugin.yaml',dict(name='memobserver',version='1.0.0',description='Native process memory observer'));(plugin/'__init__.py').write_text(H.replace('FORCE','True' if force else 'False'));c['plugins']={'enabled':['memobserver'],'isolation':'in_process'};c['background_review']={'enabled':False}
 save(p,c)
 if family=='openclaw':
  cmd=sandbox(run/'state',work,family,cli(family,['plugins','install','--force','--accept-capabilities','--link','/state/plugins/memobserver']));p=subprocess.run(cmd,capture_output=True,text=True,timeout=90);save(run/'observer-install.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
  if p.returncode:raise RuntimeError('Memory observer did not install')
 (work/'native-memory.jsonl').unlink(missing_ok=True)
 issued=0
 def route(names,body):
  nonlocal issued
  if issued>=32:return []
  issued+=1
  name=next((n for n in names if n in ['read','read_file']),None)
  if not name:raise RuntimeError('Native file read capability absent')
  return [(name,{'path':'/workspace/context.txt','limit':2000})]
 fixture=Plan(run,family,router=route);cmd=command(family)
 if family=='openclaw':cmd.insert(1,'--expose-gc')
 args=sandbox(run/'state',work,family,cmd,fixture.socket_dir);group=create('memdiag-'+family+'-'+str(time.time_ns()));args=wrap(group,args);print('MEMORY_DIAGNOSTIC_START',unit,family,force,flush=True)
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(args,stdout=out,stderr=err,timeout=180)
  path=work/'native-memory.jsonl';observations=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else [];requests=[x['request'] for x in fixture.calls if x['main']];last_results=[m for m in requests[-1].get('messages',[]) if m.get('role')=='tool'] if requests else [];rec=dict(unit=unit,family=family,explicit_collection=force,exit_code=p.returncode,completed_same_read_plan=p.returncode==0 and issued==32 and sum(x.get('stage')=='after_tool' for x in observations)>=32,main_requests=len(requests),largest_request_chars=max((len(json.dumps(b)) for b in requests),default=0),resources=read(group),native_memory=observations,baseline_credit=False,scope='Controlled context pressure and public native observer; GC diagnostics are not a task-quality or minimum-memory benchmark. Node --expose-gc enables observation only; Python explicit gc collects cycles, reference counting remains automatic.')
  save(run/'result.json',rec);print('MEMORY_DIAGNOSTIC_DONE',unit,family,force,rec['completed_same_read_plan'],len(observations),flush=True)
  if not rec['completed_same_read_plan'] or not observations:raise RuntimeError('Diagnostic workload/observer failed before interpreting memory composition')
  return rec
 finally:fixture.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for force in [False,True]:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(one(unit,family,force));save(R/'results/memory-diagnostics.json',results)
 print('MEMORY_DIAGNOSTICS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
