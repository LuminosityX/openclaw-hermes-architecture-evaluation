"""R09 full official Gateway fault domains, with the OS namespace kept alive.
Native plugin callbacks really enter and exit42; CLI-only observations are not generalized to services.
"""
import concurrent.futures,json,os,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save
from controlled import Plan
from gateway import Gateway
from run_native_suite import M
from run_state_ops import cli

def router(names,body):
 messages=body.get('messages',[]);last=max((i for i,m in enumerate(messages) if m.get('role')=='user'),default=0);text=str(messages[last].get('content',''));results=[m for m in messages[last+1:] if m.get('role')=='tool']
 if 'FAULT_TARGET' in text:
  if len(results)<2:
   target='probe_identity' if not results else 'probe_crash';name=next((n for n in names if n.endswith(target)),None)
   if not name:raise RuntimeError('Registered native plugin tool not advertised')
   return [(name,{})]
  if len(results)==2:
   name='exec' if 'exec' in names else 'terminal';args={'command':'python3 /workspace/survivor.py','background':False}
   if name=='exec':args.update(awaitResults=True,yieldMs=10000)
   return [(name,args)]
  return {'calls':[],'text':'TARGET_COMPLETE'}
 if 'PLUGIN_RECHECK' in text and not results:
  name=next((n for n in names if n.endswith('probe_identity')),None)
  return [(name,{})] if name else []
 return {'calls':[],'text':'NEIGHBOR_HEALTHY'}

def one(unit,family):
 run=R/'runs-gateway-plugin-fault'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial full-service plugin fault retained '+str(run))
 run.mkdir(parents=True);M.setup(run,family,'plugin-host');work=run/'workspace'
 if family=='openclaw':
  p=run/'state/plugins/crashprobe/index.js';s=p.read_text().replace("import fs from 'node:fs';", "import fs from 'node:fs';import {isMainThread,threadId} from 'node:worker_threads';").replace('{pid:process.pid}', '{pid:process.pid,isMainThread,threadId}');p.write_text(s)
 else:
  p=run/'state/hermes/config.yaml';c=json.loads(p.read_text());c['platform_toolsets']={'api_server':['crashprobe','terminal']};c.setdefault('approvals',{})['unattended_mode']='approve';save(p,c)
 if family=='openclaw':
  cmd=sandbox(run/'state',work,family,cli(family,['plugins','install','--force','--accept-capabilities','--link','/state/plugins/crashprobe']));p=__import__('subprocess').run(cmd,capture_output=True,text=True,timeout=90);save(run/'native-plugin-install.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
  if p.returncode:raise RuntimeError('Plugin did not install')
 fixture=Plan(run,family,router=router);gateway=Gateway(run,family,fixture,persistent_namespace=True);print('GATEWAY_PLUGIN_FAULT_START',unit,family,flush=True)
 try:
  gateway.start();before=gateway.owner_status();positive=gateway.chat('NEIGHBOR_CONTROL_BEFORE','neighbor-before',timeout=25)
  if positive.get('status')!=200:raise RuntimeError('Service positive control failed')
  begin=time.monotonic()
  try:target=gateway.chat('FAULT_TARGET Run the controlled registered plugin fault plan.','fault-target',timeout=45)
  except Exception as ex:target={'error':type(ex).__name__}
  identity_file=work/'plugin-identity.json';first_identity=json.loads(identity_file.read_text()) if identity_file.exists() else {};entered=(work/'plugin-crash-entered').exists();after=gateway.owner_status();alive=gateway.owner_alive();neighbor={}
  if alive:
   try:neighbor=gateway.chat('NEIGHBOR_CONTROL_AFTER','neighbor-after',timeout=15)
   except Exception as ex:neighbor={'error':type(ex).__name__}
  survived=(work/'SURVIVED').exists();manual_restart=not alive
  if manual_restart:gateway.restart_owner()
  identity_file.unlink(missing_ok=True)
  try:recheck=gateway.chat('PLUGIN_RECHECK Call the surviving or newly recovered plugin identity.','plugin-recheck',timeout=25)
  except Exception as ex:recheck={'error':type(ex).__name__}
  recheck_identity=json.loads(identity_file.read_text()) if identity_file.exists() else {};rec=dict(unit=unit,family=family,plugin_called=bool(first_identity),crash_entered=entered,identity=first_identity,owner_before=before,owner_after_fault=after,native_owner_alive_after_fault=alive,target_response=target,same_task_continued=survived,neighbor_after_fault=neighbor,neighbor_healthy=neighbor.get('status')==200,manual_owner_restart_needed=manual_restart,plugin_recheck=recheck,recheck_identity=recheck_identity,plugin_reloaded_and_called=bool(recheck_identity),seconds=time.monotonic()-begin,valid_fault=bool(first_identity) and entered,scope='Full official Gateway. Private persistent evaluator namespace remains live; plugin process exit and service/neighbor survival are distinct. Hosted plugin failure containment is not malicious-code OS isolation.')
  save(run/'result.json',rec);print('GATEWAY_PLUGIN_FAULT_DONE',unit,family,alive,survived,rec['neighbor_healthy'],flush=True)
  if not rec['valid_fault']:raise RuntimeError('Plugin callback did not actually enter; do not grade registration labels')
  return rec
 finally:gateway.stop();fixture.close()
def main():
 from run_async_recovery import main as native_async_recovery
 native_async_recovery()
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(one(unit,family));save(R/'results/gateway-plugin-fault.json',results)
 print('FULL_GATEWAY_PLUGIN_FAULTS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
