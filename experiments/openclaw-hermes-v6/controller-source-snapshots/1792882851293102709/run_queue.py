"""Sequential continuation of explicitly authorized experiments. Never overlaps subjects."""
import argparse,json,os,subprocess,time,shutil,hashlib
from pathlib import Path
from runtime import R,save
p=argparse.ArgumentParser();p.add_argument('--after-pid',type=int,required=True);a=p.parse_args()
while Path('/proc/'+str(a.after_pid)+'/cmdline').exists():
 try:
  cmd=Path('/proc/'+str(a.after_pid)+'/cmdline').read_bytes()
  if b'run_formal.py' not in cmd:break
 except OSError:break
 time.sleep(1)
path=R/'results/formal-task-results.json';results=json.loads(path.read_text()) if path.exists() else []
if len(results)!=48:raise RuntimeError('Formal batch did not complete; inspect retained run before proceeding')
steps=json.loads((R/'evidence/authorized-execution-queue.json').read_text())['scripts']
for step in steps:
 stamp=str(time.time_ns());snapshot=R/'evidence/controller-source-snapshots'/stamp;snapshot.mkdir(parents=True);hashes={}
 for source in (R/'scripts').iterdir():
  if source.is_file() and source.suffix in ['.py','.mjs','.js','.c']:
   shutil.copy2(source,snapshot/source.name);hashes[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
 save(snapshot/'manifest.json',dict(stage_invocation=step,source_hashes=hashes,scope='Exact controller source at this stage invocation. Cached prior results retain their earlier native evidence; this snapshot is not retroactive provenance for cached cases.'))
 save(R/'evidence/queue-active.json',dict(script=step,status='running',at=time.time(),controller_invocation_snapshot=str(snapshot)));print('QUEUE_START',step,flush=True)
 log=R/'evidence'/('queue-'+step+'.log')
 with log.open('a') as f:r=subprocess.run(['/usr/bin/python3',str(R/'scripts'/step)],stdout=f,stderr=f,env={**os.environ,'BENCHMARK_CONTROLLER_SOURCE_SNAPSHOT':str(snapshot)})
 save(R/'evidence/queue-active.json',dict(script=step,status='complete' if r.returncode==0 else 'requires_harness_review',exit_code=r.returncode,at=time.time(),controller_invocation_snapshot=str(snapshot)));print('QUEUE_DONE',step,r.returncode,flush=True)
 if r.returncode:raise RuntimeError('Preserved attempt needs inspection: '+str(log))
print('QUEUE_COMPLETE',flush=True)
