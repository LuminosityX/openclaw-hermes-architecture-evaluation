"""Locked previous official releases and native dependency installations, prepared outside timing runs."""
import base64,hashlib,json,os,subprocess,tarfile,urllib.request
from pathlib import Path
from runtime import R,OLD,save
OC=R/'runtime/openclaw-previous';HS=R/'runtime/hermes-previous';HI=R/'runtime/hermes-previous-installer';HT=R/'runtime/hermes-previous-tools'
H_COMMIT='4d04303818b61bf3aa09278af48356315515965b'
def public_get(url):
 with urllib.request.urlopen(url,timeout=120) as r:return r.read()
def prepare_oc_lifecycle():
 marker=OC/'LIFECYCLE-PREPARED.json'
 if marker.exists():return
 node=OLD/'subject-runtime/node-v24.22.1-linux-x64';cache=R/'runtime/npm-cache';cache.mkdir(exist_ok=True);user=R/'runtime/npm-empty-user-config';global_config=R/'runtime/npm-empty-global-config';user.write_text('');global_config.write_text('')
 env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE']}
 args=['bwrap','--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts','--die-with-parent','--cap-drop','ALL','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/root','--bind',str(OC),'/runtime/openclaw','--ro-bind',str(node),'/node','--bind',str(cache),'/npm-cache','--ro-bind',str(user),'/config/user','--ro-bind',str(global_config),'/config/global','--setenv','HOME','/root','--setenv','PATH','/node/bin:/usr/bin:/bin','--setenv','npm_lifecycle_event','postinstall','--setenv','NPM_CONFIG_USERCONFIG','/config/user','--setenv','NPM_CONFIG_GLOBALCONFIG','/config/global','--setenv','NPM_CONFIG_CACHE','/npm-cache','--chdir','/runtime/openclaw/node_modules/openclaw']
 for path in ['/etc/resolv.conf','/etc/hosts','/etc/ssl/certs','/etc/passwd','/etc/group']:
  if Path(path).exists():args+=['--ro-bind',path,path]
 for key in ['SSL_CERT_FILE','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE']:
  path=env.get(key)
  if path and Path(path).is_file() and not path.startswith('/usr/'):args+=['--ro-bind',path,path]
 args+=['--','node','scripts/postinstall-bundled-plugins.mjs']
 with (R/'evidence/openclaw-previous-lifecycle.log').open('a') as log:p=subprocess.run(args,env=env,stdout=log,stderr=log,timeout=900)
 save(R/'evidence/openclaw-previous-lifecycle.json',dict(exit_code=p.returncode,command=args,scope='Official published package postinstall, installer-only network, isolated temporary HOME and previous package prefix; no operator credentials or current framework mounted.'))
 if p.returncode:raise RuntimeError('Official previous-package lifecycle setup failed')
 version=json.loads((OC/'node_modules/openclaw/package.json').read_text())['version']
 if version!='2026.10.5':raise RuntimeError('Native lifecycle changed the pinned release')
 save(marker,dict(version=version,official_postinstall=True,entry='scripts/postinstall-bundled-plugins.mjs'))
def prepare_oc():
 if (OC/'PREPARED.json').exists():prepare_oc_lifecycle();return
 meta=json.loads(public_get('https://registry.npmjs.org/openclaw/2026.10.5'));save(R/'evidence/openclaw-previous-npm-metadata.json',meta)
 if meta.get('version')!='2026.10.5':raise RuntimeError('Wrong previous OC version')
 OC.mkdir(exist_ok=True);config=R/'runtime/npm-empty-user-config';config.write_text('');global_config=R/'runtime/npm-empty-global-config';global_config.write_text('');node=OLD/'subject-runtime/node-v24.22.1-linux-x64/bin';env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS']};env['PATH']=str(node)+':'+env.get('PATH','/usr/bin:/bin')
 cmd=[str(node/'npm'),'install','--prefix',str(OC),'--omit=dev','--ignore-scripts','--no-audit','--no-fund','--userconfig',str(config),'--globalconfig',str(global_config),'--cache',str(R/'runtime/npm-cache'),'openclaw@2026.10.5']
 with (R/'evidence/openclaw-previous-install.log').open('w') as out:p=subprocess.run(cmd,env=env,stdout=out,stderr=out,timeout=900)
 save(R/'evidence/openclaw-previous-install.json',dict(command=cmd,exit_code=p.returncode,version=meta['version'],gitHead=meta.get('gitHead'),integrity=meta.get('dist',{}).get('integrity')))
 if p.returncode:raise RuntimeError('Previous published OC install failed')
 prepare_oc_lifecycle();save(OC/'PREPARED.json',dict(version=meta['version'],gitHead=meta.get('gitHead'),dist=meta['dist']))
def prepare_h():
 if (HI/'PREPARED.json').exists():return
 archive=R/'runtime/hermes-v0.22.4.tar.gz';url='https://codeload.github.com/NousResearch/hermes-agent/tar.gz/'+H_COMMIT
 if not archive.exists():archive.write_bytes(public_get(url))
 if not HS.exists():
  staging=R/'runtime/hermes-previous-unpack';staging.mkdir(exist_ok=True)
  with tarfile.open(archive) as tar:tar.extractall(staging,filter='data')
  dirs=list(staging.iterdir())
  if len(dirs)!=1:raise RuntimeError('Unexpected official source archive layout')
  dirs[0].rename(HS)
 home=HI/'hermes';home.mkdir(parents=True,exist_ok=True);node=OLD/'subject-runtime/node-v24.22.1-linux-x64'
 cmd=['bwrap','--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts','--die-with-parent','--cap-drop','ALL','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/root','--bind',str(HS),'/runtime/hermes-source','--bind',str(HT),'/runtime/hermes-tools','--bind',str(home),'/runtime/installer-state/hermes','--ro-bind',str(node),'/runtime/node','--chdir','/runtime/hermes-source','--setenv','PATH','/runtime/node/bin:/usr/bin:/bin','--setenv','HERMES_HOME','/runtime/installer-state/hermes','--setenv','HERMES_RUNTIME_DIR','/runtime/hermes-tools']
 for path in ['/etc/resolv.conf','/etc/hosts','/etc/ssl/certs','/etc/passwd','/etc/group']:
  if Path(path).exists():cmd+=['--ro-bind',path,path]
 cmd+=['--','python3','-m','pm.cli','install','--without','agent-browser','--without','cua-driver']
 env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS','REQUESTS_CA_BUNDLE','PIP_INDEX_URL','UV_INDEX_URL','UV_DEFAULT_INDEX','PIP_EXTRA_INDEX_URL']}
 with (R/'evidence/hermes-previous-install.log').open('w') as out:p=subprocess.run(cmd,env=env,stdout=out,stderr=out,timeout=900)
 save(R/'evidence/hermes-previous-install.json',dict(exit_code=p.returncode,command_without_credential_environment=cmd,source_commit=H_COMMIT,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),network='Installer-only network with inherited proxy/CA; no user home or service credentials mounted. No agent or inference.'))
 if p.returncode:raise RuntimeError('Previous Hermes official PM install failed')
 save(HI/'PREPARED.json',dict(version='0.22.4',source_commit=H_COMMIT,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
def main():
 prepare_oc();prepare_h();print('LOCKED_UPGRADE_RUNTIMES_PREPARED',flush=True)
if __name__=='__main__':main()
