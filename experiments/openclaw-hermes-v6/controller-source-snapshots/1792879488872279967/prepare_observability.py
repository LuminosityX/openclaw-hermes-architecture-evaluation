"""Prepare official optional addon in task-owned storage, outside measured product runs."""
import base64,hashlib,json,os,subprocess,tarfile,urllib.request,time
from pathlib import Path
from runtime import R,OLD,save
DEST=R/'runtime/diagnostics-otel';META=R/'evidence/diagnostics-addon-registry-metadata.json'
DECODER=R/'runtime/otlp-decoder-venv'
def prepare_decoder():
 marker=DECODER/'PREPARED.json'
 if marker.exists():return
 # Reader dependency is evaluator infrastructure, not a framework capability.
 # Resolve and lock official PyPI metadata BEFORE any observation profile.
 with urllib.request.urlopen('https://pypi.org/pypi/opentelemetry-proto/json',timeout=60) as response:metadata=json.load(response)
 version=metadata['info']['version'];save(R/'evidence/otlp-decoder-pypi-metadata.json',dict(at=time.time(),version=version,requires_dist=metadata['info'].get('requires_dist'),urls=metadata.get('urls',[]),source='https://pypi.org/pypi/opentelemetry-proto/json'))
 result=subprocess.run(['/usr/bin/python3','-m','venv',str(DECODER)],capture_output=True,text=True,timeout=120)
 save(R/'evidence/otlp-decoder-venv-setup.json',dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
 if result.returncode:raise RuntimeError('Trusted evaluator venv setup failed; not product telemetry failure')
 env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE']};home=R/'runtime/otlp-decoder-installer-home';home.mkdir(exist_ok=True);env.update(HOME=str(home),PIP_CONFIG_FILE='/dev/null',PIP_CACHE_DIR=str(R/'runtime/otlp-decoder-pip-cache'))
 cmd=[str(DECODER/'bin/python'),'-m','pip','install','--disable-pip-version-check','--no-input','--index-url','https://pypi.org/simple','--report',str(R/'evidence/otlp-decoder-pip-report.json'),'opentelemetry-proto=='+version]
 with (R/'evidence/otlp-decoder-install.log').open('w') as log:result=subprocess.run(cmd,env=env,stdout=log,stderr=log,timeout=300)
 if result.returncode:raise RuntimeError('Trusted OTLP reader dependencies failed; do not grade a product on undecoded data')
 verify=subprocess.run([str(DECODER/'bin/python'),'-c','from google.protobuf.json_format import MessageToDict; from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest; print(ExportTraceServiceRequest())'],capture_output=True,text=True,timeout=30)
 if verify.returncode:raise RuntimeError('Trusted reader import preflight failed')
 freeze=subprocess.run([str(DECODER/'bin/python'),'-m','pip','freeze'],capture_output=True,text=True,timeout=30)
 save(marker,dict(proto_version=version,requirements=freeze.stdout.splitlines(),pip_report='evidence/otlp-decoder-pip-report.json',scope='Pinned trusted evaluator-only decoder. Does not add dependencies or features to either subject.'))
 print('TRUSTED_OTLP_DECODER_PREPARED',version,flush=True)

H_OBSERVE=R/'evidence/hermes-pm-mutation-preflight/observability-otlp'
def prepare_hermes_observation():
 marker=H_OBSERVE/'PREPARED.json'
 if marker.exists():return
 from runtime import configuration
 from native_hermes_mutation_support import prepare_extra
 H_OBSERVE.mkdir(parents=True,exist_ok=True);configuration('hermes',H_OBSERVE/'state');(H_OBSERVE/'workspace').mkdir(exist_ok=True)
 prepare_extra(H_OBSERVE,'otlp')
 save(marker,dict(scope='Official native Hermes PM otlp extra in one separate operator-owned prepared environment. Current baseline and core source are untouched. Configured E09 profiles share this immutable native dependency generation with private leases; no live lazy install is required.'))
 print('HERMES_OFFICIAL_OTLP_EXTRA_PREPARED',flush=True)

def hermes_observation_mounts(run):
 import shutil
 if not(H_OBSERVE/'PREPARED.json').exists():raise RuntimeError('Official optional Hermes OTLP dependency profile not prepared')
 base=H_OBSERVE/'state/hermes/installs';target=run/'state/hermes/installs';mounts=[]
 for item in base.iterdir():
  if not item.is_dir():continue
  dest=target/item.name;dest.mkdir(parents=True,exist_ok=True)
  for name in ['facts.json','inputs']:
   origin=item/name;out=dest/name
   if origin.is_dir():
    if out.exists():shutil.rmtree(out)
    shutil.copytree(origin,out)
   elif origin.exists():shutil.copy2(origin,out)
  environments=item/'environments'
  if environments.exists():
   mounts.append((environments,f'/state/hermes/installs/{item.name}/environments',True))
   for generation in environments.iterdir():
    if not generation.is_dir():continue
    (generation/'.leases').mkdir(exist_ok=True);lease=run/'state/observation-runtime-leases'/item.name/generation.name;lease.mkdir(parents=True,exist_ok=True);mounts.append((lease,f'/state/hermes/installs/{item.name}/environments/{generation.name}/.leases',False))
 return mounts

def main():
 prepare_decoder()
 prepare_hermes_observation()
 if (DEST/'PREPARED.json').exists():return
 metadata=json.loads(META.read_text())['selected_metadata'];dist=metadata['dist'];archive=R/'runtime/diagnostics-otel-2026.10.6.tgz'
 if not archive.exists():
  with urllib.request.urlopen(dist['tarball'],timeout=60) as response:archive.write_bytes(response.read())
 algorithm,digest=dist['integrity'].split('-',1)
 if algorithm!='sha512' or base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()!=digest:raise RuntimeError('Official npm artifact integrity mismatch')
 if not DEST.exists():
  unpack=R/'runtime/diagnostics-unpack';unpack.mkdir(exist_ok=True)
  with tarfile.open(archive) as tar:tar.extractall(unpack,filter='data')
  (unpack/'package').rename(DEST)
 config=R/'runtime/npm-empty-user-config';config.write_text('');global_config=R/'runtime/npm-empty-global-config';global_config.write_text('')
 node=OLD/'subject-runtime/node-v24.22.1-linux-x64/bin';env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE']};env['PATH']=str(node)+':'+env.get('PATH','/usr/bin:/bin')
 command=[str(node/'npm'),'install','--omit=dev','--ignore-scripts','--legacy-peer-deps','--no-audit','--no-fund','--userconfig',str(config),'--globalconfig',str(global_config),'--cache',str(R/'runtime/npm-cache')]
 with (R/'evidence/diagnostics-addon-install.log').open('w') as log:result=subprocess.run(command,cwd=DEST,env=env,stdout=log,stderr=log,timeout=600)
 save(R/'evidence/diagnostics-addon-install.json',dict(command=command,exit_code=result.returncode,official_version=metadata['version'],archive_sha512=digest))
 if result.returncode:raise RuntimeError('Optional official addon install failed; inspect retained log')
 save(DEST/'PREPARED.json',dict(version=metadata['version'],integrity=dist['integrity'],peer=metadata['peerDependencies'],source=dist['tarball']))
 print('OBSERVABILITY_ADDON_PREPARED',metadata['version'],flush=True)
if __name__=='__main__':main()
