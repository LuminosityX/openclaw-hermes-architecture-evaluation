"""Prepare official optional addon in task-owned storage, outside measured product runs."""
import base64,hashlib,json,os,subprocess,tarfile,urllib.request
from pathlib import Path
from runtime import R,OLD,save
DEST=R/'runtime/diagnostics-otel';META=R/'evidence/diagnostics-addon-registry-metadata.json'
def main():
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
