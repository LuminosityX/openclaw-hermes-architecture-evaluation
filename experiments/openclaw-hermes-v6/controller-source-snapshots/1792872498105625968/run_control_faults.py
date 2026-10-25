"""Native stream/tool boundary faults and task wall budget. Fixed provider plans, zero paid calls."""
import json,os,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan,shell
class Effects(Plan):
 def __init__(self,*a,**kw):self.receipts=[];self.lost_once=False;super().__init__(*a,**kw)
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_POST(self):
    if self.path=='/commit':
     body=self.rfile.read(int(self.headers.get('Content-Length',0)));owner.receipts.append(dict(id=len(owner.receipts)+1,body=body.decode(),at_ns=time.monotonic_ns()));save(owner.run/'effect-receipts.json',owner.receipts)
     if not owner.lost_once:
      owner.lost_once=True;self.close_connection=True;self.connection.shutdown(__import__('socket').SHUT_RDWR);return
     return self.send({'id':owner.receipts[-1]['id']})
    return super().do_POST()
   def do_GET(self):
    if self.path=='/receipts':return self.send(owner.receipts)
    return super().do_GET()
  return H

def run_case(unit,kind,family):
 run=R/'runs-control-faults'/kind/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial control/fault attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled fault/budget test. Return CONTROLLED_COMPLETE only after the supplied native tool plan has settled.');plans=[];fault=None
 if kind=='R03-truncated-stream':fault='truncated_stream'
 elif kind=='R04-tool-before-effect':
  (work/'before.py').write_text("raise SystemExit(7)\n");(work/'repaired.py').write_text("from pathlib import Path\nPath('/workspace/DELIVERED').write_text('one correct delivery')\nprint('REPAIRED_OK')\n");plans=[shell('python3 /workspace/before.py'),shell('python3 /workspace/repaired.py')]
 elif kind=='R05-lost-commit-ack':
  (work/'commit.py').write_text("import urllib.request\nrequest=urllib.request.Request('http://127.0.0.1:18080/commit',data=b'controlled-one-commit',method='POST')\nprint(urllib.request.urlopen(request,timeout=2).read().decode())\n");(work/'reconcile.py').write_text("import urllib.request,json\nfrom pathlib import Path\nreceipts=json.load(urllib.request.urlopen('http://127.0.0.1:18080/receipts'))\nPath('/workspace/RECONCILED.json').write_text(json.dumps(receipts))\nprint(json.dumps(receipts))\n");plans=[shell('python3 /workspace/commit.py'),shell('python3 /workspace/reconcile.py')]
 elif kind=='C07-task-wall-budget':
  (work/'tick.py').write_text("import time\nfrom pathlib import Path\nwith Path('/workspace/effects.jsonl').open('a') as f:f.write(str(time.monotonic())+'\\n')\ntime.sleep(.1)\nprint('TICK')\n");plans=[shell('python3 /workspace/tick.py '+str(i)) for i in range(100)]
  p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text())
  if family=='openclaw':c['agents']['defaults']['timeoutSeconds']=2
  else:c['agent']['run_budget_seconds']=2
  save(p,c)
 else:raise RuntimeError('Unknown case')
 fixture=Effects(run,family,plans,fault=fault);cmd=command(family)
 if kind=='C07-task-wall-budget' and family=='openclaw':cmd[cmd.index('--timeout')+1]='2'
 args=sandbox(run/'state',work,family,cmd,fixture.socket_dir);print('CONTROL_FAULT_START',kind,unit,family,flush=True);start=time.monotonic()
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(args,stdout=out,stderr=err,timeout=90)
  stdout=(run/'stdout.jsonl').read_text();stderr=(run/'stderr.log').read_text();events=[]
  try:events=[json.loads(stdout)]
  except ValueError:
   for line in stdout.splitlines():
    try:events.append(json.loads(line))
    except ValueError:pass
  native_ok=any(x.get('ok') is True and x.get('status')=='ok' for x in events) if family=='openclaw' else any(x.get('type')=='result' and x.get('exit_code')==0 for x in events)
  calls=[x for x in fixture.calls if x['main']];rec=dict(unit=unit,family=family,kind=kind,exit_code=p.returncode,elapsed_seconds=time.monotonic()-start,main_provider_requests=len(calls),native_reported_ok=native_ok,real_model=False)
  if kind=='R03-truncated-stream':
   rec.update(recovered=len(calls)>1 and 'CONTROLLED_COMPLETE' in stdout and native_ok,partial_accepted_as_success=native_ok and 'PARTIAL ' in stdout and 'CONTROLLED_COMPLETE' not in stdout,explicit_interruption=p.returncode!=0 or any(x in (stdout+stderr).lower() for x in ['interrupt','truncated','incomplete','stream error']))
  elif kind=='R04-tool-before-effect':rec.update(completed=(work/'DELIVERED').exists() and native_ok,tool_failure_visible=any('7' in str(m) for c in calls for m in c['request'].get('messages',[]) if m.get('role')=='tool'))
  elif kind=='R05-lost-commit-ack':
   f=work/'RECONCILED.json';reconciled=json.loads(f.read_text()) if f.exists() else [];rec.update(effect_count=len(fixture.receipts),reconciled_count=len(reconciled),safe_reconciliation=len(fixture.receipts)==1 and len(reconciled)==1 and native_ok,scope='Provider plan queries receipts after lost tool acknowledgement; tests orchestration avoiding unilateral tool replay, not general model reasoning about unknown effects.')
  else:
   timestamps=[float(x) for x in (work/'effects.jsonl').read_text().splitlines()] if (work/'effects.jsonl').exists() else [];first=calls[0]['time_ns']/1e9 if calls else None;last=calls[-1]['time_ns']/1e9 if calls else None;rec.update(configured_wall_seconds=2,effect_count=len(timestamps),first_to_last_provider_seconds=last-first if first is not None else None,effects_after_5_seconds_from_first_request=sum(t>first+5 for t in timestamps) if first is not None else None,native_stopped_loop=len(calls)<100,scope='Native wall budget only. Provider/model request-count and fee-cap support require separate evidence; outer subprocess timeout is not credited as a product cap.')
  save(run/'result.json',rec);print('CONTROL_FAULT_DONE',kind,unit,family,rec,flush=True);return rec
 finally:fixture.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for kind in ['R03-truncated-stream','R04-tool-before-effect','R05-lost-commit-ack','C07-task-wall-budget']:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,kind,family));save(R/'results/control-faults.json',results)
 print('CONTROL_FAULTS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
