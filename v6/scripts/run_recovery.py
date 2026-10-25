"""Gateway owner/client failures with exact tool trigger and independent effect ledger."""
import concurrent.futures,http.client,json,os,signal,socket,time
from pathlib import Path
from runtime import R,OLD,configuration,save
from gateway import Gateway,Control
from controlled import Plan,shell

def descendants(root):
 out=[];todo=[root]
 while todo:
  pid=todo.pop();out.append(pid)
  try:todo+=list(map(int,Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
  except OSError:pass
 return out

def stop_owner(gateway):
 if not gateway.persistent_namespace:raise RuntimeError('Owner-only fault requires a persistent evaluator namespace')
 identity=gateway.owner_status()
 listeners=identity.get('listening_owner_pids',[])
 if len(listeners)!=1 or listeners[0] not in identity.get('owned_descendant_pids',[]):raise RuntimeError('Native listening owner is not one precisely identified product descendant; refuse an ambiguous signal')
 actual_owner=listeners[0]
 before=gateway.owner_signal(signal.SIGKILL,pid=actual_owner);until=time.monotonic()+8
 while time.monotonic()<until:
  after=gateway.owner_status()
  dead=after.get('last_signalled_pid')==actual_owner and after.get('last_signalled_pid_alive') is False
  launcher_reaped=after.get('owner_returncode') is not None
  if dead and (actual_owner!=identity.get('owner_pid') or launcher_reaped):break
  time.sleep(.05)
 else:raise RuntimeError('Exact owner kill was not confirmed')
 save(gateway.run/'owner-fault.json',dict(before=before,after=after,signal='SIGKILL',target_pid=actual_owner,foreground_launcher_pid=identity.get('owner_pid'),namespace_preserved=gateway.process.poll() is None,scope='Only the verified listening native service PID was killed, which may be a foreground launcher child. Namespace supervisor and pre-existing tool processes remain until the experiment ends; no whole-process-group kill is used.'))
 return before

def run_case(kind,unit,family):
 run=R/'runs-recovery'/kind/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial recovery attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled gateway fault and recovery probe.')
 (work/'slow.py').write_text("from pathlib import Path\nimport time\nPath('/workspace/STARTED').write_text('actual tool started')\ntime.sleep(4)\nwith Path('/workspace/effects.jsonl').open('a') as f:f.write('COMMIT\\n')\nprint('COMMITTED')\n")
 (work/'finish.py').write_text("from pathlib import Path\np=Path('/workspace/effects.jsonl')\nrows=p.read_text().splitlines() if p.exists() else []\nif not rows:\n with p.open('a') as f:f.write('COMMIT\\n')\nPath('/workspace/FINISHED').write_text('receipt checked and committed exactly once')\nprint('FINISHED')\n")
 fixture=Plan(run,family,[shell('python3 /workspace/slow.py'),shell('python3 /workspace/finish.py')]);gateway=Gateway(run,family,fixture,persistent_namespace=(kind=='R07-owner-crash'));session='recover-'+kind+'-'+str(unit);rec=dict(kind=kind,unit=unit,family=family,real_model=False);conn=None;response=None
 print('RECOVERY_START',kind,unit,family,flush=True)
 try:
  gateway.start();conn=Control(run/'state/control.sock',90);headers={'Content-Type':'application/json','Authorization':'Bearer synthetic-evaluation-token'}
  if family=='hermes':headers.update({'X-Hermes-Session-Key':session,'X-Hermes-Session-Id':gateway.native_session_id(session)})
  else:headers['x-openclaw-session-key']=gateway.native_session_key(session)
  body={'model':'openclaw' if family=='openclaw' else 'deepseek-flash','messages':[{'role':'user','content':'Run controlled work '+session}],'user':session,'stream':True};conn.request('POST','/v1/chat/completions',json.dumps(body),headers);response=conn.getresponse();rec['initial_status']=response.status;rec['initial_headers']=dict(response.getheaders())
  until=time.monotonic()+30
  while not (work/'STARTED').exists() and time.monotonic()<until:time.sleep(.05)
  rec['trigger_reached']=(work/'STARTED').exists()
  if not rec['trigger_reached']:raise RuntimeError('Tool did not start; cannot inject a meaningful fault')
  trigger=time.monotonic()
  if kind=='R06-client-disconnect':
   conn.close();conn=None
  elif kind=='R07-owner-crash':
   stop_owner(gateway);gateway.restart_owner();trigger=gateway.ready
  else:raise RuntimeError('Unknown recovery case')
  until=trigger+30
  while not (work/'FINISHED').exists() and time.monotonic()<until:time.sleep(.1)
  rec['automatic_finish_marker']=(work/'FINISHED').exists();rec['effect_count_before_status']=len((work/'effects.jsonl').read_text().splitlines()) if (work/'effects.jsonl').exists() else 0;rec['automatically_finished']=rec['automatic_finish_marker'] and rec['effect_count_before_status']==1;rec['recovery_observation_seconds']=time.monotonic()-trigger
  # One explicitly authorized resume on the canonical same-session entry;
  # the plan may reconcile a receipt and finish, so it must not be called read-only.
  try:rec['same_session_probe']=gateway.chat('Resume the previous interrupted task. Check its persisted receipt first; complete the authorized remaining work only if needed, without duplicate commits.',session,timeout=35)
  except Exception as ex:rec['same_session_probe']={'error':type(ex).__name__}
  rec['finished_after_one_status_turn_marker']=(work/'FINISHED').exists();rec['effect_count']=len((work/'effects.jsonl').read_text().splitlines()) if (work/'effects.jsonl').exists() else 0
  rec['finished_after_one_status_turn']=rec['finished_after_one_status_turn_marker'] and rec['effect_count']==1
  rec['last_model_context_has_original_task']=any(('Run controlled work '+session) in str(m.get('content','')) for call in fixture.calls if call['main'] for m in call['request'].get('messages',[]))
  rec['application_reconciliation_scope']='The continuation queries a persisted application receipt and commits only if absent; no generic exactly-once claim. R05 separately probes non-idempotent lost acknowledgement.'
  rec['intervention_scope']='After the automatic window, one explicitly authorized same-session resume turn; this turn is not a read-only status query.'
  rec['automatic_provider_calls_after_fault']=sum(x['time_ns']/1e9>trigger for x in fixture.calls if x['main']);rec['service_survived']=gateway.owner_alive()
  # Keep raw statuses; safe unknown is not a false completion and not an execution replay.
  rec['classification']='automatic_resume' if rec['automatically_finished'] else 'status_turn_resume' if rec['finished_after_one_status_turn'] else 'requires_adjudication';save(run/'result.json',rec);print('RECOVERY_DONE',kind,unit,family,rec['classification'],rec['effect_count'],flush=True);return rec
 finally:
  if conn:conn.close()
  gateway.stop();fixture.close()

def main():
 from run_readonly_fuzz import main as readonly_native_dispatch
 readonly_native_dispatch()
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for kind in ['R06-client-disconnect','R07-owner-crash']:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(kind,unit,family));save(R/'results/recovery-gateway.json',results)
 print('GATEWAY_RECOVERY_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
