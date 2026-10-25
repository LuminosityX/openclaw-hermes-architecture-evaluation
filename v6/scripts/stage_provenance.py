"""Capture late-loaded controlled substages, without retroactive source claims."""
import hashlib,os,shutil,time
from runtime import R,save

def snapshot(name):
 parent=os.environ.get('BENCHMARK_CONTROLLER_SOURCE_SNAPSHOT');dest=R/'evidence/controller-source-snapshots'/(str(time.time_ns())+'-'+name);dest.mkdir(parents=True);hashes={}
 for p in (R/'scripts').iterdir():
  if p.is_file() and p.suffix in ['.py','.mjs','.js','.c']:shutil.copy2(p,dest/p.name);hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
 save(dest/'manifest.json',dict(stage_invocation=name,parent_invocation_snapshot=parent,source_hashes=hashes,scope='Actual source at this late-loaded substage invocation. No retroactive claim that cached earlier native cases used newer controller code.'))
 os.environ['BENCHMARK_CONTROLLER_SOURCE_SNAPSHOT']=str(dest);return dest
