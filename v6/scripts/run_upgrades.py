"""Real old/new releases, native backup and state activation/rollback. No model fees.
This measures pinned release state compatibility and recovery; it does not pretend to benchmark a latest-channel updater.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save
from gateway import Gateway
from controlled import Plan,shell
from run_state_ops import cli,cron_step,db_inventory,cron_list_step,disabled_job_in
from run_approvals import oc_cli
from prepare_upgrades import OC,HS,HI,HT
from activation import activate_openclaw

def install_facts(state,root):
 home=state/'hermes';home.mkdir(parents=True,exist_ok=True)
 for item in (root/'installs').iterdir():
  if not item.is_dir():continue
  target=home/'installs'/item.name;target.mkdir(parents=True,exist_ok=True)
  for name in ['facts.json','inputs']:
   source=item/name
   if source.is_dir():shutil.copytree(source,target/name,dirs_exist_ok=True)
   elif source.exists():shutil.copy2(source,target/name)
  p=target/'facts.json'
  if p.exists():p.write_text(p.read_text().replace('/runtime/installer-state/hermes/installs/','/state/hermes/installs/'))
  (target/'environments').mkdir(exist_ok=True)

def mounts(family,state,old):
 if not old:return []
 if family=='openclaw':return [(OC,'/runtime/openclaw',True)]
 extra=[(HS,'/runtime/hermes-source',True),(HT,'/runtime/hermes-tools',True),(HI/'hermes','/runtime/installer-state/hermes',True)]
 for item in (HI/'hermes/installs').iterdir():
  if not (item/'environments').exists():continue
  extra.append((item/'environments',f'/state/hermes/installs/{item.name}/environments',True))
  for generation in (item/'environments').iterdir():
   if generation.is_dir():
    (generation/'.leases').mkdir(exist_ok=True);lease=state/'runtime-leases'/item.name/generation.name;lease.mkdir(parents=True,exist_ok=True);extra.append((lease,f'/state/hermes/installs/{item.name}/environments/{generation.name}/.leases',False))
 return extra

def setup(state,family,old):
 configuration(family,state)
 if family=='hermes' and old:
  shutil.rmtree(state/'hermes/installs');install_facts(state,HI/'hermes')

def invoke(run,family,old,args,label,extra=(),gateway=None):
 if gateway:
  cmd=cli(family,args);rec=gateway.harness('POST','/exec',{'command':cmd,'timeout':180},timeout=185);rec['command']=cmd;rec['transport']='Same normally stopped owner namespace; unchanged native CLI.'
 else:
  cmd=sandbox(run/'state',run/'workspace',family,cli(family,args),extra_mounts=[*mounts(family,run/'state',old),*extra]);p=subprocess.run(cmd,capture_output=True,text=True,timeout=180);rec=dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr,command=cmd)
 save(run/(label+'.json'),rec)
 if rec['exit_code']:raise RuntimeError('Native release operation failed: '+label)
 return rec

def plugin(run,family):
 work=run/'workspace';source=work/'upgradeprobe';source.mkdir()
 if family=='openclaw':
  save(source/'package.json',{'name':'upgradeprobe','version':'1.0.0','type':'module','openclaw':{'extensions':['./index.js']}});save(source/'openclaw.plugin.json',{'id':'upgradeprobe','activation':{'onStartup':True},'contracts':{'tools':['upgrade_identity']},'configSchema':{'type':'object','properties':{},'additionalProperties':False}});(source/'index.js').write_text("import fs from 'node:fs';export default {id:'upgradeprobe',register(api){api.registerTool({name:'upgrade_identity',label:'Upgrade identity',description:'Prove unchanged plugin still executes',parameters:{type:'object',properties:{}},async execute(){fs.writeFileSync('/workspace/PLUGIN_CALLED','UNCHANGED_PLUGIN');return {content:[{type:'text',text:'UNCHANGED_PLUGIN'}]};}});}};")
  invoke(run,family,True,['plugins','install','--force','--accept-capabilities','/workspace/upgradeprobe'],'plugin-install-old')
 else:
  source=run/'state/hermes/plugins/upgradeprobe';source.mkdir(parents=True);save(source/'plugin.yaml',dict(name='upgradeprobe',version='1.0.0',description='Unchanged upgrade probe',provides_tools=['upgrade_identity']));(source/'__init__.py').write_text("import json\nfrom pathlib import Path\ndef identity(args,**kw):\n Path('/workspace/PLUGIN_CALLED').write_text('UNCHANGED_PLUGIN');return json.dumps({'identity':'UNCHANGED_PLUGIN'})\ndef register(ctx):ctx.register_tool(name='upgrade_identity',toolset='upgradeprobe',schema={'name':'upgrade_identity','description':'Prove unchanged plugin still executes','parameters':{'type':'object','properties':{}}},handler=identity)\n")
 p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text())
 if family=='openclaw':c['tools']={'toolSearch':False,'exec':{'mode':'full'},'alsoAllow':['upgrade_identity']};c['cron']={'enabled':False}
 else:c['plugins']={'enabled':['upgradeprobe'],'isolation':'in_process'};c['tools']={'tool_search':{'enabled':'off'}};c['platform_toolsets']={'api_server':['terminal','cronjob','upgradeprobe']}
 save(p,c)

def plugin_call(names,body):
 name=next((n for n in names if n.endswith('upgrade_identity')),None)
 if name is None:raise RuntimeError('Installed upgrade plugin absent')
 return [(name,{})]
def list_cron(names,body):
 return cron_list_step(names,body)

def phase(run,family,old,name,unit,seed=False,hold=None):
 trace=run/name;trace.mkdir();token='UPGRADE_CANARY_U'+str(unit);steps=[shell('python3 /workspace/step.py '+name),plugin_call,cron_step if seed else list_cron];fixture=Plan(trace,family,steps);extra=mounts(family,run/'state',old)
 if hold:extra=[*extra,(hold['archives'],'/archives',False)]
 gateway=Gateway(run,family,fixture,extra_mounts=extra,persistent_namespace=family=='openclaw');(run/'workspace/PLUGIN_CALLED').unlink(missing_ok=True);retain=False
 print('UPGRADE_PHASE',unit,family,name,flush=True);begin=time.monotonic()
 try:
  gateway.start();res=gateway.chat(('Create the baseline '+token if seed else 'Continue the same task after the release transition; verify previous history and scheduled job.'),'upgrade-u'+str(unit),timeout=65);time.sleep(.5);admin_jobs=None
  if family=='openclaw':admin_jobs=oc_cli(gateway,['gateway','call','cron.list','--params',json.dumps({'includeDisabled':True}),'--json'],'native-admin-jobs-'+name)
  save(trace/'response.json',res);inventory=db_inventory(run/'state',token);save(trace/'native-state.json',inventory);first=next((x['request'] for x in fixture.calls if x['main']),{});last=next((x['request'] for x in reversed(fixture.calls) if x['main']),{});results=[m for m in last.get('messages',[]) if m.get('role')=='tool'];marker=run/'workspace/DELIVERED.json';got=json.loads(marker.read_text()) if marker.exists() else {};job_ok=disabled_job_in(admin_jobs) if admin_jobs is not None else bool(results) and disabled_job_in(results[-1].get('content'))
  rec=dict(phase=name,old_runtime=old,http_status=res.get('status'),seconds=time.monotonic()-begin,native_plugin_called=(run/'workspace/PLUGIN_CALLED').exists(),tool_effect=got.get('phase')==name,history_persisted=any(x.get('token_hits') for x in inventory),previous_history_on_first_request=token in json.dumps(first.get('messages',[])),scheduled_job_present=job_ok,scheduled_job_disabled=job_ok,native_administrator_job_inventory=admin_jobs);rec['passed']=res.get('status')==200 and rec['native_plugin_called'] and rec['tool_effect'] and rec['history_persisted'] and rec['scheduled_job_present'] and (seed or rec['previous_history_on_first_request']);save(trace/'result.json',rec)
  if not rec['passed']:raise RuntimeError('Release state contract did not hold; inspect native evidence before assigning cause')
  if hold:
   gateway.pause_owner();hold['gateway']=gateway;hold['fixture']=fixture;retain=True
  return rec
 finally:
  if not retain:gateway.stop();fixture.close()

def backup(run,family,archives,gateway=None):
 suffix='tar.gz' if family=='openclaw' else 'zip';name='pre-update.'+suffix
 args=['backup','create','--output','/archives/'+name,'--verify','--json'] if family=='openclaw' else ['backup','--output','/archives/'+name,'--keep','0'];invoke(run,family,True,args,'native-pre-update-backup',[(archives,'/archives',False)],gateway)
 if family=='hermes':shutil.copytree(run/'workspace',archives/'external-workspace-adjunct')
 return archives/name

def restore(run,family,archive,old=True):
 archive_dir=archive.parent
 if family=='openclaw':
  staging=run/'staging';staging.mkdir();invoke(run,family,old,['backup','restore','/archives/'+archive.name,'--target','/restore-target/fresh','--json'],'native-rollback-restore',[(archive_dir,'/archives',True),(staging,'/restore-target',False)]);activate_openclaw(staging/'fresh',run/'state',run/'workspace',run/'offline-rollback-activation.json')
 else:
  invoke(run,family,old,['import','/archives/'+archive.name,'--force'],'native-rollback-import',[(archive_dir,'/archives',True)]);shutil.copytree(archive_dir/'external-workspace-adjunct',run/'workspace',dirs_exist_ok=True)

def run_case(unit,family):
 root=R/'runs-upgrades'/f'u{unit}'/family
 if (root/'result.json').exists():return json.loads((root/'result.json').read_text())
 if root.exists():raise RuntimeError('Partial upgrade attempt retained '+str(root))
 active=root/'active';active.mkdir(parents=True);setup(active/'state',family,True);work=active/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Synthetic native release transition.');(work/'step.py').write_text("import json,sys\nfrom pathlib import Path\n(Path(__file__).parent/'DELIVERED.json').write_text(json.dumps({'phase':sys.argv[1]}))\nprint('STEP_'+sys.argv[1])\n");plugin(active,family);versions=[invoke(active,family,True,['--version'],'old-version')];archives=root/'archives';archives.mkdir();held={'archives':archives} if family=='openclaw' else None;old=phase(active,family,True,'old-baseline',unit,seed=True,hold=held)
 try:archive=backup(active,family,archives,held['gateway'] if held else None)
 finally:
  if held and held.get('gateway'):held['gateway'].stop();held['fixture'].close()
 # Install generations were created by the official pinned installers; activation switches the actual release artifact.
 if family=='hermes':install_facts(active/'state',R/'runtime/hermes-installer')
 versions.append(invoke(active,family,False,['--version'],'upgraded-version'));new=phase(active,family,False,'upgraded',unit)
 rollback=root/'rollback';rollback.mkdir();setup(rollback/'state',family,True);(rollback/'workspace').mkdir();(rollback/'workspace/PROMPT.md').write_text('Native rollback restore.');restore(rollback,family,archive);versions.append(invoke(rollback,family,True,['--version'],'rollback-version'));rolled=phase(rollback,family,True,'rollback-recovered',unit)
 rec=dict(unit=unit,family=family,versions=[x['stdout'] for x in versions],phases=[old,new,rolled],passed=all(x['passed'] for x in [old,new,rolled]),pre_update_backup_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),install_transition='Actual side-by-side official pinned releases and native dependency generations; preserve same user state during upgrade.',rollback='Original official release plus native pre-update backup restoration. Post-update work is outside that recovery point; no real external effects.',scope='State/schema/plugin compatibility and backup-based rollback. Does not measure latest-channel updater orchestration or universal downgrade compatibility.')
 save(root/'result.json',rec);print('UPGRADE_DONE',unit,family,rec['passed'],flush=True);return rec

def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,family));save(R/'results/upgrades.json',results)
 print('UPGRADE_CYCLES_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
