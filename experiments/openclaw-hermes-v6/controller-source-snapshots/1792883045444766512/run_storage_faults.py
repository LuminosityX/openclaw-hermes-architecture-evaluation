"""Real SQLite EIO during live native admission plus recovery from controlled state corruption."""
import concurrent.futures,hashlib,json,os,shutil,sqlite3,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save,read_config
from controlled import Plan,shell
from gateway import Gateway
from run_state_ops import cli,portable_call,cron_list_step,disabled_job_in
from run_upgrades import restore
from inspect_native_state import decision_records
LIB=R/'runtime/sqlite-fault.so'

def prepare_shim():
 if LIB.exists():return
 source=Path(__file__).parent/'sqlite_fault.c';p=subprocess.run(['cc','-shared','-fPIC','-O2',str(source),'-ldl','-o',str(LIB)],capture_output=True,text=True);save(R/'evidence/storage-fault-compiler.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
 if p.returncode:raise RuntimeError('Fault injector compilation failed')

def seed_copy(run,unit,family):
 source=R/'runs-state-ops'/f'u{unit}'/family/'source'
 if not(source/'state-before.json').exists():raise RuntimeError('Valid native source state must exist first')
 shutil.copytree(source/'state',run/'state',ignore=shutil.ignore_patterns('*.sock'),symlinks=True);shutil.copytree(source/'workspace',run/'workspace',symlinks=True);(run/'workspace/PROMPT.md').write_text('Controlled native storage boundary test.')
 if family=='openclaw':
  config=run/'state/openclaw.json';value=read_config(config);value.setdefault('cron',{})['enabled']=False;save(config,value)
 return source

def canonical_files(run,family):
 if family=='hermes':return [run/'state/hermes/state.db']
 return [run/'state/openclaw/agents/main/agent/openclaw-agent.sqlite',run/'state/openclaw/state/openclaw.sqlite']
def live_has(run,family,token):
 for p in canonical_files(run,family):
  if not p.exists():continue
  try:
   c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
   for table, in c.execute("select name from sqlite_master where type='table' and name not like '%fts%'"):
    quote='"'+table.replace('"','""')+'"'
    if any(token in str(row) for row in c.execute('SELECT * FROM '+quote)):
     c.close();return True
   c.close()
  except sqlite3.Error:pass
 return False

def completed(response):
 return response.get('status')==200 and 'CONTROLLED_COMPLETE' in json.dumps(response.get('response',{})) and not response.get('response',{}).get('error')

def native_eio(unit,family):
 """Primary R10: native acknowledged background admission, not HTTP completion
 compatibility behavior. No product CLI runs under the injected SQLite error.
 """
 import uuid
 from native_operator_client import Operator
 run=R/'runs-storage-faults/native-EIO'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial native-admission EIO attempt retained '+str(run))
 run.mkdir(parents=True);seed_copy(run,unit,family);control=run/'fault-control';events=run/'fault-events';control.mkdir();events.mkdir();fixture=Plan(run,family,[])
 gateway=Gateway(run,family,fixture,extra_mounts=[(LIB,'/sqlite-fault.so',True),(control,'/fault-control',True),(events,'/fault-events',False)])
 at=gateway.command.index('--');gateway.command=gateway.command[:at]+['--setenv','LD_PRELOAD','/sqlite-fault.so']+gateway.command[at:];operator=None
 def submit(token,label):
  if family=='openclaw':
   body=operator.rpc('chat.send',{'sessionKey':'agent:main:main','message':token,'idempotencyKey':uuid.uuid4().hex,'deliver':False},label+'-admission');run_id=body.get('runId');ack=bool(run_id);terminal={};until=time.monotonic()+12
   while ack and time.monotonic()<until:
    terminal=operator.rpc('agent.wait',{'runId':run_id,'timeoutMs':1000},label+'-status')
    if terminal.get('status') not in ['pending','timeout']:break
   return dict(acknowledged=ack,native_admission=body,native_terminal=terminal,completed=terminal.get('status')=='ok',native_run_id=run_id)
  code,_,raw=gateway.raw('POST','/v1/runs',{'model':'deepseek-flash','input':token},headers={'X-Hermes-Session-Key':label+'-u'+str(unit)},timeout=15)
  body=json.loads(raw);run_id=body.get('run_id');ack=code==202 and bool(run_id);terminal={};until=time.monotonic()+12
  while ack and time.monotonic()<until:
   _,_,raw=gateway.raw('GET','/v1/runs/'+run_id,timeout=5);terminal=json.loads(raw)
   if terminal.get('status') in ['completed','failed','unknown','cancelled','interrupted']:break
   time.sleep(.1)
  return dict(acknowledged=ack,http_status=code,native_admission=body,native_terminal=terminal,completed=terminal.get('status')=='completed',native_run_id=run_id)
 before='R10_NATIVE_PREFLIGHT_U'+str(unit);attempt='R10_NATIVE_FAULT_U'+str(unit);recovered='R10_NATIVE_RECOVERED_U'+str(unit)
 print('STORAGE_NATIVE_EIO_START',unit,family,flush=True)
 try:
  gateway.start()
  if family=='openclaw':operator=Operator(gateway).start()
  baseline=submit(before,'native-eio-positive');save(run/'native-positive.json',baseline)
  if not baseline['acknowledged'] or not baseline['completed'] or not live_has(run,family,before):raise RuntimeError('Native durable-admission positive control failed before storage fault')
  (control/'ENABLED').write_text('Controlled SQLite EIO after native positive control')
  try:response=submit(attempt,'native-eio-fault')
  except Exception as ex:response=dict(acknowledged=None,error=type(ex).__name__,detail=str(ex)[:1500])
  rows=[json.loads(x) for x in (events/'events.jsonl').read_text().splitlines()] if (events/'events.jsonl').exists() else [];during=dict(response=response,user_turn_in_active_store=live_has(run,family,attempt),injected_failures=rows);save(run/'during-failure.json',during);(control/'ENABLED').unlink(missing_ok=True)
  restarts=0
  try:after=submit(recovered,'native-eio-recovered')
  except Exception as ex:after=dict(acknowledged=None,error=type(ex).__name__)
  if not after.get('completed'):
   if operator:operator.stop()
   gateway.stop();gateway.start();restarts+=1
   if family=='openclaw':operator=Operator(gateway).start()
   after=submit(recovered,'native-eio-restarted')
  record=dict(unit=unit,family=family,kind='native-EIO',valid_fault=bool(rows),baseline=baseline,during=during,after=after,after_persisted=live_has(run,family,recovered),preexisting_state_retained=live_has(run,family,before),owner_restarts_needed=restarts,scope='Primary R10 uses public native chat.send/agent.wait or /v1/runs acknowledged background contract. Operator transport records are excluded from persistence proof. Acknowledgment, completed execution, retained user turn and later recovery are distinct; a missing database row alone is not proof of unrecoverable loss without examining other declared durable stores. Compatibility HTTP EIO is a separate entry contrast.')
  save(run/'result.json',record);print('STORAGE_NATIVE_EIO_DONE',unit,family,record['valid_fault'],response.get('acknowledged'),record['after_persisted'],flush=True)
  if not rows:raise RuntimeError('Native storage fault was not triggered; do not grade an untriggered injector')
  return record
 finally:
  (control/'ENABLED').unlink(missing_ok=True)
  if operator:operator.stop()
  gateway.stop();fixture.close()

def eio(unit,family):
 run=R/'runs-storage-faults/EIO'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial EIO attempt retained '+str(run))
 run.mkdir(parents=True);seed_copy(run,unit,family);control=run/'fault-control';events=run/'fault-events';control.mkdir();events.mkdir();fixture=Plan(run,family,[]);extra=[(LIB,'/sqlite-fault.so',True),(control,'/fault-control',True),(events,'/fault-events',False)];gateway=Gateway(run,family,fixture,extra_mounts=extra);i=gateway.command.index('--');gateway.command=gateway.command[:i]+['--setenv','LD_PRELOAD','/sqlite-fault.so']+gateway.command[i:];pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);before_token='R10_PREFLIGHT_U'+str(unit);attempt_token='R10_FAULT_ATTEMPT_U'+str(unit);recovered_token='R10_RECOVERED_U'+str(unit)
 print('STORAGE_EIO_START',unit,family,flush=True)
 try:
  gateway.start();baseline=gateway.chat(before_token,'eio-u'+str(unit),timeout=25)
  if not completed(baseline) or not live_has(run,family,before_token):raise RuntimeError('Native persistent admission positive control failed before EIO')
  (control/'ENABLED').write_text('Injected SQLITE I/O failure. Only state SQLite FD writes/fsyncs fail.');future=pool.submit(gateway.chat,attempt_token,'eio-fault-u'+str(unit),25);begin=time.monotonic()
  while not future.done() and time.monotonic()-begin<20:time.sleep(.1)
  if not future.done():gateway.stop()
  try:response=future.result(timeout=7)
  except Exception as ex:response={'exception':type(ex).__name__}
  rows=[json.loads(x) for x in (events/'events.jsonl').read_text().splitlines()] if (events/'events.jsonl').exists() else [];during=dict(response=response,completed=completed(response),user_turn_in_active_store=live_has(run,family,attempt_token),injected_failures=rows);save(run/'during-failure.json',during);(control/'ENABLED').unlink(missing_ok=True)
  restarts=0
  if gateway.process.poll() is not None:gateway.stop();gateway.start();restarts+=1
  try:after=gateway.chat(recovered_token,'eio-recovery-u'+str(unit),timeout=25)
  except Exception as ex:after={'exception':type(ex).__name__}
  if not completed(after):
   gateway.stop();gateway.start();restarts+=1;after=gateway.chat(recovered_token,'eio-recovery-retry-u'+str(unit),timeout=25)
  rec=dict(unit=unit,family=family,fault='SQLite state write/fsync EIO after successful persistent admission preflight',valid_fault=bool(rows),during=during,after=after,after_persisted=live_has(run,family,recovered_token),preexisting_state_retained=live_has(run,family,before_token),owner_restarts_needed=restarts,scope='Injected OS I/O errors, no product code edits. Completion without the active user turn is an observation requiring its declared persistence contract; an external fault log never counts as native audit.')
  save(run/'result.json',rec);print('STORAGE_EIO_DONE',unit,family,rec['valid_fault'],during['completed'],during['user_turn_in_active_store'],rec['after_persisted'],flush=True)
  if not rec['valid_fault']:raise RuntimeError('Storage injection did not reach a native SQLite write; do not grade an untriggered fault')
  return rec
 finally:gateway.stop();fixture.close();pool.shutdown(wait=False,cancel_futures=True)

