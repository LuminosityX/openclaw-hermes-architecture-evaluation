"""Lossless archival of completed fixture-only private dependency generations.
Never touches active profiles, global runtime or native evidence/state/config.
"""
import hashlib,json,shutil,tarfile,time
from runtime import R,save

def one(run):
 result=json.loads((run/'result.json').read_text())
 valid=result.get('passed') is True or all(result.get(k) is True for k in ['tool_contract','hook_contract','context_contract','update_contract','disable_contract','uninstall_contract'])
 if not valid:raise RuntimeError('Only completed positive fixtures may be archived')
 root=run/'state/hermes/installs';targets=[x for x in root.glob('*/environments') if any(x.iterdir())]
 if not targets:return json.loads((run/'dependency-archive.json').read_text()) if (run/'dependency-archive.json').exists() else None
 archive=run/'completed-private-dependency-environments.tar.gz';record=run/'dependency-archive.json'
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
  for target in targets:tar.add(target,arcname=str(target.relative_to(run)),recursive=True)
 count=0
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    f=tar.extractfile(member)
    while f.read(1024*1024):pass
    count+=1
 row=dict(at=time.time(),archive=str(archive.relative_to(run)),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),payload_files=count,relative_paths=[str(x.relative_to(run)) for x in targets],reason='Completed protocol/native-extension fixture dependencies only. Full lossless payload archive read back including gzip CRC before releasing expanded copies. Native facts/config/history/receipts/source and global runtimes untouched. No benchmark running during archival.',restore='Extract this task-owned tar archive in its original run directory before replaying saved launches.')
 save(record,row)
 for target in targets:shutil.rmtree(target);target.mkdir()
 print('DEPENDENCY_ARCHIVED',str(run.relative_to(R)),count,archive.stat().st_size,flush=True)
 return row

def previous_runtime():
 upgrades=json.loads((R/'results/upgrades.json').read_text())
 if len(upgrades)!=6 or not all(x['passed'] for x in upgrades):raise RuntimeError('Previous releases still required by incomplete actual upgrade experiments')
 target=R/'runtime/openclaw-previous/node_modules';archive=R/'runtime/openclaw-previous-dependencies.tar.gz';meta=R/'runtime/openclaw-previous-dependency-archive.json'
 if not target.exists():return json.loads(meta.read_text()) if meta.exists() else None
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:tar.add(target,arcname='node_modules',recursive=True)
 count=0
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    f=tar.extractfile(member)
    while f.read(1024*1024):pass
    count+=1
 row=dict(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),expanded_target=str(target),payload_files=count,restore='Extract in runtime/openclaw-previous before replaying earlier-release launches.',scope='Only the fully completed OLD OpenClaw10.5 fixture release. Current10.6 and all native state/evidence are untouched; exact payload retained losslessly. No product benchmark active during archival.')
 save(meta,row);shutil.rmtree(target);print('OLD_OC_RUNTIME_ARCHIVED',count,archive.stat().st_size,flush=True);return row

def main():
 rows=[]
 for unit in range(1,4):
  row=one(R/'runs-protocols/anthropic'/f'u{unit}'/'hermes')
  if row:rows.append(row)
 # Additional completed mutable extension generations are no longer executed.
 for unit in range(1,4):
  run=R/'runs-extensions'/f'u{unit}'/'hermes'
  if (run/'result.json').exists():
   row=one(run)
   if row:rows.append(row)
 old=previous_runtime()
 if old:rows.append(old)
 save(R/'evidence/completed-dependency-archives.json',rows)
if __name__=='__main__':main()
