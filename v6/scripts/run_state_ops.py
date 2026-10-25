"""Native backup/restore plus clean Linux path migration. Real state, not just archive exit status."""
import hashlib,json,os,shutil,sqlite3,subprocess,time,tarfile,zipfile
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save
from gateway import Gateway
from controlled import Plan,shell
from relocation import rebind_configuration,sandbox_relocated
from activation import activate_openclaw

def cli(family,args):
 if family=='openclaw':return ['node','/runtime/openclaw/node_modules/openclaw/openclaw.mjs',*args]
 import shlex
 return ['bash','-c','cd /runtime/hermes-source; task_activation="$(python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes '+shlex.join(args)]
def invoke(run,family,args,label,relay=None,relocated=False):
 launch=sandbox_relocated if relocated else sandbox
 cmd=launch(run/'state',run/'workspace',family,cli(family,args),relay.socket_dir if relay else None);begin=time.monotonic();p=subprocess.run(cmd,capture_output=True,text=True,timeout=150);rec=dict(command=cmd,exit_code=p.returncode,seconds=time.monotonic()-begin,stdout=p.stdout,stderr=p.stderr);save(run/(label+'.json'),rec);return rec

def db_inventory(state,token):
 records=[]
 for p in state.rglob('*'):
  if not p.is_file() or p.suffix not in ['.db','.sqlite','.sqlite3'] or 'installs' in p.parts:continue
  try:
   conn=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);tables=[x[0] for x in conn.execute("select name from sqlite_master where type='table'")];hits=[]
   for table in tables:
    if table.startswith('sqlite_'):continue
    escaped='"'+table.replace('"','""')+'"';rows=list(conn.execute('SELECT * FROM '+escaped));matches=[row for row in rows if token in str(row)]
    if matches:hits.append(dict(table=table,count=len(matches),rows=[str(x) for x in matches]))
   status=conn.execute('PRAGMA integrity_check').fetchone()[0];conn.close();records.append(dict(path=str(p.relative_to(state)),integrity=status,token_hits=hits))
  except sqlite3.Error as ex:records.append(dict(path=str(p.relative_to(state)),error=type(ex).__name__))
 return records

def cron_step(names,body):
 cron=next((n for n in ['automations','cron'] if n in names),None)
 if cron:return [(cron,{'action':'add','job':{'name':'portable-disabled-job','enabled':False,'schedule':{'kind':'every','everyMs':3600000},'sessionTarget':'isolated','payload':{'kind':'agentTurn','message':'Synthetic migration canary, must remain disabled.'},'delivery':{'mode':'none'}}})]
 if 'cronjob_manage' in names:return [('cronjob_manage',{'action':'create','name':'portable-disabled-job','paused':True,'paused_reason':'migration experiment; no automatic execution','schedule':'every 1h','prompt':'Synthetic migration canary, must remain disabled.'})]
 raise RuntimeError('Native scheduled-job tool unavailable in fixture; inspect schemas')

def cron_list_step(names,body):
 cron=next((n for n in ['automations','cron'] if n in names),None)
 if cron:return [(cron,{'action':'list','includeDisabled':True})]
 if 'cronjob_manage' in names:return [('cronjob_manage',{'action':'list'})]
 raise RuntimeError('Native scheduled-job list tool unavailable')

def portable_call(marker):
 def call(names,body):
  name=next((n for n in names if n.endswith('portable_identity')),None)
  if not name:raise RuntimeError('Portable plugin was not actually advertised')
  return [(name,{'marker_path':marker})]
 return call

