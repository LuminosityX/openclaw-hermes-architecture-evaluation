"""O01/M02 and O02: fresh native app dependency rebuild, then config repair.
Machine toolchains and byte caches may be warm; no application environment is
copied into these targets. This is not a cold-network or cross-OS benchmark.
"""
import json,os,re,shutil,subprocess,time,tarfile,hashlib
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan,shell
from run_state_ops import cli

def operator_install(run,family,cmd,mounts,cwd):
 base=sandbox(run/'state',run/'workspace',family,cmd,extra_mounts=mounts);at=base.index('--');args=[]
 for item in base[:at]:args.extend(['--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts'] if item=='--unshare-all' else [item])
 for path in ['/etc/resolv.conf','/etc/hosts']:
  if Path(path).exists():args+=['--ro-bind',path,path]
 env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE','PIP_INDEX_URL','UV_INDEX_URL','UV_DEFAULT_INDEX','PIP_EXTRA_INDEX_URL']}
 for key in ['SSL_CERT_FILE','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE']:
  path=env.get(key)
  if path and Path(path).is_file() and not path.startswith('/usr/'):args+=['--ro-bind',path,path]
 args+=['--chdir',cwd,'--']+cmd;started=time.monotonic()
 with (run/'native-install.log').open('w') as out:result=subprocess.run(args,env=env,stdout=out,stderr=out,stdin=subprocess.DEVNULL,timeout=900)
 rec=dict(exit_code=result.returncode,seconds=time.monotonic()-started,command=args,scope='Native installer-only network namespace, temporary HOME and experiment-owned target/cache. No agent, original user HOME or actual service credentials exposed; machine toolchains/cache are preprovided.');save(run/'native-install.json',rec)
 if result.returncode:raise RuntimeError('Fresh native application dependency setup requires preflight review')
 return rec

def delivery(run,family,label,mounts):
 trace=run/label;trace.mkdir();(run/'workspace/INSTALL_DELIVERED').unlink(missing_ok=True);fixture=Plan(trace,family,[shell('python3 /workspace/installer_probe.py')]);args=sandbox(run/'state',run/'workspace',family,command(family),fixture.socket_dir,mounts)
 try:
  with (trace/'stdout.jsonl').open('w') as out,(trace/'stderr.log').open('w') as err:result=subprocess.run(args,stdout=out,stderr=err,timeout=90)
  first=next((c for c in fixture.calls if c['main']),None);rec=dict(exit_code=result.returncode,actual_native_model_and_tool_loop=bool(first),tool_effect=(run/'workspace/INSTALL_DELIVERED').exists(),passed=result.returncode==0 and bool(first) and (run/'workspace/INSTALL_DELIVERED').exists());save(trace/'result.json',rec);return rec
 finally:fixture.close()

def retain_rebuilt_dependencies(run,family):
 # These are freshly generated experiment dependencies, never global runtimes
 # or native history. Keep a lossless archive before releasing disk blocks.
 target=run/'installed-openclaw' if family=='openclaw' else run/'state/hermes/installs'
 archive=run/'rebuilt-application-dependencies.tar.gz'
 if not target.exists():raise RuntimeError('Cannot archive absent rebuilt dependencies')
 count=sum(1 for p in target.rglob('*') if p.is_file())
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:tar.add(target,arcname=str(target.relative_to(run)),recursive=True)
 # Read every archive payload back; gzip CRC and tar payload are checked before
 # deleting the regenerable expanded copy. Config/history/receipts stay in place.
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    f=tar.extractfile(member)
    while f.read(1024*1024):pass
 sha=hashlib.sha256(archive.read_bytes()).hexdigest()
 record=dict(archive=str(archive.relative_to(run)),sha256=sha,expanded_file_count=count,expanded_relative_path=str(target.relative_to(run)),reason='Preserve the complete successful independent rebuild in a lossless archive while keeping space for subsequent experiments. Only the private generated dependency tree is archived; native state, input, output and traces are retained expanded. Global product/runtime trees are untouched.',restore='Extract this task-owned tar archive at the original run directory before replaying its saved native launch.')
 save(run/'dependency-archive.json',record);shutil.rmtree(target)
 return record

