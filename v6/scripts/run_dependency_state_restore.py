"""M02 integration: native state archive + freshly rebuilt application dependencies.
Three original semantic state units per product, new clean targets and namespaces.
Machine tool/byte caches are allowed warm; no original app venv/node_modules copied.
Same logical /state and /workspace, so this does not claim changed-path or cross-OS success.
"""
import hashlib,json,os,shutil
from pathlib import Path
from runtime import R,OLD,configuration,save,read_config
from run_upgrades import restore
from run_install_rebuild import operator_install,retain_rebuilt_dependencies
from run_state_ops import portable_call,cron_list_step,disabled_job_in
from gateway import Gateway
from controlled import Plan,shell
from native_operator_client import Operator

def one(unit,family):
 run=R/'runs-install-rebuild/state-restore'/f'u{unit}'/family
 if(run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial M02 integration retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('State restoration plus independent application dependency rebuild.')
 original=R/'runs-state-ops'/f'u{unit}'/family;source=original/'source';bundle=run/'native-backup-input';bundle.mkdir();archive=original/'archives'/('full-backup.tar.gz' if family=='openclaw' else 'full-backup.zip');target_archive=bundle/archive.name;shutil.copy2(archive,target_archive)
 if family=='hermes':shutil.copytree(source/'workspace',bundle/'external-workspace-adjunct')
 # Existing pinned read-only CLI is used only as a restore utility. The actual
 # post-restore agent verifier below must use its newly created app environment.
 restore(run,family,target_archive,old=False)
 expected_file=hashlib.sha256((source/'workspace/artifact.bin').read_bytes()).hexdigest();mounts=[]
 if family=='openclaw':
  package=run/'installed-openclaw';package.mkdir();mounts=[(package,'/runtime/openclaw',False)];user=R/'runtime/npm-empty-user-config';glob=R/'runtime/npm-empty-global-config';user.write_text('');glob.write_text('');cache=R/'runtime/npm-cache';cache.mkdir(exist_ok=True);installed=operator_install(run,family,['/runtime/node-v24.22.1-linux-x64/bin/npm','install','--prefix','/runtime/openclaw','--omit=dev','--foreground-scripts','--no-audit','--no-fund','--userconfig','/native-config/user','--globalconfig','/native-config/global','--cache','/native-npm-cache','openclaw@2026.10.6'],[*mounts,(user,'/native-config/user',True),(glob,'/native-config/global',True),(cache,'/native-npm-cache',False)],'/runtime/openclaw');mounts=[(package,'/runtime/openclaw',True)];new_generation=True
 else:
  home=run/'state/hermes';before=list((home/'installs').glob('*/environments/*'))
  if any((x/'venv/lib').is_dir() or (x/'venv/lib64').is_dir() for x in before):raise RuntimeError('Old native archive unexpectedly copied an application environment; do not credit this as a rebuild')
  code=run/'installed-source';shutil.copytree(R/'runtime/hermes-stable',code,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'));(home/'cache/uv').mkdir(parents=True,exist_ok=True);save(run/'state/benchmark-hermes-writable-installs.json',dict(cache=str(R/'runtime/hermes-installer/cache/uv'),scope='Old user state is imported but no application environment exists. Native PM builds dependencies from the pinned source/lock into this fresh target. Machine cache only.'));installed=operator_install(run,family,['python3','-m','pm.cli','install','--extra','all'],[(code,'/runtime/hermes-source',False)],'/runtime/hermes-source');mounts=[(code,'/runtime/hermes-source',True)];after=list((home/'installs').glob('*/environments/*'));new_generation=any((x/'venv/lib').is_dir() or (x/'venv/lib64').is_dir() for x in after)
  if not new_generation:raise RuntimeError('No new native dependency generation was created after the restore')
 for name in ['DELIVERED.txt','PLUGIN_DELIVERED']:(work/name).unlink(missing_ok=True)
 fixture=Plan(run,family,[shell('python3 /workspace/seed.py'),portable_call('/workspace/PLUGIN_DELIVERED'),cron_list_step]);gateway=Gateway(run,family,fixture,extra_mounts=mounts,allow_disk_warning=True);print('DEPENDENCY_STATE_RESTORE_START',unit,family,flush=True)
 try:
  gateway.start();response=gateway.chat('Continue the existing restored conversation; run its local verifier, retained native plugin and disabled scheduled-job inspection.','migration-'+str(unit),timeout=60);admin=None
  if family=='openclaw':
   with Operator(gateway) as client:admin=client.rpc('cron.list',{'includeDisabled':True},'native-rebuilt-runtime-job-list')
  gateway.stop();first=next((c['request'] for c in fixture.calls if c['main']),{});last=next((c['request'] for c in reversed(fixture.calls) if c['main']),{});tools=[m for m in last.get('messages',[]) if m.get('role')=='tool'];token='STATE_CANARY_'+str(unit)+'_'+family
  row=dict(unit=unit,family=family,native_install_exit=installed['exit_code'],application_dependencies_rebuilt_without_original_runtime_copy=new_generation,original_user_history_visible_before_new_tools=any(m.get('role')=='user' and token in json.dumps(m.get('content','')) and 'Create the controlled state fixture' in json.dumps(m.get('content','')) for m in first.get('messages',[])),artifact_hash_retained=hashlib.sha256((work/'artifact.bin').read_bytes()).hexdigest()==expected_file,actual_new_seed_effect=(work/'DELIVERED.txt').exists() and (work/'DELIVERED.txt').read_text()==token,actual_native_plugin=(work/'PLUGIN_DELIVERED').exists() and (work/'PLUGIN_DELIVERED').read_text()=='PORTABLE_PLUGIN_OK',disabled_job_retained=disabled_job_in(admin) if admin is not None else bool(tools) and disabled_job_in(tools[-1].get('content')),response_status=response.get('status'),archive_sha256=hashlib.sha256(target_archive.read_bytes()).hexdigest(),real_model=False,scope='M02 integration at original logical paths: native backup/import plus fresh app dependency build from pinned source/lock, real same-session continuation and actual plugin/file/job semantics. Existing immutable CLI is a restore utility only. Independent original source units reused, not new fault samples. No cross-OS claim.')
  row['passed']=response.get('status')==200 and all(row[k] for k in ['application_dependencies_rebuilt_without_original_runtime_copy','original_user_history_visible_before_new_tools','artifact_hash_retained','actual_new_seed_effect','actual_native_plugin','disabled_job_retained']);save(run/'result.json',row);print('DEPENDENCY_STATE_RESTORE_DONE',unit,family,row['passed'],flush=True)
  if not row['passed']:raise RuntimeError('Fresh dependencies plus restored state do not satisfy the semantic contract; inspect before classifying')
  row['retained_dependency_archive']=retain_rebuilt_dependencies(run,family);save(run/'result.json',row);return row
 finally:gateway.stop();fixture.close()

def main():
 from stage_provenance import snapshot
 snapshot('native-state-restore-and-dependency-rebuild-M02')
 os.chdir(OLD);rows=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):rows.append(one(unit,family));save(R/'results/dependency-state-restore.json',rows)
 print('DEPENDENCY_STATE_RESTORE_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
