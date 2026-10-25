"""C07 capability guard: Hermes Kanban has an additional native worker deadline.
Keep the interactive soft-budget contrast, but do not mistake it for absence of
all native hard time controls. Official CLI/dispatcher only, no database writes.
"""
import json,os,sqlite3,time
from pathlib import Path
from runtime import R,OLD,configuration,save
from controlled import Plan,shell
from gateway import Gateway
from run_state_ops import cli

def inventory(state):
 rows=[]
 for path in state.rglob('*.db'):
  if 'installs' in path.parts:continue
  try:
   c=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
   tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
   if {'tasks','task_events'}<=tables:
    rows.append(dict(path=str(path.relative_to(state)),tasks=[dict(r) for r in c.execute('select * from tasks')],events=[dict(r) for r in c.execute('select * from task_events')]))
   c.close()
  except sqlite3.Error:pass
 return rows

def one(unit,positive=False):
 run=R/'runs-budget-native-kanban'/('positive' if positive else 'deadline')/f'u{unit}'
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial native Kanban budget attempt retained '+str(run))
 run.mkdir(parents=True);configuration('hermes',run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled native Kanban deadline experiment.')
 (work/'tick.py').write_text("from pathlib import Path\nimport time,sys,os,json\nwith Path('/workspace/effects.jsonl').open('a') as f:f.write(json.dumps(dict(time_ns=time.monotonic_ns(),pid=os.getpid(),index=sys.argv[1]))+'\\n')\ntime.sleep(.1)\nprint('TICK')\n")
 p=run/'state/hermes/config.yaml';cfg=json.loads(p.read_text());cfg['agent']['run_budget_seconds']=None;cfg['kanban']={'dispatch_in_gateway':True,'dispatch_interval_seconds':1,'max_spawn':1,'max_in_progress':1,'failure_limit':1,'review_dispatch':False};cfg['approvals']={'mode':'off','single_query_mode':'approve','unattended_mode':'approve'};save(p,cfg)
 fixture=Plan(run,'hermes',[shell('python3 /workspace/tick.py '+str(i)) for i in range(2 if positive else 1000)]);gateway=Gateway(run,'hermes',fixture,persistent_namespace=True)
 # The real owner in this namespace is manually launched, not a systemd unit.
 # Outer VM service markers falsely advertised a systemd manager that is not
 # mounted/running here. Remove only those inherited supervisor markers; keep
 # every native launch flag and all native worker policy unchanged.
 at=gateway.command.index('--');unset=[]
 for marker in ['INVOCATION_ID','SYSTEMD_EXEC_PID','JOURNAL_STREAM','NOTIFY_SOCKET']:unset+=['--unsetenv',marker]
 gateway.command=gateway.command[:at]+unset+gateway.command[at:];save(run/'manual-owner-environment.json',dict(unset_outer_supervisor_markers=['INVOCATION_ID','SYSTEMD_EXEC_PID','JOURNAL_STREAM','NOTIFY_SOCKET'],scope='Manually launched evaluator namespace; no systemd manager or user bus is present. Native launch flags are unchanged.'))
 print('NATIVE_KANBAN_BUDGET_START',unit,positive,flush=True)
 try:
  gateway.start()
  for label,args in [('init',['kanban','init']),('create',['kanban','create','C07 controlled native deadline','--assignee','default','--workspace','dir:/workspace','--max-runtime','120' if positive else '2','--max-retries','1','--model','deepseek-flash','--provider','deepseek','--json'])]:
   result=gateway.harness('POST','/exec',{'command':cli('hermes',args),'timeout':45},timeout=50);save(run/(label+'.json'),result)
   if result['exit_code']:raise RuntimeError('Native Kanban setup failed: '+label)
  until=time.monotonic()+65;observed=[]
  while time.monotonic()<until:
   observed=inventory(run/'state');events=[e for db in observed for e in db['events']]
   if positive and (work/'effects.jsonl').exists():break
   if not positive and any(e.get('kind')=='timed_out' for e in events):break
   time.sleep(.2)
  save(run/'native-kanban-state.json',observed);before=(work/'effects.jsonl').read_text() if (work/'effects.jsonl').exists() else '';time.sleep(5);after=(work/'effects.jsonl').read_text() if (work/'effects.jsonl').exists() else '';events=[e for db in observed for e in db['events']];timed=[e for e in events if e.get('kind')=='timed_out'];tasks=[t for db in observed for t in db['tasks']]
  record=dict(unit=unit,family='hermes',positive_control=positive,native_timeout_observed=bool(timed),native_timeout_events=timed,native_task_statuses=[t.get('status') for t in tasks],actual_tool_effects=bool(after),effects_stable_after_native_timeout=before==after,main_provider_calls=sum(c['main'] for c in fixture.calls),real_model=False,scope='Public Hermes Kanban task max-runtime plus max-retries=1 and native 1-second dispatcher tick. This is a queued-worker cap, not an interactive chat timeout. Positive control proves the same native worker can call the controlled model and execute the tool; it is not used as a clean completed-card quality result. Evaluator does not signal workers before this observation.')
  record['valid']=bool(after) and any(c['main'] for c in fixture.calls) if positive else bool(timed) and bool(tasks)
  save(run/'result.json',record);print('NATIVE_KANBAN_BUDGET_DONE',unit,positive,record['valid'],flush=True)
  if not record['valid']:raise RuntimeError('Native deadline capability preflight unresolved; no absence-of-capability conclusion')
  return record
 finally:gateway.stop();fixture.close()

def main():
 os.chdir(OLD);records=[one(0,True)];save(R/'results/native-kanban-budget.json',records)
 for unit in range(1,4):records.append(one(unit));save(R/'results/native-kanban-budget.json',records)
 print('NATIVE_KANBAN_BUDGET_COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