def corruption(unit,family):
 run=R/'runs-storage-faults/corruption'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial corruption attempt retained '+str(run))
 run.mkdir(parents=True);source=seed_copy(run,unit,family);file=canonical_files(run,family)[0]
 if not file.exists():raise RuntimeError('Canonical conversation DB path not established')
 original_hash=hashlib.sha256(file.read_bytes()).hexdigest();with_backup=run/'original-active-db.snapshot';shutil.copy2(file,with_backup)
 with file.open('r+b') as stream:stream.write(b'CONTROLLED_CORRUPTION'.ljust(100,b'!'))
 corrupted_hash=hashlib.sha256(file.read_bytes()).hexdigest()
 args=['doctor','--non-interactive'] if family=='openclaw' else ['doctor'];p=subprocess.run(sandbox(run/'state',run/'workspace',family,cli(family,args)),capture_output=True,text=True,timeout=120);save(run/'native-diagnosis.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr,corrupted_database=str(file.relative_to(run)),original_sha256=original_hash,corrupted_sha256=corrupted_hash,active_path_present_after_diagnosis=file.exists()))
 # Recovery point is the source fixture's native pre-fault archive. Hermes additionally had its external workspace captured before corruption.
 bundle=run/'recovery-bundle';bundle.mkdir();archive_source=R/'runs-state-ops'/f'u{unit}'/family/'archives'/('full-backup.tar.gz' if family=='openclaw' else 'full-backup.zip');archive=bundle/archive_source.name;shutil.copy2(archive_source,archive)
 if family=='hermes':shutil.copytree(source/'workspace',bundle/'external-workspace-adjunct')
 target=run/'recovered';target.mkdir();configuration(family,target/'state');(target/'workspace').mkdir();(target/'workspace/PROMPT.md').write_text('Native corruption recovery.');restore(target,family,archive,old=False)
 if family=='openclaw':
  config=target/'state/openclaw.json';value=read_config(config);value.setdefault('cron',{})['enabled']=False;save(config,value)
 token='STATE_CANARY_'+str(unit)+'_'+family;fixture=Plan(target,family,[shell('python3 /workspace/seed.py'),portable_call('/workspace/PLUGIN_DELIVERED'),cron_list_step]);gateway=Gateway(target,family,fixture);(target/'workspace/DELIVERED.txt').unlink(missing_ok=True);(target/'workspace/PLUGIN_DELIVERED').unlink(missing_ok=True)
 print('CORRUPTION_RESTORE_START',unit,family,flush=True)
 try:
  gateway.start();reply=gateway.chat('Verify the restored original conversation, run the local seed verifier, and verify preserved native plugin and disabled scheduled job.','migration-'+str(unit),timeout=45);admin_jobs=None
  if family=='openclaw':
   from native_operator_client import Operator
   with Operator(gateway) as client:admin_jobs=client.rpc('cron.list',{'includeDisabled':True},'native-admin-restored-job-list')
  gateway.stop();first=next((x['request'] for x in fixture.calls if x['main']),{});last=next((x['request'] for x in reversed(fixture.calls) if x['main']),{});tool_results=[m for m in last.get('messages',[]) if m.get('role')=='tool'];job=disabled_job_in(admin_jobs) if admin_jobs is not None else bool(tool_results) and disabled_job_in(tool_results[-1].get('content'));file=target/'workspace/DELIVERED.txt';plugin=target/'workspace/PLUGIN_DELIVERED';rec=dict(unit=unit,family=family,native_diagnosis_exit=p.returncode,restored_history_visible_before_new_tool=token in json.dumps(first.get('messages',[])),restored_workspace_effect=file.exists() and file.read_text()==token,restored_native_plugin_called=plugin.exists() and plugin.read_text()=='PORTABLE_PLUGIN_OK',restored_job_listed_and_still_disabled=job,native_administrator_job_inventory=admin_jobs,response=reply,backup_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),recovery='Native verified full archive restore/import into a fresh stopped target at the ORIGINAL logical state/workspace layout, then documented offline activation and real native startup; corrupt state retained. This recovery control is separate from changed-logical-path M01 portability.');rec['passed']=reply.get('status')==200 and rec['restored_history_visible_before_new_tool'] and rec['restored_workspace_effect'] and rec['restored_native_plugin_called'] and job;save(run/'result.json',rec);print('CORRUPTION_RESTORE_DONE',unit,family,rec['passed'],flush=True);return rec
 finally:gateway.stop();fixture.close()
def main():
 os.chdir(OLD);prepare_shim();results=[]
 primary=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):primary.append(native_eio(unit,family));save(R/'results/native-storage-faults.json',primary)
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append({'kind':'EIO',**eio(unit,family)});save(R/'results/storage-faults.json',results);results.append({'kind':'corruption',**corruption(unit,family)});save(R/'results/storage-faults.json',results)
 print('STORAGE_FAULTS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
