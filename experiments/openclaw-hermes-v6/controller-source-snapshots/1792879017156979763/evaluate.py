import csv,json,subprocess,shutil,hashlib,re
from pathlib import Path
from runtime import R,sandbox,save

def project_checks(task,seed,obs):
 checks=[]
 def check(n,v):checks.append(dict(name=n,passed=bool(v)))
 if obs.get('probe_error'):return [dict(name='api_probe',passed=False,error=obs)]
 if task=='W1':
  for r in obs.get('observations',[]):
   if r['case']=='new_relay':check('new_relay_removed',not r['relay_left'] and r['names']==[]);continue
   check(r['case']+'_error',r['error'] is not None);check(r['case']+'_names',r['names']==['good'] and not r['plugin_present']);check(r['case']+'_hooks',r['calls']==[7+seed]);check(r['case']+'_retry',r.get('retry_name')=='broken')
  return checks
 def valid(events,n):
  groups={};fields={'call_id','parent_call_id','hook_name','plugin_name','phase','duration_ns','exception_type'}
  try:
   for i,e in enumerate(events):
    if not fields<=set(e) or not isinstance(e['call_id'],str) or not e['call_id'] or type(e['duration_ns']) is not int or e['duration_ns']<0:return False
    groups.setdefault(e['call_id'],[]).append((i,e))
   if len(groups)!=n:return False
   for cid,es in groups.items():
    if len(es)!=2 or [x[1]['phase'] for x in es]!=['start','finish'] or es[0][1]['duration_ns']!=0:return False
    parent=es[0][1]['parent_call_id']
    if parent is not None and (parent not in groups or not groups[parent][0][0]<es[0][0]<es[1][0]<groups[parent][1][0]):return False
   return True
  except (KeyError,TypeError):return False
 rows={x['case']:x for x in obs.get('observations',[])}
 a=rows.get('observers',{});check('observer_return',a.get('result')==[seed*2,seed+1]);check('observer_events',valid(a.get('a',[]),2) and valid(a.get('b',[]),2));check('observer_undo',a.get('after_a')==4 and a.get('after_b')==8 and a.get('final_b')==8)
 a=rows.get('nested',{});check('nested_return',a.get('result')==[seed*3+1]);check('nested_trace',valid(a.get('events',[]),2));check('nested_roots',sum(e.get('phase')=='start' and e.get('parent_call_id') is None for e in a.get('events',[]))==1)
 a=rows.get('threads',{});check('thread_returns',sorted(a.get('results',[]))==sorted([[(seed+i)*3+1] for i in range(3)]));check('thread_trace',valid(a.get('events',[]),6));check('thread_roots',sum(e.get('phase')=='start' and e.get('parent_call_id') is None for e in a.get('events',[]))==3)
 a=rows.get('exception',{});check('business_exception',a.get('error')=='ValueError');check('exception_trace',valid(a.get('events',[]),1) and any(e.get('phase')=='finish' and e.get('exception_type')=='ValueError' for e in a.get('events',[])))
 a=rows.get('wrapper',{});check('wrapper_semantics',a.get('error') is None and a.get('result')==['recovered']);check('wrapper_trace',valid(a.get('events',[]),2));check('wrapper_errors',any(e.get('phase')=='finish' and e.get('plugin_name')=='bad' and e.get('exception_type')=='ValueError' for e in a.get('events',[])) and any(e.get('phase')=='finish' and e.get('plugin_name')=='suppress' and e.get('exception_type') is None for e in a.get('events',[])))
 a=rows.get('first_legacy',{});check('firstresult_legacy',a.get('result')==seed+11);check('legacy_trace',valid(a.get('events',[]),2))
 a=rows.get('manager_isolation',{});check('manager_isolation',a.get('result')==[seed+19] and valid(a.get('a',[]),1) and valid(a.get('b',[]),1) and all(e.get('parent_call_id') is None for e in a.get('b',[])))
 a=rows.get('observer_recursion',{});check('observer_recursion',a.get('result')==[seed+1] and valid(a.get('events',[]),1));return checks

