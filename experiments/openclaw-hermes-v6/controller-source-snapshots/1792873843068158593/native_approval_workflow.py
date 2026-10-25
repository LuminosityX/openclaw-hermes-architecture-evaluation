"""Evaluator client for a real approval workflow on an already running native owner.
All operator decisions are external truth; only native stores/exporters count as audit.
"""
import concurrent.futures,json,os,signal,subprocess,time
from pathlib import Path
from runtime import sandbox,save
from run_approvals import BRIDGE,operator_rpc

def approved_workflow(gateway,prompt,session):
 root=gateway.run;family=gateway.family;observer=None;pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);decisions=[]
 try:
  if family=='openclaw':
   helper=Path(__file__).parent/'native_approval_observer.mjs'
   args=sandbox(root/'state',root/'workspace',family,['python3','/bridge.py',str(gateway.port),json.dumps(['node','/approval-observer.mjs'])],gateway.relay.socket_dir,[(BRIDGE,'/bridge.py',True),(helper,'/approval-observer.mjs',True),(root/'state/control.sock','/gateway-control.sock',False)])
   log=(root/'approval-observer.log').open('w');observer=subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True);until=time.monotonic()+20
   while not(root/'state/approval-observer-ready.json').exists() and time.monotonic()<until and observer.poll() is None:time.sleep(.05)
   if not(root/'state/approval-observer-ready.json').exists():raise RuntimeError('Native approval inbox did not connect')
   future=pool.submit(gateway.chat,prompt,session,timeout=120)
  else:
   code,_,raw=gateway.raw('POST','/v1/runs',{'model':'deepseek-flash','input':prompt,'stream':False},headers={'X-Hermes-Session-Key':session});start=json.loads(raw);save(root/'native-approval-workflow-admission.json',dict(status=code,body=start));run_id=start.get('run_id')
   if code!=202 or not run_id:raise RuntimeError('Native async approval admission failed')
  until=time.monotonic()+115;seen=set();status={}
  while time.monotonic()<until:
   if family=='openclaw':
    if future.done():break
    pending=operator_rpc(gateway,'exec.approval.list',{},'audit-pending')
   else:
    code,_,raw=gateway.raw('GET','/v1/runs/'+run_id,timeout=10);status=json.loads(raw)
    if status.get('status') in ['completed','failed','cancelled','interrupted']:break
    pending=status.get('pending_controls',[])
   for entry in pending:
    identity=entry.get('id') or entry.get('prompt_id') or entry.get('request_id')
    if not identity or identity in seen:continue
    choice='allow-once' if len(decisions)<2 else 'deny'
    if family=='openclaw':reply=operator_rpc(gateway,'exec.approval.resolve',{'id':identity,'decision':choice},'audit-resolve-'+str(len(decisions)))
    else:
     code,_,raw=gateway.raw('POST','/v1/runs/'+run_id+'/approval',{'request_id':identity,'execution_generation':entry.get('execution_generation',status.get('execution_generation')),'choice':'once' if choice=='allow-once' else 'deny'},timeout=15);reply=dict(status=code,body=raw.decode())
     if code!=200:raise RuntimeError('Native approval rejected current identity')
    decisions.append(dict(identity=identity,choice=choice,pending=entry,native_response=reply));seen.add(identity);save(root/'operator-approval-truth.json',decisions)
   time.sleep(.15)
  if family=='openclaw':response=future.result(timeout=5)
  else:response=dict(status=200 if status.get('status')=='completed' else 500,response=status)
  if len(decisions)!=3:raise RuntimeError('Audit approval workflow did not observe the three actual decisions')
  return response,decisions
 finally:
  if observer and observer.poll() is None:
   os.killpg(observer.pid,signal.SIGTERM)
   try:observer.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(observer.pid,signal.SIGKILL);observer.wait()
  pool.shutdown(wait=False,cancel_futures=True)
