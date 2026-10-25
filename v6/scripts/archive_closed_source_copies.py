"""Release expanded, closed fixture source copies; preserve exact lossless payloads.
Never touches current framework source/runtime, native state, inputs or evidence.
"""
import gzip,hashlib,json,shutil,tarfile,time
from pathlib import Path
from runtime import R,save

def archive(path):
 path=Path(path)
 if not path.exists():return None
 if not path.resolve().is_relative_to(R.resolve()):raise RuntimeError('Not an experiment-owned path')
 out=path.parent/(path.name+'-retained.tar.gz');meta=path.parent/(path.name+'-archive.json')
 if out.exists():raise RuntimeError('Expanded directory and an existing archive both present; inspect before releasing any files')
 tmp=out.with_suffix(out.suffix+'.tmp');count=sum(1 for p in path.rglob('*') if p.is_file());started=time.monotonic()
 with tarfile.open(tmp,'w:gz',compresslevel=1,dereference=False) as tar:tar.add(path,arcname=path.name)
 with tarfile.open(tmp,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    f=tar.extractfile(member)
    while f.read(1048576):pass
 # Explicitly consume the complete gzip stream through its CRC trailer.
 with gzip.open(tmp,'rb') as stream:
  while stream.read(1048576):pass
 with tmp.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 tmp.replace(out);row=dict(at=time.time(),expanded_path=str(path.relative_to(R)),archive=str(out.relative_to(R)),sha256=sha,payload_files=count,bytes=out.stat().st_size,seconds=time.monotonic()-started,restore='Extract the trusted task-owned archive in its parent directory before replaying a saved launch that references this private source/tool copy.',scope='Closed experiment-only duplicate source or unused previous-release tool store. Native state/config/logs and current pinned source/tool/runtime remain unchanged; every archive payload and the entire gzip CRC stream were read back before releasing expanded files.')
 save(meta,row);shutil.rmtree(path);print('CLOSED_COPY_ARCHIVED',row['expanded_path'],row['bytes'],flush=True);return row

def main():
 rows=[]
 for root in [R/'runs-install-rebuild',R/'runs-install-rebuild/state-restore']:
  for case in sorted(root.glob('u*/hermes')):
   p=case/'installed-source'
   if p.exists():
    if not json.loads((case/'result.json').read_text()).get('passed'):raise RuntimeError('Source case not completed')
    rows.append(archive(p))
 for case in sorted((R/'runs-protocols/anthropic').glob('u*/hermes')):
  if(case/'installer-only-source').exists():
   if not json.loads((case/'result.json').read_text()).get('passed'):raise RuntimeError('Protocol case not complete')
   rows.append(archive(case/'installer-only-source'))
 sdk=R/'evidence/hermes-pm-mutation-preflight/observability-otlp'
 if(sdk/'installer-only-source').exists():
  if not(sdk/'PREPARED.json').exists():raise RuntimeError('SDK installer not complete')
  rows.append(archive(sdk/'installer-only-source'))
 if(R/'runtime/hermes-previous-tools').exists():
  old=json.loads((R/'results/upgrades.json').read_text())
  if len(old)!=6 or not all(x['passed'] for x in old):raise RuntimeError('Old tool store still required by unfinished upgrade cases')
  rows.append(archive(R/'runtime/hermes-previous-tools'))
 save(R/'evidence/closed-source-and-old-tool-archives.json',[x for x in rows if x])
 print('CLOSED_COPY_CAPACITY_RESTORED',shutil.disk_usage(R).free,flush=True)
if __name__=='__main__':main()
