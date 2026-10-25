"""One native HTTP service at a time; deterministic 250 ms provider, no paid inference."""
import json,os,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from run_mechanisms import C,OLD,Fixture,save

DRIVER=r'''
import concurrent.futures,http.client,json,os,socket,subprocess,sys,time,uuid,signal
from pathlib import Path
family=sys.argv[1];S=Path('/state');W=Path('/workspace');port=18789 if family=='openclaw' else 18790
if family=='openclaw':
 p=S/'openclaw.json';c=json.loads(p.read_text());c['gateway']={'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':'synthetic-scale-token'},'controlUi':{'enabled':False},'http':{'endpoints':{'chatCompletions':{'enabled':True}}}};c['agents']['defaults']['maxConcurrent']=8;p.write_text(json.dumps(c))
 cmd=['node','/runtime/openclaw/node_modules/openclaw/openclaw.mjs','gateway','run','--bind','loopback','--port',str(port)]
else:
 p=S/'hermes/config.yaml';c=json.loads(p.read_text());c['gateway']={'api_server':{'max_concurrent_runs':8}};c['platform_toolsets']={'api_server':['terminal']};p.write_text(json.dumps(c))
 # Official gateway startup installs session authority and durable admission.
 # Direct APIServerAdapter.connect() is legacy/component mode and is not comparable.
 cmd=['bash','-c','cd /runtime/hermes-source; task_activation="$(/runtime/hermes-tools/python-3.14.9+20261021-linux-x64/bin/python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes gateway run']
env=dict(os.environ);env['OPENCLAW_SKIP_CHANNELS']='1'
if family=='hermes':env.update(API_SERVER_ENABLED='true',API_SERVER_KEY='synthetic-scale-token',API_SERVER_HOST='127.0.0.1',API_SERVER_PORT=str(port),API_SERVER_MODEL_NAME='deepseek-flash')
with (S/'http-server.log').open('w') as log:
 server=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True,env=env)
 try:
  until=time.monotonic()+60
  while time.monotonic()<until:
   if server.poll() is not None:raise RuntimeError('server exited')
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('port not ready')
  def request(_):
   token='SCALE_'+uuid.uuid4().hex;body=json.dumps({'model':'openclaw' if family=='openclaw' else 'deepseek-flash','messages':[{'role':'user','content':'Return exactly '+token}],'stream':False,'user':token})
   start=time.monotonic();conn=http.client.HTTPConnection('127.0.0.1',port,timeout=45)
   try:
    conn.request('POST','/v1/chat/completions',body,{'Content-Type':'application/json','Authorization':'Bearer synthetic-scale-token'});res=conn.getresponse();raw=res.read().decode();data=json.loads(raw)
    content=''.join(str(c.get('message',{}).get('content','')) for c in data.get('choices',[]));ok=res.status==200 and token in content
    return dict(token=token,status=res.status,correct=ok,seconds=time.monotonic()-start,response=data)
   except Exception as e:return dict(token=token,correct=False,seconds=time.monotonic()-start,error=type(e).__name__)
   finally:conn.close()
  warmup=request(0);(W/'warmup.json').write_text(json.dumps(warmup))
  if not warmup['correct']:raise RuntimeError('functional warmup failed; inspect raw response')
  results=[]
  for repeat in range(5):
   for n in ([1,2,4,8] if repeat%2==0 else [8,4,2,1]):
    start=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:group=list(pool.map(request,range(n)))
    elapsed=time.monotonic()-start
    results.append(dict(repeat=repeat,concurrency=n,seconds=elapsed,completed=sum(x['correct'] for x in group),requests=group,throughput=sum(x['correct'] for x in group)/elapsed))
    (W/'scale-results.json').write_text(json.dumps(results));print(json.dumps({'family':family,'concurrency':n,'repeat':repeat,'seconds':elapsed,'completed':sum(x['correct'] for x in group)}),flush=True)
 finally:
  if server.poll() is None:
   os.killpg(server.pid,signal.SIGTERM)
   try:server.wait(timeout=8)
   except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait()
'''

def main():
 os.chdir(OLD)
 active=json.loads((R/'evidence/active.json').read_text())
 if active.get('pid'):raise RuntimeError('Wait for paid timing batch')
 for family in ['openclaw','hermes']:
  run=R/'runs-mechanisms/http-scale'/family
  if run.exists():raise RuntimeError('Preserve existing run')
  run.mkdir(parents=True);(run/'state').mkdir();(run/'workspace').mkdir();C.configuration(family,run/'state')
  (run/'workspace/PROMPT.md').write_text('Controlled native HTTP concurrency fixture. No real model calls.\n')
  (run/'workspace/http_driver.py').write_text(DRIVER)
  fixture=Fixture(run,family,'scale');cmd=C.sandbox(run/'state',run/'workspace',fixture.socket_dir,family,['python3','/workspace/http_driver.py',family])
  save(run/'launch.json',dict(command=cmd,real_model=False,provider_fixed_latency_seconds=.25,surface='official native Gateway with durable admission; not standalone API component'))
  print('SCALE_START',family,flush=True)
  try:
   with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:
    result=subprocess.run(cmd,stdout=out,stderr=err,timeout=300)
   path=run/'workspace/scale-results.json';data=json.loads(path.read_text()) if path.exists() else []
   save(run/'result.json',dict(family=family,exit_code=result.returncode,real_model=False,paid_calls=0,passed=len(data)==20 and all(x['completed']==x['concurrency'] for x in data),batches=data))
   print('SCALE_DONE',family,'batches',len(data),'exit',result.returncode,flush=True)
  finally:fixture.close()

if __name__=='__main__':main()
