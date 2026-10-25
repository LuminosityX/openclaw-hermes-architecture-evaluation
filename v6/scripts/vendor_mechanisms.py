"""Native products with a deterministic protocol fixture; ZERO real model calls.
Synthetic provider only fixes tool plans. Real installed products execute real tools.
Run after paid timing tests finish, not concurrently.
"""
import json,os,shutil,socketserver,subprocess,sys,threading,time,statistics
from http.server import BaseHTTPRequestHandler
from pathlib import Path
R=Path(__file__).resolve().parents[1];OLD=Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval/work')
sys.path.insert(0,str(OLD));import pilot_coordinator as C
sys.path.insert(0,str(R/'scripts'));from run_pairs import save
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True

class Fixture:
 def __init__(self,run,family,kind):
  self.run,self.family,self.kind=run,family,kind;self.calls=[];self.main_calls=0;self.fault_sent_ns=None;self.retry_seen_ns=None;self.record_lock=threading.Lock()
  self.socket_dir=R/'evidence'/f'socket-{family}-{kind}';self.socket_dir.mkdir(exist_ok=True)
  socket=self.socket_dir/'api.sock';socket.unlink(missing_ok=True)
  self.server=Server(str(socket),self.handler());threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def handler(self):
  owner=self
  class H(BaseHTTPRequestHandler):
   protocol_version='HTTP/1.0'
   def log_message(self,*args):pass
   def send_json(self,d,status=200):
    b=json.dumps(d).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
   def do_GET(self):self.send_json({'object':'list','data':[{'id':'deepseek-flash','object':'model'}]})
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
    messages=body.get('messages',[]);names=[x.get('function',{}).get('name','') for x in body.get('tools',[])]
    tool_results=[m for m in messages if m.get('role')=='tool'];calls=[]
    selected=next((n for n in names if 'bench_delay' in n),None) if owner.kind=='mcp' else next((n for n in names if n in ['exec','terminal']),None)
    # Auxiliary title requests have no tools and must not consume the test plan.
    is_main=bool(names)
    if is_main and owner.kind.startswith('retry'):
     if owner.fault_sent_ns is None:
      owner.fault_sent_ns=time.monotonic_ns();status=int(owner.kind.split('-')[1])
      with owner.record_lock:
       owner.calls.append(dict(time_ns=owner.fault_sent_ns,injected_status=status,retry_after_seconds=2,main=True))
       save(owner.run/'fixture-requests.json',owner.calls)
      b=json.dumps({'error':{'message':'Controlled transient fault; retry after 2 seconds','type':'rate_limit_error' if status==429 else 'server_error'}}).encode()
      self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Retry-After','2');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
     elif owner.retry_seen_ns is None:owner.retry_seen_ns=time.monotonic_ns()
    if is_main:
     index=owner.main_calls;owner.main_calls+=1
     if owner.kind=='mcp':
      plan=[1]*6+[4]*6+[8]*6
      if index<len(plan) and selected:
       count=plan[index]
       for j in range(count):
        args=dict(run_id=f'batch-{index}',id=j,delay_ms=200)
        calls.append(dict(id=f'call_{index}_{j}',type='function',function=dict(name=selected,arguments=json.dumps(args))))
     elif owner.kind=='timeout' and index<10 and selected:
      i=index//2;cmd=f'python3 /workspace/heartbeat.py /workspace/beat-{i}' if index%2==0 else f'python3 /workspace/observe.py /workspace/beat-{i}'
      args={'command':cmd}
      if selected=='exec':args.update(timeoutSeconds=1 if index%2==0 else 5,awaitResults=True,yieldMs=10000)
      else:args.update(timeout=1 if index%2==0 else 5,background=False)
      calls=[dict(id=f'call_{index}',type='function',function=dict(name=selected,arguments=json.dumps(args)))]
     elif owner.kind.startswith('deny') and index==0:
      name=selected or ('exec' if owner.family=='openclaw' else 'terminal')
      args={'command':'python3 -c "from pathlib import Path; Path(\'/workspace/DENIED_SIDE_EFFECT\').write_text(\'bad\')"'}
      calls=[dict(id='call_denied',type='function',function=dict(name=name,arguments=json.dumps(args)))]
     elif owner.kind.startswith('plugin') and index<3:
      if index<2:
       desired='probe_identity' if index==0 else 'probe_crash';name=next((n for n in names if n.endswith(desired)),None)
       if name:calls=[dict(id=f'plugin_{index}',type='function',function=dict(name=name,arguments='{}'))]
      elif selected:
       calls=[dict(id='after_plugin',type='function',function=dict(name=selected,arguments=json.dumps({'command':'python3 /workspace/survivor.py'})))]
     elif owner.kind=='authorization-parity' and index<4:
      commands=["python3 -c \"from pathlib import Path; Path('/workspace/inline.probe').write_text('ok')\"","python3 - <<'PY'\nfrom pathlib import Path\nPath('/workspace/heredoc.probe').write_text('ok')\nPY","rm -r /workspace/scratch-remove","python3 /workspace/api-code-probe.py"]
      name=selected
      if index==3 and owner.family=='hermes' and 'execute_code' in names:
       name='execute_code';args={'code':"from pathlib import Path\nPath('/workspace/api-code.probe').write_text('ok')\nprint('ok')"}
      else:args={'command':commands[index]}
      if name:calls=[dict(id=f'parity_{index}',type='function',function=dict(name=name,arguments=json.dumps(args)))]
    with owner.record_lock:
     owner.calls.append(dict(time_ns=time.monotonic_ns(),selected_tool=selected,tools=names,returned_calls=len(calls),tool_results=tool_results,main=is_main))
     save(owner.run/'fixture-requests.json',owner.calls)
    final=json.dumps(dict(fixture=True,kind=owner.kind,seen_results=len(tool_results)))
    if owner.kind=='scale':
     import re
     tokens=re.findall(r'SCALE_[a-f0-9]+',json.dumps(messages))
     final=tokens[-1] if tokens else 'synthetic auxiliary response'
     if tokens:time.sleep(.25)
    msg={'role':'assistant','content':None if calls else final,'reasoning_content':''}
    if calls:msg['tool_calls']=calls
    reason='tool_calls' if calls else 'stop'
    if not body.get('stream'):
     self.send_json(dict(id='fixture-completion',object='chat.completion',model='deepseek-flash',created=int(time.time()),choices=[dict(index=0,message=msg,finish_reason=reason)],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)));return
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
    delta={'role':'assistant','reasoning_content':''}
    if calls:delta['tool_calls']=[dict(index=i,**x) for i,x in enumerate(calls)]
    else:delta['content']=final
    try:
     for d,finish in [(delta,None),({},reason)]:
      chunk=dict(id='fixture-completion',object='chat.completion.chunk',created=int(time.time()),model='deepseek-flash',choices=[dict(index=0,delta=d,finish_reason=finish)])
      self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
     self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  return H
 def close(self):self.server.shutdown();self.server.server_close();(self.socket_dir/'api.sock').unlink(missing_ok=True)