def evaluate_project(run,task,family,seed,positive_control=None):
 if positive_control:mount=R/'private'
 else:
  mount=run/'observation-probe';mount.mkdir(exist_ok=True);shutil.copy(R/'private/probe_project.py',mount/'probe_project.py')
 cmd=['python3','/probe/probe_project.py',task,str(seed)]
 if positive_control:cmd=['python3','-c',f"import sys,runpy;sys.path[:0]=['/workspace/project/src','/probe'];import {positive_control};sys.argv=['probe',{task!r},{str(seed)!r}];runpy.run_path('/probe/probe_project.py',run_name='__main__')"]
 p=subprocess.run(sandbox(run/'state',run/'workspace',family,cmd,extra_mounts=[(mount,'/probe',True)]),capture_output=True,text=True,timeout=60)
 try:obs=json.loads(p.stdout.strip().splitlines()[-1])
 except Exception:obs=dict(probe_error='runner_invalid',stdout=p.stdout,stderr=p.stderr)
 checks=project_checks(task,seed,obs)
 p=subprocess.run(sandbox(run/'state',run/'workspace',family,['python3','/workspace/run_tests.py']),capture_output=True,text=True,timeout=120)
 counts=re.findall(r'(\d+) passed',p.stdout);upstream_count=int(counts[-1]) if counts else None
 checks.append(dict(name='upstream_regressions',passed=p.returncode==0 and upstream_count==109,passed_test_count=upstream_count,expected_test_count=109));save(run/'upstream-tests.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
 return dict(passed=bool(checks) and all(x['passed'] for x in checks),checks=checks,observations=obs)

def evaluate_data(run,family,variant):
 want=json.loads((R/'private'/f'W3-v{variant}-expected.json').read_text());checks=[]
 def verify(out,label,expected):
  try:
   with (out/'summary.csv').open(encoding='utf-8-sig',newline='') as f:got=list(csv.DictReader(f))
   checks.append(dict(name=label+'_summary',passed=got==expected['summary']))
   a=json.loads((out/'audit.json').read_text());checks.append(dict(name=label+'_audit',passed=all(a.get(k)==v for k,v in expected['audit'].items())))
  except Exception as e:checks.append(dict(name=label,passed=False,error=type(e).__name__))
 verify(run/'workspace/output','original',want)
 p=subprocess.run(sandbox(run/'state',run/'workspace',family,['python3','/workspace/reconcile_data.py','--input-dir','/workspace/sources','--output-dir','/workspace/eval_rerun']),capture_output=True,text=True,timeout=60)
 checks.append(dict(name='rerun_exit',passed=p.returncode==0));verify(run/'workspace/eval_rerun','rerun',want)
 changed=run/'changed-input';shutil.copytree(run/'workspace/sources',changed,dirs_exist_ok=True)
 for f in changed.glob('*.csv'):
  with f.open(encoding='utf-8-sig',newline='') as s:q=csv.DictReader(s);fields=q.fieldnames;rows=list(q)
  for row in rows:
   if row['record_id']=='EDGE0':row['units']=str(int(row['units'])+3)
  with f.open('w',newline='') as s:q=csv.DictWriter(s,fieldnames=fields);q.writeheader();q.writerows(rows)
 altered=json.loads(json.dumps(want))
 for row in altered['summary']:
  if row['region']=='华东' and row['currency']=='CNY':row['units']=str(int(row['units'])+3)
 p=subprocess.run(sandbox(run/'state',run/'workspace',family,['python3','/workspace/reconcile_data.py','--input-dir','/changed','--output-dir','/workspace/eval_changed'],extra_mounts=[(changed,'/changed',True)]),capture_output=True,text=True,timeout=60)
 checks.append(dict(name='changed_exit',passed=p.returncode==0));verify(run/'workspace/eval_changed','changed',altered)
 try:text=(run/'workspace/output/report.md').read_text();checks.append(dict(name='source_traceability',passed='policy-2026.txt' in text and sum(f'part-{j}.csv' in text for j in range(3))>=2))
 except OSError:checks.append(dict(name='source_traceability',passed=False))
 return dict(passed=all(x['passed'] for x in checks),checks=checks)

def expected_business(spec):
 from decimal import Decimal,ROUND_HALF_UP
 latest={}
 for row in spec['orders']:
  if row['id'] not in latest or row['revision']>latest[row['id']]['revision']:latest[row['id']]=row
 expected={k:v for k,v in spec['initial'].items() if k not in latest};groups={};active=void=0
 for key,row in latest.items():
  if row['status']=='void':void+=1;continue
  active+=1;net=__import__('decimal').Decimal(row['gross']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)-Decimal(row['refund']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
  expected[key]=dict(id=key,revision=row['revision'],currency=row['currency'],net=f'{net:.2f}')
  a=groups.setdefault(row['currency'],[0,Decimal(0)]);a[0]+=1;a[1]+=net
 rows=sorted(expected.values(),key=lambda x:x['id']);digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 report=dict(unique_orders=len(latest),active_orders=active,void_orders=void,by_currency=[dict(currency=k,records=v[0],net=f'{v[1]:.2f}') for k,v in sorted(groups.items())],billing_digest=digest)
 return expected,report,latest

def evaluate_business(run,family,biz,relay):
 expected,report,latest=expected_business(biz.spec);checks=[]
 def check(n,b):checks.append(dict(name=n,passed=bool(b)))
 check('native_business_state',biz.billing==expected)
 check('no_wrong_commits',all((e['kind']=='put' and e['key'] in expected and e['after']==expected[e['key']]) or (e['kind']=='delete' and e['key'] in latest and latest[e['key']]['status']=='void') for e in biz.events))
 try:actual=json.loads((run/'workspace/report.json').read_text());check('report',all(actual.get(k)==v for k,v in report.items()))
 except Exception:check('report',False)
 count=len(biz.events)
 p=subprocess.run(sandbox(run/'state',run/'workspace',family,['python3','/workspace/sync_worker.py','--base-url','http://127.0.0.1:18080/biz','--output','/workspace/report-rerun.json'],relay.socket_dir),capture_output=True,text=True,timeout=60)
 check('reproducible_exit',p.returncode==0);check('idempotent_no_new_writes',len(biz.events)==count and biz.billing==expected)
 try:a=json.loads((run/'workspace/report-rerun.json').read_text());check('rerun_report',all(a.get(k)==v for k,v in report.items()))
 except Exception:check('rerun_report',False)
 check('documentation',(run/'workspace/README.md').exists())
 return dict(passed=all(x['passed'] for x in checks),checks=checks,expected_report=report,effect_count=len(biz.events))