def prepare_portable_plugin(source,family,relay):
 if family=='openclaw':
  package=source/'workspace/portableprobe';package.mkdir();save(package/'package.json',{'name':'portableprobe','version':'1.0.0','type':'module','openclaw':{'extensions':['./index.js']}});save(package/'openclaw.plugin.json',{'id':'portableprobe','activation':{'onStartup':True},'contracts':{'tools':['portable_identity']},'configSchema':{'type':'object','properties':{},'additionalProperties':False}});code="import fs from 'node:fs';export default {id:'portableprobe',register(api){api.registerTool({name:'portable_identity',label:'Portable identity',description:'Verify unchanged restored plugin code really runs',parameters:{type:'object',properties:{marker_path:{type:'string'}},required:['marker_path']},async execute(id,args){fs.writeFileSync(args.marker_path,'PORTABLE_PLUGIN_OK');return {content:[{type:'text',text:JSON.stringify({identity:'PORTABLE_PLUGIN_OK',modulePath:import.meta.url})}]};}});}};";(package/'index.js').write_text(code)
  args=sandbox(source/'state',source/'workspace',family,cli(family,['plugins','install','--force','--accept-capabilities','/workspace/portableprobe']),relay.socket_dir);p=subprocess.run(args,capture_output=True,text=True,timeout=90);save(source/'portable-plugin-install.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
  if p.returncode:raise RuntimeError('Native portable plugin install failed')
  path=source/'state/openclaw/extensions/portableprobe/index.js'
 else:
  package=source/'state/hermes/plugins/portableprobe';package.mkdir(parents=True);save(package/'plugin.yaml',{'name':'portableprobe','version':'1.0.0','description':'Verify unchanged restored plugin code really runs','provides_tools':['portable_identity']});code="import json\nfrom pathlib import Path\ndef identity(args,**kw):\n Path(args['marker_path']).write_text('PORTABLE_PLUGIN_OK');return json.dumps({'identity':'PORTABLE_PLUGIN_OK','modulePath':__file__})\ndef register(ctx):ctx.register_tool(name='portable_identity',toolset='portableprobe',schema={'name':'portable_identity','description':'Verify unchanged restored plugin code really runs','parameters':{'type':'object','properties':{'marker_path':{'type':'string'}},'required':['marker_path']}},handler=identity)\n";(package/'__init__.py').write_text(code);path=package/'__init__.py'
 return dict(relative_path=str(path.relative_to(source/'state')),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def disabled_job_in(value):
 if isinstance(value,str):
  try:return disabled_job_in(json.loads(value))
  except ValueError:return False
 if isinstance(value,list):return any(disabled_job_in(x) for x in value)
 if isinstance(value,dict):
  if value.get('name')=='portable-disabled-job' and (value.get('enabled') is False or value.get('paused') is True or value.get('status') in ['disabled','paused']):return True
  return any(disabled_job_in(x) for x in value.values())
 return False

def restore_archived_plugin_dependencies(target,relay):
 records=[]
 for plugin in ['deepseek','portableprobe']:
  source=target/'state/openclaw/extensions'/plugin;staged=target/'workspace/.archived-plugin-source'/plugin;staged.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,staged,symlinks=True,ignore=shutil.ignore_patterns('node_modules'))
  restored=invoke(target,'openclaw',['plugins','install','--force','--accept-capabilities','/newworkspace/.archived-plugin-source/'+plugin],'restore-archived-plugin-'+plugin,relay,relocated=True);records.append(restored)
  if restored['exit_code']:raise RuntimeError('Documented archive-contained plugin dependency restoration did not complete')
 save(target/'documented-plugin-restoration.json',{'operations':records,'source':'Only code/material already present in this restored native archive; no fresh code injected from global runtime or controller fixture.'})
 return records

def run_case(unit,family):
 root=R/'runs-state-ops'/f'u{unit}'/family
 if (root/'result.json').exists():return json.loads((root/'result.json').read_text())
 if root.exists():raise RuntimeError('Partial state-ops attempt retained '+str(root))
 source=root/'source';source.mkdir(parents=True);configuration(family,source/'state');work=source/'workspace';work.mkdir();token='STATE_CANARY_'+str(unit)+'_'+family;
 p=source/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');cfg=json.loads(p.read_text());cfg['tools']={'toolSearch':False,'exec':{'mode':'full'}} if family=='openclaw' else {'tool_search':{'enabled':'off'}};
 if family=='hermes':cfg['platform_toolsets']={'api_server':['terminal','cronjob','portableprobe']};cfg['plugins']={'enabled':['portableprobe'],'isolation':'in_process'}
 else:cfg['tools']['alsoAllow']=['portable_identity'];cfg['cron']={'enabled':False}
 save(p,cfg);
 (work/'PROMPT.md').write_text('Native state migration experiment '+token);(work/'artifact.bin').write_bytes(hashlib.shake_256(token.encode()).digest(131072));artifact_sha=hashlib.sha256((work/'artifact.bin').read_bytes()).hexdigest()
 (work/'seed.py').write_text("from pathlib import Path\n(Path(__file__).parent/'DELIVERED.txt').write_text("+repr(token)+")\nprint("+repr(token)+")\n")
 fixture=Plan(source,family,[shell('python3 /workspace/seed.py'),portable_call('/workspace/PLUGIN_DELIVERED'),cron_step])
 if family=='openclaw':
  from native_provider_support import install_deepseek
  install_deepseek(source,fixture)
  # Installation updates the native plugin registry/config; assemble the
  # Gateway from that complete source configuration, before backup/restore.
 portable_source=prepare_portable_plugin(source,family,fixture)
 archive_dir=root/'archives';archive_dir.mkdir();gateway=Gateway(source,family,fixture,persistent_namespace=family=='openclaw',extra_mounts=[(archive_dir,'/archives',False)] if family=='openclaw' else [])
 print('STATE_OPS_START',unit,family,flush=True)
 try:
  gateway.start();reply=gateway.chat('Create the controlled state fixture '+token,'migration-'+str(unit),timeout=65);save(source/'seed-response.json',reply)
  if family=='openclaw':gateway.pause_owner()
  else:gateway.stop()
  inv=db_inventory(source/'state',token);save(source/'state-before.json',inv)
  last_seed=next((call['request'] for call in reversed(fixture.calls) if call['main']),{});seed_tools=[m for m in last_seed.get('messages',[]) if m.get('role')=='tool'];seed_job=bool(seed_tools) and disabled_job_in(seed_tools[-1].get('content'));save(source/'source-scheduled-job-positive.json',dict(created_and_disabled=seed_job,last_native_tool_result=seed_tools[-1] if seed_tools else None))
  if reply['status']!=200 or not (work/'DELIVERED.txt').exists() or not (work/'PLUGIN_DELIVERED').exists() or not seed_job or not any(x.get('token_hits') for x in inv):raise RuntimeError('Native state seed did not establish persisted conversation, actual plugin and disabled job')
  archive=work/('full-backup.tar.gz' if family=='openclaw' else 'full-backup.zip')
  if family=='openclaw':args=['backup','create','--output',str('/workspace/'+archive.name),'--verify','--json']
  else:args=['backup','--output','/workspace/'+archive.name,'--keep','0']
  # OC prevents recursive archives; destination is a separately mounted task-owned archive folder.
  cmd=cli(family,[x.replace('/workspace/'+archive.name,'/archives/'+archive.name) for x in args])
  if family=='openclaw':created=gateway.harness('POST','/exec',{'command':cmd,'timeout':180},timeout=185);created.update(command=cmd,transport='Unchanged native CLI inside the normally stopped owners existing namespace; no lock override.')
  else:
   outer=sandbox(source/'state',work,family,cmd,fixture.socket_dir,[(archive_dir,'/archives',False)]);p=subprocess.run(outer,capture_output=True,text=True,timeout=180);created=dict(command=outer,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
  save(source/'backup-create.json',created);archive=archive_dir/archive.name
  if created['exit_code'] or not archive.exists():raise RuntimeError('Backup failed; preserve original attempt')
  gateway.stop()
  # A clean namespace target gets rebuilt framework dependencies, no source installation or sockets copied.
  target=root/'target-different-path';target.mkdir();configuration(family,target/'state');(target/'workspace').mkdir();(target/'workspace/PROMPT.md').write_text('Restore validation '+token)
  if family=='openclaw':
   stage=root/'staging';cmd=sandbox(target/'state',target/'workspace',family,cli(family,['backup','restore','/archives/'+archive.name,'--target','/staging/restored','--json']),fixture.socket_dir,[(archive_dir,'/archives',True),(root,'/staging',False)])
   p=subprocess.run(cmd,capture_output=True,text=True,timeout=180);save(target/'restore-native.json',dict(command=cmd,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
   if p.returncode:raise RuntimeError('Native restore refused; inspect')
   manifests=list((root/'restored').rglob('manifest.json'));save(target/'restore-manifests.json',[dict(path=str(x),content=json.loads(x.read_text())) for x in manifests])
   activate_openclaw(root/'restored',target/'state',target/'workspace',target/'offline-activation.json')
   actions=['native backup with verification','native restore to fresh staging','manifest-based offline activation of state/config/workspace','doctor before restart']
  else:
   cmd=sandbox(target/'state',target/'workspace',family,cli(family,['import','/archives/'+archive.name,'--force']),fixture.socket_dir,[(archive_dir,'/archives',True)])
   p=subprocess.run(cmd,capture_output=True,text=True,timeout=180);save(target/'restore-native.json',dict(command=cmd,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
   if p.returncode:raise RuntimeError('Native import failed')
   # Explicit external workspace adjunct: native Hermes home backup does not claim to include /workspace.
   shutil.copytree(work,target/'workspace',dirs_exist_ok=True)
   actions=['native home backup','separate external-workspace capture','native home import','restore external workspace','doctor before restart']
  after=db_inventory(target/'state',token);save(target/'state-restored.json',after)
  artifact=(target/'workspace/artifact.bin').exists() and hashlib.sha256((target/'workspace/artifact.bin').read_bytes()).hexdigest()==artifact_sha
  history=any(x.get('token_hits') for x in after);integrity=all(x.get('integrity')=='ok' for x in after)
  # Native doctor is diagnostic, not an automatic core patch; retain all reported issues.
  rebind_configuration(target/'state',family)
  if family=='openclaw':restore_archived_plugin_dependencies(target,fixture);actions+=['stage archive-contained plugin package sources','native reinstall of preserved deepseek plugin dependencies/registration','native reinstall of preserved portableprobe plugin dependencies/registration']
  diagnosis=invoke(target,family,['doctor','--fix','--non-interactive'] if family=='openclaw' else ['doctor'],'doctor',fixture,relocated=True)
  (target/'workspace/DELIVERED.txt').unlink(missing_ok=True);(target/'workspace/PLUGIN_DELIVERED').unlink(missing_ok=True);target_fixture=Plan(target,family,[shell('python3 /newworkspace/seed.py'),portable_call('/newworkspace/PLUGIN_DELIVERED'),cron_list_step]);resumed=Gateway(target,family,target_fixture,relocated=True)
  admin_jobs=None
  try:
   resumed.start();new_reply=resumed.chat('Verify the restored history and workspace. You are explicitly allowed to run the migrated seed.py and write its local verification marker; do not perform external actions.','migration-'+str(unit));save(target/'continuation.json',new_reply)
   if family=='openclaw':
    from native_operator_client import Operator
    with Operator(resumed) as client:admin_jobs=client.rpc('cron.list',{'includeDisabled':True},'native-administrator-job-list')
  finally:resumed.stop();target_fixture.close()
  initial_request=next((c['request'] for c in target_fixture.calls if c['main']),{});visible=token in json.dumps(initial_request.get('messages',[]))
  last_request=next((c['request'] for c in reversed(target_fixture.calls) if c['main']),{});last_tools=[m for m in last_request.get('messages',[]) if m.get('role')=='tool'];job_held=disabled_job_in(admin_jobs) if admin_jobs is not None else bool(last_tools) and disabled_job_in(last_tools[-1].get('content'));plugin_marker=target/'workspace/PLUGIN_DELIVERED';plugin_called=plugin_marker.exists() and plugin_marker.read_text()=='PORTABLE_PLUGIN_OK';plugin_file=target/'state'/portable_source['relative_path'];plugin_code_held=plugin_file.exists() and hashlib.sha256(plugin_file.read_bytes()).hexdigest()==portable_source['sha256']
  rec=dict(unit=unit,family=family,relocated_user_and_paths={'uid':1000,'gid':1000,'state':'/moved-state','workspace':'/newworkspace'},post_migration_tool_effect=(target/'workspace/DELIVERED.txt').exists() and (target/'workspace/DELIVERED.txt').read_text()==token,native_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),artifact_integrity=artifact,persisted_history=history,sqlite_integrity=integrity,new_turn_accepted=new_reply.get('status')==200,prior_history_visible_on_new_turn=visible,passed=artifact and history and integrity and new_reply.get('status')==200 and visible and (target/'workspace/DELIVERED.txt').exists(),logical_actions=actions+['rebind configured paths and activate under UID/GID1000'],scope='Clean Linux namespace, changed visible state/workspace/home paths and UID/GID1000, different real task path, shared immutable runtime cache reactivated from locked dependencies; cross-OS unavailable, not scored as failure. External workspace adjunct is explicitly recorded for Hermes.')
  rec.update(portable_plugin_source=portable_source,post_migration_native_plugin_called=plugin_called,portable_plugin_source_hash_retained=plugin_code_held,scheduled_job_listed_and_still_disabled=job_held,job_current_list_tool_result=last_tools[-1] if last_tools else None,native_administrator_job_inventory=admin_jobs);rec['passed']=rec['passed'] and plugin_called and plugin_code_held and job_held
  save(root/'result.json',rec);print('STATE_OPS_DONE',unit,family,rec['passed'],flush=True);return rec
 finally:gateway.stop();fixture.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,family));save(R/'results/state-ops.json',results)
 print('STATE_OPS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
