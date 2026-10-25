"""Native explicit task cancellation, foreground parent+child, independent neighboring session."""
import concurrent.futures,json,os,time
from pathlib import Path
from runtime import R,OLD,configuration,save
from controlled import Plan,shell
from gateway import Gateway
from run_approvals import oc_cli
from run_recovery import descendants
SLOW=r'''
import os,subprocess,sys,time
from pathlib import Path
root=Path('/workspace')
child=subprocess.Popen([sys.executable,'-c',"import time;from pathlib import Path\np=Path('/workspace/child.beat')\nfor i in range(100):p.write_text(str(i));time.sleep(.2)\nPath('/workspace/CHILD_LATE_EFFECT').write_text('late')"])
(root/'STARTED.json').write_text(__import__('json').dumps({'parent':os.getpid(),'child':child.pid,'pid_namespace':os.readlink('/proc/self/ns/pid')}))
for i in range(100):(root/'parent.beat').write_text(str(i));time.sleep(.2)
(root/'PARENT_LATE_EFFECT').write_text('late');child.wait()
'''
def beats(work):return {name:(work/name).read_text() if (work/name).exists() else None for name in ['parent.beat','child.beat']}
def remaining_processes(gateway,identity):
 observed=[]
 for pid in descendants(gateway.process.pid):
  try:
   status=Path(f'/proc/{pid}/status').read_text();line=next((x for x in status.splitlines() if x.startswith('NSpid:')),None)
   if line is None or os.readlink(f'/proc/{pid}/ns/pid')!=identity['pid_namespace']:continue
   native_pid=int(line.split()[-1])
   if native_pid not in [identity['parent'],identity['child']]:continue
   stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();observed.append(dict(host_pid=pid,native_pid=native_pid,state=stat[0],alive=stat[0]!='Z'))
  except (OSError,ValueError,IndexError):pass
 return observed
def run_case(unit,family):
 run=R/'runs-cancel'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial cancel attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled native foreground cancellation test.');(work/'slow.py').write_text(SLOW)
 fixture=Plan(run,family,[shell('python3 /workspace/slow.py',background=False)]);gateway=Gateway(run,family,fixture);pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);session='cancel-u'+str(unit)
 print('CANCEL_START',unit,family,flush=True)
 try:
  gateway.start()
  if family=='openclaw':future=pool.submit(gateway.chat,'Run the controlled foreground task. It is ordinary nonpersistent work.',session,timeout=90);run_id=None
  else:
   status,h,raw=gateway.raw('POST','/v1/runs',{'input':'Run the controlled foreground task. It is ordinary nonpersistent work.','model':'deepseek-flash'},headers={'X-Hermes-Session-Key':session});body=json.loads(raw);save(run/'run-start.json',dict(status=status,response=body));run_id=body.get('run_id')
   if status!=202 or not run_id:raise RuntimeError('Native async task admission failed')
  until=time.monotonic()+30
  while not(work/'STARTED.json').exists() and time.monotonic()<until:time.sleep(.05)
  if not(work/'STARTED.json').exists():raise RuntimeError('Foreground parent and child did not start; cannot meaningfully cancel')
  started=time.monotonic();before=beats(work)
  if family=='openclaw':stop=oc_cli(gateway,['gateway','call','chat.abort','--params',json.dumps({'sessionKey':gateway.native_session_key(session)}),'--json'],'native-stop')
  else:
   status,h,raw=gateway.raw('POST','/v1/runs/'+run_id+'/stop',{});stop=dict(status=status,body=raw.decode());save(run/'native-stop.json',stop)
  samples=[];status_rows=[]
  for index in range(15):
   samples.append(dict(seconds=time.monotonic()-started,beats=beats(work)))
   if family=='hermes' and index%3==0:
    code,h,raw=gateway.raw('GET','/v1/runs/'+run_id,timeout=5);status_rows.append(dict(seconds=time.monotonic()-started,status=code,response=json.loads(raw)))
   time.sleep(.2)
  neighbor=gateway.chat('Return a short controlled response in a different independent session.','cancel-neighbor-'+str(unit),timeout=20);after=beats(work);time.sleep(.5);later=beats(work)
  foreground_result={}
  if family=='openclaw':
   try:foreground_result=future.result(timeout=5)
   except Exception as ex:foreground_result={'error':type(ex).__name__}
  identity=json.loads((work/'STARTED.json').read_text());remaining=remaining_processes(gateway,identity)
  rec=dict(unit=unit,family=family,stop_response=stop,foreground_result=foreground_result,foregound_started=identity,beats_before=before,beat_samples=samples,status_observations=status_rows,beats_after_neighbor=after,beats_later=later,nonpersistent_effects_stopped=after==later,remaining_foreground_processes=remaining,nonpersistent_processes_stopped=not any(x['alive'] for x in remaining),namespace_alive_during_observation=gateway.process.poll() is None,late_effects=(work/'PARENT_LATE_EFFECT').exists() or (work/'CHILD_LATE_EFFECT').exists(),neighbor_healthy=neighbor.get('status')==200 and 'CONTROLLED_COMPLETE' in json.dumps(neighbor.get('response',{})),scope='Foreground background=false; namespace/service remains live during observations. A stop request acknowledgment is distinguished from terminal cancellation. Remaining parent/child are matched by native PID plus PID namespace inside the owned host process subtree. Final namespace cleanup does not count as product cancellation.')
  save(run/'result.json',rec);print('CANCEL_DONE',unit,family,rec['nonpersistent_effects_stopped'],rec['neighbor_healthy'],flush=True);return rec
 finally:gateway.stop();fixture.close();pool.shutdown(wait=False,cancel_futures=True)
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,family));save(R/'results/cancellation.json',results)
 print('CANCELLATION_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