def setup(run,family,kind):
 state=run/'state';state.mkdir();work=run/'workspace';work.mkdir();C.configuration(family,state)
 (work/'PROMPT.md').write_text('Controlled native tool integration test. Follow the supplied tool plan; no real model is used.\n')
 src=Path('/root/output/openclaw-hermes-benchmark-20261022/scripts/mcp_fixture.py').read_text().replace('ROOT = Path(__file__).resolve().parents[1]','ROOT = Path("/workspace")')
 (work/'raw').mkdir();(work/'mcp_fixture.py').write_text(src)
 shutil.copy('/root/output/openclaw-hermes-nonfunctional-20261022/scripts/heartbeat.py',work/'heartbeat.py')
 (work/'survivor.py').write_text("from pathlib import Path\nPath('/workspace/SURVIVED').write_text('ok')\nprint('SURVIVED')\n")
 (work/'api-code-probe.py').write_text("from pathlib import Path\nPath('/workspace/api-code.probe').write_text('ok')\nprint('ok')\n")
 if kind=='authorization-parity':
  (work/'scratch-remove').mkdir();(work/'scratch-remove/leaf').write_text('Synthetic permission positive control only')
 (work/'observe.py').write_text('''import json,time,sys
from pathlib import Path
p=Path(sys.argv[1]);pids=json.loads(Path(str(p)+'.pids').read_text()) if Path(str(p)+'.pids').exists() else []
def alive(pid):
 try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
 except OSError:return False
b=Path(str(p)+'.beat');before=b.read_text() if b.exists() else None;time.sleep(.3);after=b.read_text() if b.exists() else None
result=dict(started=len(pids)==2,survivors=[pid for pid in pids if alive(pid)],heartbeat_continued=before!=after)
Path(str(p)+'.observed.json').write_text(json.dumps(result));print(json.dumps(result))
''')
 if family=='openclaw':
  p=state/'openclaw.json';cfg=json.loads(p.read_text());cfg['tools']={'toolSearch':False}
  if kind=='mcp':
   cfg['mcp']={'servers':{'bench':{'command':'/usr/bin/python3','args':['/workspace/mcp_fixture.py'],'transport':'stdio','enabled':True,'supportsParallelToolCalls':True,'connectionTimeoutMs':5000,'requestTimeoutMs':5000}}};cfg['tools']['alsoAllow']=['bench__bench_delay']
  if kind.startswith('deny'):cfg['tools']['exec']={'security':'deny','ask':'off'} if 'legacy' in kind else {'mode':'deny'}
  if kind=='authorization-parity':cfg['tools']['exec']={'mode':'full'}
  if kind.startswith('plugin'):
   plugin=state/'plugins/crashprobe';plugin.mkdir(parents=True)
   save(plugin/'openclaw.plugin.json',dict(id='crashprobe',name='Controlled crash probe',activation={'onStartup':True},contracts={'tools':['probe_identity','probe_crash']},configSchema={'type':'object','properties':{},'additionalProperties':False}))
   save(plugin/'package.json',{'name':'controlled-crashprobe','version':'1.0.0','type':'module','openclaw':{'extensions':['./index.js']}})
   (plugin/'index.js').write_text('''import fs from 'node:fs';
export default {id:'crashprobe',name:'Controlled crash probe',register(api){
 api.registerTool({name:'probe_identity',label:'Identity',description:'Return plugin PID for controlled fault isolation test',parameters:{type:'object',properties:{}},async execute(){fs.writeFileSync('/workspace/plugin-identity.json',JSON.stringify({pid:process.pid}));return {content:[{type:'text',text:JSON.stringify({pid:process.pid})}]};}});
 api.registerTool({name:'probe_crash',label:'Crash',description:'Exit only this test plugin process during the controlled test',parameters:{type:'object',properties:{}},async execute(){fs.writeFileSync('/workspace/plugin-crash-entered','yes');process.exit(42);}});
}};
''')
   cfg['plugins']={'allow':['crashprobe'],'load':{'paths':['/state/plugins/crashprobe']},'entries':{'crashprobe':{'enabled':True}}};cfg['tools']['alsoAllow']=['probe_identity','probe_crash']
 else:
  p=state/'hermes/config.yaml';cfg=json.loads(p.read_text());cfg['tools']={'tool_search':{'enabled':'off'}};cfg['background_review']={'enabled':False}
  if kind=='mcp':cfg['mcp_servers']={'bench':{'command':'/usr/bin/python3','args':['/workspace/mcp_fixture.py'],'supports_parallel_tool_calls':True,'trust':'full','lazy':False}}
  if kind=='deny':cfg['approvals']={'mode':'off','deny':['*']}
  if kind=='authorization-parity':cfg['approvals']={'single_query_mode':'approve'}
  if kind.startswith('plugin'):
   plugin=state/'hermes/plugins/crashprobe';plugin.mkdir(parents=True)
   save(plugin/'plugin.yaml',dict(name='crashprobe',version='1.0.0',description='Controlled isolated plugin crash probe',provides_tools=['probe_identity','probe_crash']))
   (plugin/'__init__.py').write_text('''import json,os
from pathlib import Path
def identity(args,**kwargs):
 d={'pid':os.getpid()};Path('/workspace/plugin-identity.json').write_text(json.dumps(d));return json.dumps(d)
def crash(args,**kwargs):
 Path('/workspace/plugin-crash-entered').write_text('yes');os._exit(42)
def register(ctx):
 for name,fn in [('probe_identity',identity),('probe_crash',crash)]:
  ctx.register_tool(name=name,toolset='crashprobe',schema={'name':name,'description':'Controlled fault isolation probe','parameters':{'type':'object','properties':{}}},handler=fn)
''')
   cfg['plugins']={'enabled':['crashprobe'],'isolation':'in_process' if kind=='plugin-in-process' else 'host'}
 save(p,cfg)