def one(unit,family):
 run=R/'runs-install-rebuild'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial fresh-install attempt retained '+str(run))
 run.mkdir(parents=True);state=run/'state';state.mkdir();work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled fresh installation and configuration-repair probe.');(work/'installer_probe.py').write_text("from pathlib import Path\nPath('/workspace/INSTALL_DELIVERED').write_text('NATIVE_TOOL_DELIVERED')\nprint('NATIVE_TOOL_DELIVERED')\n")
 mounts=[]
 if family=='openclaw':
  configuration(family,state);package=run/'installed-openclaw';package.mkdir();mounts=[(package,'/runtime/openclaw',False)];user=R/'runtime/npm-empty-user-config';glob=R/'runtime/npm-empty-global-config';user.write_text('');glob.write_text('');cache=R/'runtime/npm-cache';cache.mkdir(exist_ok=True)
  install_mounts=[*mounts,(user,'/native-config/user',True),(glob,'/native-config/global',True),(cache,'/native-npm-cache',False)];cmd=['/runtime/node-v24.22.1-linux-x64/bin/npm','install','--prefix','/runtime/openclaw','--omit=dev','--foreground-scripts','--no-audit','--no-fund','--userconfig','/native-config/user','--globalconfig','/native-config/global','--cache','/native-npm-cache','openclaw@2026.10.6'];before=[];installed=operator_install(run,family,cmd,install_mounts,'/runtime/openclaw');version=json.loads((package/'node_modules/openclaw/package.json').read_text())['version']
  if version!='2026.10.6':raise RuntimeError('Wrong rebuilt published application release')
  mounts=[(package,'/runtime/openclaw',True)];cfg=state/'openclaw.json'
 else:
  bootstrap=run/'configuration-source';configuration(family,bootstrap);home=state/'hermes';home.mkdir();shutil.copy2(bootstrap/'hermes/config.yaml',home/'config.yaml');source=run/'installed-source';shutil.copytree(R/'runtime/hermes-stable',source,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'));(home/'cache/uv').mkdir(parents=True);save(state/'benchmark-hermes-writable-installs.json',dict(cache=str(R/'runtime/hermes-installer/cache/uv'),scope='Fresh target: no copied app venv or installed application facts; native PM creates them. Machine tool/byte cache only.'));before=list((home/'installs').glob('*/environments/*')) if(home/'installs').exists() else [];mounts=[(source,'/runtime/hermes-source',False)];installed=operator_install(run,family,['python3','-m','pm.cli','install','--extra','all'],mounts,'/runtime/hermes-source');mounts=[(source,'/runtime/hermes-source',True)];cfg=home/'config.yaml';version='v0.22.5/bf0203a';after=list((home/'installs').glob('*/environments/*'))
  if before or not after:raise RuntimeError('Fresh dependency generation was not independently created')
 print('INSTALL_REBUILD_START',unit,family,flush=True);first=delivery(run,family,'native-installed-positive',mounts)
 if not first['passed']:raise RuntimeError('Fresh native installation did not execute the real tool positive')
 good=cfg.read_bytes();save(run/'valid-config-before-fault.json',{'sha256':__import__('hashlib').sha256(good).hexdigest()});cfg.write_text('{"model": [BROKEN_CONFIGURATION')
 check_args=['config','validate','--json'] if family=='openclaw' else ['config','check'];result=subprocess.run(sandbox(state,work,family,cli(family,check_args),extra_mounts=mounts),capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=75);diagnosis=dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr);save(run/'native-bad-configuration-diagnosis.json',diagnosis);cfg.write_bytes(good);repaired=delivery(run,family,'after-restoring-valid-config',mounts);explicit=bool(re.search(r'parse|syntax|yaml|json5|invalid.*config|failed.*config',result.stdout+'\n'+result.stderr,re.I));row=dict(unit=unit,family=family,version=version,application_environment_absent_before_install=True,native_install=installed,native_initial_tool_delivery=first,native_configuration_fault_diagnosed=explicit,native_repaired_tool_delivery=repaired,real_model=False,passed=first['passed'] and repaired['passed'] and explicit,logical_repair_actions=['native configuration diagnosis','restore last-known-valid configuration bytes','native task verifies actual tool delivery'],scope='Three independent empty application install targets per framework. Framework source/artifact pinned; warm machine package/tool cache allowed. No application venv/node_modules copied. Config repair operates on synthetic profile files only. This does not benchmark native latest-channel updater orchestration or cross-OS relocation.');save(run/'result.json',row);print('INSTALL_REBUILD_DONE',unit,family,row['passed'],flush=True)
 if not row['passed']:raise RuntimeError('Fresh install/configuration-repair acceptance needs adjudication')
 row['retained_dependency_archive']=retain_rebuilt_dependencies(run,family);save(run/'result.json',row)
 return row

def main():
 os.chdir(OLD);rows=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):rows.append(one(unit,family));save(R/'results/install-rebuilds.json',rows)
 print('INSTALL_REBUILDS_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
