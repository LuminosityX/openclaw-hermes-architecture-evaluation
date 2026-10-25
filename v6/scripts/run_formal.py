import argparse,hashlib,json,os,shutil,signal,subprocess,sys,threading,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from services import Business,AuditedRelay
from resources import create,read,wrap
from evaluate import evaluate_project,evaluate_data,evaluate_business
from audit_relay_unlimited import utc
BUDGET={'lock':threading.Lock(),'spent':0.,'reserved':0.,'limit':None}
def run_case(task,v,rep,family,phase='formal'):
 run=R/'runs'/phase/f'{task}-v{v}-r{rep}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial run retained; inspect before restart: '+str(run))
 run.mkdir(parents=True);run.chmod(0o700)
 if phase=='preflight':
  (run/'workspace').mkdir();(run/'workspace/PROMPT.md').write_text('Please reply exactly READY. Do not call tools.')
 else:shutil.copytree(R/'fixtures'/f'{task}-v{v}',run/'workspace')
 configuration(family,run/'state')
 save(run/'input-manifest.json',{str(p.relative_to(run/'workspace')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/'workspace').rglob('*') if p.is_file()})
 biz=Business(json.loads((R/'private'/f'W4-v{v}-service.json').read_text()),run/'business-truth.json') if task=='W4' and phase=='formal' else None
 relay=AuditedRelay(run,family,BUDGET,inference_authorized=True,business=biz)
 cmd=sandbox(run/'state',run/'workspace',family,command(family),relay.socket_dir)
 group=create('job-'+hashlib.sha256(str(run).encode()).hexdigest()[:18]+'-'+str(time.time_ns()));cmd=wrap(group,cmd)
 save(run/'launch.json',dict(command=cmd,model='deepseek-flash',reasoning='high',source='OpenClawfe06181 / Hermes stablebf0203a',permissions='Matched explicit task authorization in outer evaluator isolation; not native security evidence'))
 rec=dict(task=task,variant=v,repeat=rep,family=family,phase=phase,started=utc(),failure=None,human_interventions=0)
 start=time.monotonic();print('START',phase,task,v,rep,family,flush=True)
 process=None;memory=[]
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:
   env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HOME','TERM']}
   process=subprocess.Popen(cmd,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True,env=env)
   save(R/'evidence/active.json',dict(pid=process.pid,task=task,variant=v,repeat=rep,family=family,run=str(run),started=utc()))
   last=0
   while process.poll() is None:
    elapsed=time.monotonic()-start
    try:memory.append(dict(seconds=elapsed,bytes=int((group/'memory.current').read_text())))
    except OSError:pass
    if elapsed-last>=30:print('ACTIVE',task,v,rep,family,round(elapsed),'s',relay.calls,'requests',flush=True);last=elapsed;save(run/'progress.json',dict(elapsed_seconds=elapsed,model_calls=relay.calls))
    if elapsed>900 or relay.violations or relay.calls>128:
     rec['failure']='timeout' if elapsed>900 else 'fixed_model_policy' if relay.violations else 'request_ceiling'
     os.killpg(process.pid,signal.SIGTERM)
     try:process.wait(timeout=8)
     except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
     break
    time.sleep(1)
   rec.update(elapsed_seconds=round(time.monotonic()-start,3),exit_code=process.returncode)
  until=time.monotonic()+8
  while len(relay.responses)<relay.calls and time.monotonic()<until:time.sleep(.2)
  save(run/'resources.json',read(group));save(run/'memory-samples.json',memory)
  save(run/'artifact-manifest.json',{str(p.relative_to(run/'workspace')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/'workspace').rglob('*') if p.is_file() and not p.is_symlink()})
  relay.inference_authorized=False
  if phase=='preflight':acc=dict(passed=rec['exit_code']==0 and relay.calls>0 and not relay.violations,checks=[])
  elif task in ['W1','W2']:acc=evaluate_project(run,task,family,913+v*37)
  elif task=='W3':acc=evaluate_data(run,family,v)
  else:acc=evaluate_business(run,family,biz,relay)
  save(run/'acceptance.json',acc)
  rec.update(passed=bool(acc.get('passed')) and rec['exit_code']==0 and not rec['failure'],checks_passed=sum(x['passed'] for x in acc.get('checks',[])),checks_total=len(acc.get('checks',[])))
 finally:
  if process and process.poll() is None:
   os.killpg(process.pid,signal.SIGKILL);process.wait()
  relay.close();save(R/'evidence/active.json',dict(active=False,at=utc()))
 rec.update(ended=utc(),model_calls=relay.calls,responses=relay.responses,violations=relay.violations,cost_estimated_CNY=sum(x.get('estimated_cost_CNY') or 0 for x in relay.responses),cost_incomplete=any(x.get('usage_completeness')!='terminal_observed' for x in relay.responses))
 save(run/'result.json',rec);print('DONE',task,v,rep,family,'PASS' if rec['passed'] else 'FAIL',rec['elapsed_seconds'],'s',relay.calls,'requests',round(rec['cost_estimated_CNY'],5),'CNY',flush=True)
 return rec

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--preflight',action='store_true');ap.add_argument('--tasks',nargs='*',default=['W1','W2','W3','W4']);ap.add_argument('--limit',type=int,default=1000);a=ap.parse_args();os.chdir(OLD)
 save(R/'evidence/authorization-current.json',dict(at=utc(),user_instruction='不用管总预算了，你就跑实验，我要对比结果',financial_cap=None,models='OpenClaw/Hermes with DeepSeek Flash only',concurrency=1,no_new_paid_cloud=True))
 if a.preflight:
  for family in ['openclaw','hermes']:run_case('READY',0,0,family,'preflight')
  return
 results=[];order=[]
 for rep in [1,2]:
  for v in [1,2,3]:
   for task in a.tasks:
    fs=['openclaw','hermes'] if (rep+v+int(task[1:]))%2 else ['hermes','openclaw'];order.extend((task,v,rep,f) for f in fs)
 save(R/'evidence/formal-order.json',order)
 for task,v,rep,f in order[:a.limit]:
  r=run_case(task,v,rep,f);results.append(r);save(R/'results/formal-task-results.json',results)
  if r['failure']=='fixed_model_policy':raise RuntimeError('Model/configuration gate violated; inspect rather than score as product weakness')
 print('FORMAL_TASK_BATCH_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
