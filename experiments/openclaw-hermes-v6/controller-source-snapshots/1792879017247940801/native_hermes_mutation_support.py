"""Operator-fixture support for native dependency admission, not product changes.
Normal task runs use immutable prepared runtimes. Plugin mutation needs a private
writable install store and the already-prepared native machine package cache.
"""
import json,shutil,subprocess,hashlib
from pathlib import Path
from runtime import R,save

def prepare(run,installer=None):
 run=Path(run);state=run/'state'
 if not state.resolve().is_relative_to(R):raise ValueError('Mutation store must be owned by this experiment')
 marker=state/'benchmark-hermes-writable-installs.json'
 if marker.exists():return
 installer=Path(installer or R/'runtime/hermes-installer');rows=[]
 for source in (installer/'installs').iterdir():
  target=state/'hermes/installs'/source.name;target.mkdir(parents=True,exist_ok=True)
  for name in ['environments','pm-runtime']:
   if not(source/name).is_dir():continue
   destination=target/name;destination.mkdir(exist_ok=True)
   result=subprocess.run(['cp','-a','--reflink=auto',str(source/name)+'/.' ,str(destination)],capture_output=True,text=True,timeout=180)
   if result.returncode:raise RuntimeError('Private native install-store copy failed: '+result.stderr[:500])
   # Runtime leases belong to the original installation's live processes, not
   # the cloned dependency fixture; each native process takes its own lease.
   for directory in destination.rglob('.leases'):
    if directory.is_dir() and not directory.is_symlink():shutil.rmtree(directory);directory.mkdir()
  rows.append(dict(install_id=source.name,source=str(source),facts_sha256=hashlib.sha256((source/'facts.json').read_bytes()).hexdigest()))
 (state/'hermes/cache/uv').mkdir(parents=True,exist_ok=True)
 save(marker,dict(installer=str(installer),cache=str(installer/'cache/uv'),installs=rows,scope='Private cloned native dependency generations and native PM bootstrap runtime; writable per-profile generations, task-owned shared warm uv cache. No source edits or dependency-admission bypass; package downloads are not required from the offline agent namespace.'))

def prepare_extra(run,extra):
 """Run official optional-feature installation before an offline contract test.
 Installer has network but no agent, original HOME or current writable core.
 """
 import os
 from runtime import sandbox
 from run_state_ops import cli
 run=Path(run);marker=run/('native-extra-'+extra+'-prepared.json')
 if marker.exists():return
 prepare(run);source=run/'installer-only-source'
 if not source.exists():shutil.copytree(R/'runtime/hermes-stable',source,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
 command=cli('hermes',['pm','install','--extra',extra,'--without','agent-browser','--without','cua-driver']);normal=sandbox(run/'state',run/'workspace','hermes',command,extra_mounts=[(source,'/runtime/hermes-source',False)]);at=normal.index('--');prefix=[]
 for arg in normal[:at]:
  if arg=='--unshare-all':prefix+=['--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts']
  else:prefix.append(arg)
 for path in ['/etc/resolv.conf','/etc/hosts']:
  if Path(path).exists():prefix+=['--ro-bind',path,path]
 env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE','PIP_INDEX_URL','UV_INDEX_URL','UV_DEFAULT_INDEX','PIP_EXTRA_INDEX_URL']}
 for name in ['SSL_CERT_FILE','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE']:
  path=env.get(name)
  if path and Path(path).is_file() and not path.startswith('/usr/'):prefix+=['--ro-bind',path,path]
 args=prefix+['--']+command
 with (run/('native-extra-'+extra+'-install.log')).open('a') as log:result=subprocess.run(args,env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,timeout=600)
 row=dict(extra=extra,exit_code=result.returncode,command=args,scope='Official hermes pm install --extra in installer-only network namespace. Native app/code copy, dependency state and package cache are experiment-owned; no agent or real credentials. Actual protocol runs remain offline with the original pinned core source.')
 save(run/('native-extra-'+extra+'-install.json'),row)
 if result.returncode:raise RuntimeError('Official optional SDK preparation failed: '+extra)
 save(marker,row)
