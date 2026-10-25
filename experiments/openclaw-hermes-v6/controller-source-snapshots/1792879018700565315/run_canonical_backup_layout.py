"""Resolve O03/O06 operation-count confounding from an external OC config file.
Same three original semantic state units; a layout control, not new fault samples.
No actual model inference. H canonical home config + external-workspace adjunct
was already exercised by the three complete original recovery controls.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save,read_config
from gateway import Gateway
from controlled import Plan,shell
from run_state_ops import cli,portable_call,disabled_job_in
from native_operator_client import Operator
CANON='/state/openclaw/openclaw.json'

def environment(args):
 at=args.index('--');return args[:at]+['--setenv','OPENCLAW_CONFIG_PATH',CANON]+args[at:]

def gateway_for(run,fixture,mounts=(),persistent=False):
 g=Gateway(run,'openclaw',fixture,extra_mounts=mounts,persistent_namespace=persistent);g.command=environment(g.command);return g

def activate_two(staging,target):
 manifests=[]
 for p in staging.rglob('manifest.json'):
  try:d=json.loads(p.read_text())
  except ValueError:continue
  if isinstance(d.get('assets'),list) and all(isinstance(x,dict) and 'sourcePath' in x for x in d['assets']):manifests.append((p,d))
 if len(manifests)!=1:raise RuntimeError('Native canonical-layout manifest is not unique')
 manifest,data=manifests[0];actions=[]
 for original,destination in [('/state/openclaw',target/'state/openclaw'),('/workspace',target/'workspace')]:
  choices=[a for a in data['assets'] if original==a['sourcePath'] or original.startswith(a['sourcePath'].rstrip('/')+'/')]
  if not choices:raise RuntimeError('Native manifest does not cover logical asset '+original)
  asset=max(choices,key=lambda a:len(a['sourcePath']));member=Path(asset['archivePath']);base=manifest.parent.parent if member.parts[0]==manifest.parent.name else manifest.parent;source=base/member;relative=original[len(asset['sourcePath']):].lstrip('/');source=source/relative if relative else source
  if not source.resolve().is_relative_to(staging.resolve()):raise RuntimeError('Archive-contained activation source expected')
  shutil.copytree(source,destination,dirs_exist_ok=True,symlinks=True);actions.append(dict(source_asset=original,archive=str(source.relative_to(staging)),target=str(destination)))
 if not(target/'state/openclaw/openclaw.json').exists():raise RuntimeError('Canonical config did not travel inside the native profile asset; do not assume two-copy restoration')
 # Only the evaluator's transport constructor reads the external mirror. Native
 # product processes are explicitly pointed at CANON throughout. This mirror is
 # evaluator plumbing and never counted as a native user restore operation.
 shutil.copy2(target/'state/openclaw/openclaw.json',target/'state/openclaw.json')
 save(target/'canonical-offline-activation.json',dict(actions=actions,manifest=data,product_config_path=CANON,evaluator_only_transport_mirror='/state/openclaw.json'))
 return data,actions

def verify(run,unit,fixture,persistent=False,mounts=()):
 g=gateway_for(run,fixture,mounts,persistent);(run/'workspace/PLUGIN_DELIVERED').unlink(missing_ok=True)
 try:
  g.start();reply=g.chat('Verify the existing conversation, run its local verifier and retained native plugin, then inspect the disabled job.','migration-'+str(unit),timeout=60)
  with Operator(g) as operator:jobs=operator.rpc('cron.list',{'includeDisabled':True},'canonical-job-inventory')
  first=next((c['request'] for c in fixture.calls if c['main']),{});token='STATE_CANARY_'+str(unit)+'_openclaw';row=dict(http_status=reply.get('status'),original_history_visible=any(m.get('role')=='user' and token in json.dumps(m.get('content','')) and 'Create the controlled state fixture' in json.dumps(m.get('content','')) for m in first.get('messages',[])),seed_effect=(run/'workspace/DELIVERED.txt').exists() and (run/'workspace/DELIVERED.txt').read_text()==token,native_plugin_actual=(run/'workspace/PLUGIN_DELIVERED').exists() and (run/'workspace/PLUGIN_DELIVERED').read_text()=='PORTABLE_PLUGIN_OK',disabled_job_retained=disabled_job_in(jobs));save(run/'native-canonical-verification.json',row)
  if not all(row[k] for k in ['original_history_visible','seed_effect','native_plugin_actual','disabled_job_retained']) or reply.get('status')!=200:raise RuntimeError('Canonical layout changed the semantic state contract')
  return g,row
 except BaseException:g.stop();raise

def one(unit):
 run=R/'runs-canonical-backup-layout'/f'u{unit}'/'openclaw'
 if(run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial canonical-layout control retained '+str(run))
 original=R/'runs-state-ops'/f'u{unit}'/'openclaw/source';source=run/'source';source.mkdir(parents=True);shutil.copytree(original/'state',source/'state',symlinks=True,ignore=shutil.ignore_patterns('*.sock'));shutil.copytree(original/'workspace',source/'workspace',symlinks=True);shutil.copy2(source/'state/openclaw.json',source/'state/openclaw/openclaw.json');artifact=hashlib.sha256((source/'workspace/artifact.bin').read_bytes()).hexdigest();archives=run/'archives';archives.mkdir();fixture=Plan(source,'openclaw',[shell('python3 /workspace/seed.py'),portable_call('/workspace/PLUGIN_DELIVERED')]);g=None
 print('CANONICAL_LAYOUT_START',unit,flush=True)
 try:
  g,before=verify(source,unit,fixture,True,[(archives,'/archives',False)]);g.pause_owner();command=cli('openclaw',['backup','create','--output','/archives/canonical.tar.gz','--verify','--json']);created=g.harness('POST','/exec',{'command':command,'timeout':180},timeout=185);save(source/'native-canonical-backup.json',created)
  if created['exit_code']:raise RuntimeError('Native canonical-layout backup failed')
 finally:
  if g:g.stop()
  fixture.close()
 target=run/'target';target.mkdir();configuration('openclaw',target/'state');(target/'state/openclaw').mkdir(exist_ok=True);shutil.copy2(target/'state/openclaw.json',target/'state/openclaw/openclaw.json');(target/'workspace').mkdir();(target/'workspace/PROMPT.md').write_text('Native canonical-layout restoration verification.');staging=run/'staging';staging.mkdir();command=environment(sandbox(target/'state',target/'workspace','openclaw',cli('openclaw',['backup','restore','/archives/canonical.tar.gz','--target','/staging/fresh','--json']),extra_mounts=[(archives,'/archives',True),(staging,'/staging',False)]));result=subprocess.run(command,capture_output=True,text=True,timeout=180);save(target/'native-canonical-restore.json',dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr,command=command))
 if result.returncode:raise RuntimeError('Native canonical-layout staging restore failed')
 manifest,actions=activate_two(staging/'fresh',target);fixture=Plan(target,'openclaw',[shell('python3 /workspace/seed.py'),portable_call('/workspace/PLUGIN_DELIVERED')]);g=None
 try:g,after=verify(target,unit,fixture)
 finally:
  if g:g.stop()
  fixture.close()
 row=dict(unit=unit,family='openclaw',source_state_unit=str(original.relative_to(R)),layout_only_change=True,native_config_path=CANON,source=before,restored=after,artifact_hash_retained=hashlib.sha256((target/'workspace/artifact.bin').read_bytes()).hexdigest()==artifact,native_archive_sha256=hashlib.sha256((archives/'canonical.tar.gz').read_bytes()).hexdigest(),native_archive_asset_sources=[x['sourcePath'] for x in manifest['assets']],offline_activation_actions=actions,logical_roundtrip_operations=['native full backup with verification','native restore into staging','offline activation of complete native profile including config','offline activation of external workspace'],evaluator_transport_mirror_excluded_from_user_operations=True,real_model=False,scope='Same logical profile/workspace paths; canonical OC config inside native profile. Existing independent source state units are reused only for a layout contrast. No new fault sample, no core/state-row patch, no dependency or user-goal injection. Do not generalize this manual pinned runbook to native updater automation.')
 row['passed']=row['artifact_hash_retained'] and all(after[k] for k in ['original_history_visible','seed_effect','native_plugin_actual','disabled_job_retained']);save(run/'result.json',row);print('CANONICAL_LAYOUT_DONE',unit,row['passed'],flush=True);return row

def main():
 os.chdir(OLD);rows=[]
 for unit in range(1,4):rows.append(one(unit));save(R/'results/canonical-backup-layout.json',rows)
 print('CANONICAL_LAYOUT_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