def run_one(family,kind):
 run=R/'runs-mechanisms'/kind/family
 if run.exists():raise RuntimeError('Preserve prior attempt '+str(run))
 run.mkdir(parents=True);setup(run,family,kind);fixture=Fixture(run,family,kind)
 if family=='openclaw' and kind.startswith('deny'):
  pre=subprocess.run(C.sandbox(run/'state',run/'workspace',fixture.socket_dir,family,['node','/runtime/openclaw/node_modules/openclaw/openclaw.mjs','config','validate','--json']),capture_output=True,text=True,timeout=60)
  save(run/'config-validation.json',dict(exit_code=pre.returncode,stdout=pre.stdout,stderr=pre.stderr))
  if pre.returncode:
   fixture.close();raise RuntimeError('Invalid policy fixture; do not score as product failure')
 cmd=C.product_command(family)
 if family=='openclaw' and kind.startswith('plugin'):
  # Official installer creates the native provenance/index record required for activation.
  # A config path alone is not proof that a plugin was installed or executed.
  launcher=run/'workspace/plugin_launch.py'
  launcher.write_text("import json,os,subprocess,sys\nfrom pathlib import Path\ncmd="+repr(['node','/runtime/openclaw/node_modules/openclaw/openclaw.mjs','plugins','install','--force','--accept-capabilities','--link','/state/plugins/crashprobe'])+"\nr=subprocess.run(cmd,capture_output=True,text=True)\nPath('/state/plugin-install.log').write_text(r.stdout+r.stderr)\nPath('/state/plugin-install-result.json').write_text(json.dumps({'exit_code':r.returncode}))\nif r.returncode:sys.exit(r.returncode)\nargs="+repr(cmd)+"\nos.execvp(args[0],args)\n")
  cmd=['python3','/workspace/plugin_launch.py']
 if family=='hermes' and kind=='mcp':cmd[-1]+=' --toolsets bench'
 if family=='hermes' and kind.startswith('plugin'):cmd[-1]+=' --toolsets crashprobe,terminal'
 command=C.sandbox(run/'state',run/'workspace',fixture.socket_dir,family,cmd)
 save(run/'launch.json',dict(command=command,real_model=False,paid_calls=0))
 print('MECHANISM_START',kind,family,flush=True);start=time.monotonic()
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:
   p=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
   try:code=p.wait(timeout=180)
   except subprocess.TimeoutExpired:
    import signal
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    code=p.returncode
 finally:fixture.close()
 rec=dict(family=family,kind=kind,elapsed_seconds=time.monotonic()-start,exit_code=code,real_model=False,paid_calls=0,main_provider_requests=fixture.main_calls)
 if kind=='mcp':
  path=run/'workspace/raw/tool-events.jsonl';events=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
  batches=[]
  for index in range(18):
   es=[x for x in events if x['run_id']==f'batch-{index}'];count=1 if index<6 else 4 if index<12 else 8
   starts=[x['timestamp_ns'] for x in es if x['event']=='start'];ends=[x['timestamp_ns'] for x in es if x['event']=='end'];active=maximum=0
   for x in sorted(es,key=lambda x:x['timestamp_ns']):active+=1 if x['event']=='start' else -1;maximum=max(maximum,active)
   ids=[x['id'] for x in es if x['event']=='start'];endids=[x['id'] for x in es if x['event']=='end']
   batches.append(dict(index=index,count=count,warmup=index%6==0,valid=sorted(ids)==list(range(count)) and sorted(endids)==list(range(count)) and active==0,duration_ms=(max(ends)-min(starts))/1e6 if starts and ends else None,max_overlap=maximum))
  rec.update(batches=batches,passed=all(x['valid'] for x in batches),actual_tool_events=len(events))
 elif kind=='timeout':
  obs=[json.loads(p.read_text()) for p in sorted((run/'workspace').glob('beat-*.observed.json'))]
  rec.update(observations=obs,passed=len(obs)==5 and all(x['started'] and not x['survivors'] and not x['heartbeat_continued'] for x in obs))
 elif kind.startswith('retry'):
  wait=(fixture.retry_seen_ns-fixture.fault_sent_ns)/1e9 if fixture.retry_seen_ns and fixture.fault_sent_ns else None
  rec.update(injected_status=int(kind.split('-')[1]),retry_after_seconds=2,actual_retry_wait_seconds=wait,passed=code==0 and wait is not None and wait>=1.9)
 elif kind.startswith('plugin'):
  entered=(run/'workspace/plugin-crash-entered').exists();survived=(run/'workspace/SURVIVED').exists();identity=(run/'workspace/plugin-identity.json').exists()
  rec.update(plugin_loaded_and_called=identity,crash_entered=entered,main_loop_survived=survived,passed=identity and entered and survived,valid_comparison=identity and entered)
 elif kind=='authorization-parity':
  checks={name:(run/'workspace'/name).exists() and (run/'workspace'/name).read_text()=='ok' for name in ['inline.probe','heredoc.probe','api-code.probe']};checks['scoped_remove']=not (run/'workspace/scratch-remove').exists()
  rec.update(checks=checks,passed=code==0 and all(checks.values()),scope='Equal explicit authorization inside evaluator-isolated synthetic workspace; not evidence of native security isolation')
 else:
  results=[m for c in fixture.calls for m in c['tool_results']]
  rec.update(side_effect_created=(run/'workspace/DENIED_SIDE_EFFECT').exists(),tool_results_present=bool(results),passed=bool(results) and not (run/'workspace/DENIED_SIDE_EFFECT').exists())
 save(run/'result.json',rec);print('MECHANISM_DONE',kind,family,rec['passed'],round(rec['elapsed_seconds'],2),flush=True);return rec

if __name__=='__main__':
 os.chdir(OLD)
 active=json.loads((R/'evidence/active.json').read_text())
 if active.get('pid'):raise RuntimeError('Wait for real-model timing batch to finish')
 results=[]
 for kind in ['mcp','timeout','deny','plugin-host','retry-429-r1','retry-503-r1','retry-429-r2','retry-503-r2','retry-429-r3','retry-503-r3']:
  for family in ['openclaw','hermes']:
   results.append(run_one(family,kind));save(R/'results/mechanisms.json',results)
 results.append(run_one('hermes','plugin-in-process'));save(R/'results/mechanisms.json',results)
