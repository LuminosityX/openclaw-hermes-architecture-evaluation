"""Coordinator for official native gateways through a task-only Unix control forward."""
import hashlib,http.client,json,os,signal,socket,subprocess,time,uuid
from pathlib import Path
from runtime import R,sandbox,save,read_config
class Control(http.client.HTTPConnection):
 def __init__(self,path,timeout=950):
  actual=Path(path).absolute()
  if not actual.is_relative_to(R):raise ValueError('Control socket outside task root')
  short=R/'evidence/controls'/hashlib.sha256(str(actual.parent).encode()).hexdigest()[:10];short.parent.mkdir(parents=True,exist_ok=True)
  if not short.is_symlink():short.symlink_to(actual.parent,target_is_directory=True)
  elif short.resolve()!=actual.parent:raise ValueError('Unexpected control alias owner')
  self.unix_path=str(short/actual.name);super().__init__('localhost',timeout=timeout)
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect(self.unix_path)
class Gateway:
 def __init__(self,run,family,relay,concurrency=16,relocated=False,extra_mounts=(),persistent_namespace=False,allow_disk_warning=False):
  self.run=Path(run);self.family=family;self.relay=relay;self.port=18789 if family=='openclaw' else 18790;self.process=None;self.command=[];self.persistent_namespace=persistent_namespace;self.allow_disk_warning=bool(allow_disk_warning)
  if self.allow_disk_warning and getattr(relay,'inference_authorized',False):raise ValueError('Diagnostic-warning admission is restricted to zero-inference operator fixtures; paid task/performance profiles keep their original readiness contract')
  state=self.run/'state'
  p=state/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=read_config(p)
  if family=='openclaw':
   g=c.setdefault('gateway',{});g.update(mode='local',bind='loopback',port=self.port);g.setdefault('auth',{}).update(mode='token',token='synthetic-evaluation-token');g.setdefault('controlUi',{})['enabled']=False;g.setdefault('http',{}).setdefault('endpoints',{}).setdefault('chatCompletions',{})['enabled']=True;c['agents']['defaults']['maxConcurrent']=concurrency
   cmd=['node','/runtime/openclaw/node_modules/openclaw/openclaw.mjs','gateway','run','--bind','loopback','--port',str(self.port)]
   env={'OPENCLAW_SKIP_CHANNELS':'1'}
  else:
   c.setdefault('gateway',{}).setdefault('api_server',{})['max_concurrent_runs']=concurrency
   # The task's explicit synthetic-workspace authorization has to apply to
   # this entry as well as the CLI. Explicit approval/deny fixtures override it.
   c.setdefault('approvals',{}).setdefault('unattended_mode','approve')
   cmd=['bash','-c','cd /runtime/hermes-source; task_activation="$(python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes gateway run']
   env={'API_SERVER_ENABLED':'true','API_SERVER_KEY':'synthetic-evaluation-token','API_SERVER_HOST':'127.0.0.1','API_SERVER_PORT':str(self.port),'API_SERVER_MODEL_NAME':'deepseek-flash'}
  save(p,c);env['EVAL_CONTROL_PORT']=str(self.port);self.native_command=cmd
  if persistent_namespace:
   if getattr(relay,'inference_authorized',False):raise ValueError('Private crash-control namespace is only for deterministic no-model fixtures')
   if relocated:raise ValueError('Persistent crash harness and path relocation are separate experiments')
   extra_mounts=[*extra_mounts,(R/'scripts/gateway_supervisor.py','/bootstrap/gateway_supervisor.py',True)];cmd=['python3','/bootstrap/gateway_supervisor.py',json.dumps(cmd),str(self.port)]
  if relocated:
   from relocation import rebind_configuration,sandbox_relocated
   rebind_configuration(state,family);args=sandbox_relocated(state,self.run/'workspace',family,cmd,relay.socket_dir,extra_mounts)
  else:args=sandbox(state,self.run/'workspace',family,cmd,relay.socket_dir,extra_mounts)
  idx=args.index('--');insert=[]
  for k,v in env.items():insert+=['--setenv',k,v]
  self.command=args[:idx]+insert+args[idx:];save(self.run/'gateway-launch.json',dict(command=self.command,entry='official gateway run',synthetic_control_credential=True))
 def raw(self,method,path,body=None,headers=None,timeout=950):
  conn=Control(self.run/'state/control.sock',timeout);h={'Authorization':'Bearer synthetic-evaluation-token','Content-Type':'application/json'};h.update(headers or {})
  try:
   conn.request(method,path,json.dumps(body,ensure_ascii=False).encode() if body is not None else None,h);res=conn.getresponse();payload=res.read();return res.status,dict(res.getheaders()),payload
  finally:conn.close()
 def harness(self,method,path,body=None,timeout=15):
  if not self.persistent_namespace:raise RuntimeError('Persistent namespace control not enabled')
  conn=Control(self.run/'state/harness.sock',timeout)
  try:
   conn.request(method,path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'});response=conn.getresponse();return json.loads(response.read())
  finally:conn.close()
 def owner_status(self):
  if self.persistent_namespace:return self.harness('GET','/status')
  return dict(owner_started=self.process is not None,owner_returncode=self.process.poll() if self.process else None)
 def owner_alive(self):
  try:
   status=self.owner_status();alive=status.get('owner_started') and status.get('owner_returncode') is None
   return alive and bool(status.get('listening_owner_pids')) if self.persistent_namespace else alive
  except (OSError,http.client.HTTPException):return False
 def owner_signal(self,signal_number,pid=None):
  before=self.owner_status();body={'signal':int(signal_number)}
  if pid is not None:body['pid']=int(pid)
  result=self.harness('POST','/signal',body);save(self.run/'owner-signal.json',dict(before=before,response=result,signal=int(signal_number),target_pid=pid if pid is not None else before.get('owner_pid'),scope='Exact recorded native owner PID only; namespace supervisor and old tool children are not signalled.'));return before
 def wait_ready(self):
  deadline=self.started+75;probes=[];self.readiness_attempt=getattr(self,'readiness_attempt',0)+1
  while time.monotonic()<deadline:
   if self.process.poll() is not None:raise RuntimeError('Namespace exited during startup; inspect '+str(self.run/'gateway.log'))
   if self.persistent_namespace:
    try:
     status=self.owner_status()
     if status.get('owner_started') and status.get('owner_returncode') is not None:raise RuntimeError('Native Gateway owner exited during startup')
    except (OSError,http.client.HTTPException):pass
   try:
    ready=True
    for path in (['/startupz','/readyz'] if self.family=='openclaw' else ['/health/detailed']):
     status,_,raw=self.raw('GET',path,timeout=2)
     try:body=json.loads(raw)
     except ValueError:body={'raw':raw.decode(errors='replace')}
     probes.append(dict(path=path,status=status,body=body,seconds=time.monotonic()-self.started))
     healthy=status==200 and (self.family!='hermes' or body.get('status')=='ok')
     if not healthy and self.allow_disk_warning and self.family=='hermes' and status==200 and body.get('status')=='degraded':
      checks=body.get('readiness',{}).get('checks',{});disk=checks.get('disk',{});core_ok=bool(checks) and all(v.get('status')=='ok' for k,v in checks.items() if k!='disk')
      if core_ok and disk.get('status')=='degraded' and disk.get('free_bytes',0)>=2*1024**3:
       healthy=True;probes[-1]['evaluator_admission_note']='Native HTTP200 usable API; all core checks ok; disk-only diagnostic warning retained, free space >=2GiB. No native threshold/source change; zero-inference operator fixture only.'
     if not healthy:
      ready=False;break
    if ready:
     self.ready=time.monotonic();save(self.run/f'native-readiness-{self.readiness_attempt}.json',dict(ready=True,seconds=self.ready-self.started,probes=probes));return self
   except (OSError,http.client.HTTPException):pass
   time.sleep(.2)
  save(self.run/f'native-readiness-{self.readiness_attempt}.json',dict(ready=False,probes=probes));raise RuntimeError('Gateway readiness timeout')
 def start(self):
  self.started=time.monotonic()
  if self.persistent_namespace and self.process and self.process.poll() is None:self.harness('POST','/start');return self.wait_ready()
  self.log=(self.run/'gateway.log').open('a');self.process=subprocess.Popen(self.command,stdout=self.log,stderr=self.log,start_new_session=True,stdin=subprocess.DEVNULL);return self.wait_ready()
 def restart_owner(self):
  if not self.persistent_namespace:raise RuntimeError('Owner-only restart requires a persistent evaluator namespace')
  self.started=time.monotonic();self.harness('POST','/start');return self.wait_ready()
 def pause_owner(self,label='normal-owner-stop'):
  if not self.persistent_namespace:raise RuntimeError('Normal shared-namespace handoff requires persistent evaluator namespace')
  status=self.owner_status();targets=status.get('listening_owner_pids',[])
  if len(targets)!=1:raise RuntimeError('Cannot identify sole native owner for normal handoff')
  self.owner_signal(signal.SIGTERM,targets[0]);until=time.monotonic()+30
  while time.monotonic()<until:
   status=self.owner_status()
   if status.get('owner_returncode') is not None and not status.get('listening_owner_pids'):save(self.run/(label+'.json'),status);return status
   time.sleep(.1)
  raise RuntimeError('Native owner did not settle normal shutdown before exclusive CLI handoff')
 def native_session_key(self,key):return 'agent:main:eval:'+key.strip().lower() if self.family=='openclaw' else key
 def native_session_id(self,key):return 'eval-'+hashlib.sha256(key.encode()).hexdigest()[:32] if self.family=='hermes' else None
 def chat(self,prompt,session_key=None,timeout=950,stream=False):
  session_key=session_key or 'eval-'+uuid.uuid4().hex;body={'model':'openclaw' if self.family=='openclaw' else 'deepseek-flash','messages':[{'role':'user','content':prompt}],'user':session_key,'stream':stream};headers={}
  if self.family=='hermes':headers.update({'X-Hermes-Session-Key':session_key,'X-Hermes-Session-Id':self.native_session_id(session_key)})
  else:headers['x-openclaw-session-key']=self.native_session_key(session_key)
  begin=time.monotonic();status,h,raw=self.raw('POST','/v1/chat/completions',body,headers,timeout)
  try:value=json.loads(raw)
  except ValueError:value={'raw':raw.decode(errors='replace')}
  return dict(status=status,headers=h,response=value,seconds=time.monotonic()-begin,session_key=session_key,native_session_key=self.native_session_key(session_key),native_session_id=self.native_session_id(session_key))
 def stop(self,hard=False):
  if self.process and self.process.poll() is None:
   if self.persistent_namespace and not hard:
    try:self.harness('POST','/shutdown',timeout=3)
    except (OSError,http.client.HTTPException):pass
   else:os.killpg(self.process.pid,signal.SIGKILL if hard else signal.SIGTERM)
   try:self.process.wait(timeout=15)
   except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait()
  if hasattr(self,'log'):self.log.close()
 def __enter__(self):return self.start()
 def __exit__(self,*a):self.stop()
