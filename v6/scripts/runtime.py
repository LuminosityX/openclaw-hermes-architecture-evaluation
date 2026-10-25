import json,os,shutil,subprocess,sys,threading,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
OLD=Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval/work')
sys.path.insert(0,str(OLD));import pilot_coordinator as C

def save(p,d):
 p=Path(p)
 if p.name in ['launch.json','gateway-launch.json'] and isinstance(d,dict) and os.environ.get('BENCHMARK_CONTROLLER_SOURCE_SNAPSHOT'):d={**d,'controller_invocation_snapshot':os.environ['BENCHMARK_CONTROLLER_SOURCE_SNAPSHOT']}
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.{threading.get_ident()}.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2));tmp.replace(p)

def read_config(path):
 path=Path(path)
 if path.suffix in ['.yaml','.yml']:
  import yaml
  value=yaml.safe_load(path.read_text())
  if not isinstance(value,dict):raise ValueError('Expected a native configuration object')
  return value
 return json.loads(path.read_text())

def configuration(family,state):
 state.mkdir(parents=True,exist_ok=True)
 if family=='openclaw':
  C.configuration(family,state)
  p=state/'openclaw.json';c=json.loads(p.read_text());c['tools']={'exec':{'mode':'full'}}
  c['agents']['defaults']['models']['deepseek/deepseek-flash']['params']['maxTokens']=65536
  c['models']['providers']['deepseek']['models'][0]['maxTokens']=65536
 else:
  c={'model':{'default':'deepseek-flash','provider':'deepseek','base_url':'http://127.0.0.1:18080/ds/v1','context_length':1000000},'agent':{'reasoning_effort':'high','run_budget_seconds':900,'max_turns':128},'max_tokens':32768,'terminal':{'backend':'local','cwd':'/workspace'},'approvals':{'single_query_mode':'approve'},'fallback_providers':[],'delegation':{'provider':'deepseek','model':'deepseek-flash','base_url':'http://127.0.0.1:18080/ds/v1','fallback_providers':[]},'auxiliary':{}}
  for slot in ['vision','compression','title_generation','session_search','curator','background_review','approval','skills_hub','mcp','web_extract']:
   c['auxiliary'][slot]={'provider':'deepseek','model':'deepseek-flash','base_url':'http://127.0.0.1:18080/ds/v1','reasoning_effort':'high','fallback_chain':[],'extra_body':{'thinking':{'type':'enabled'}}}
  home=state/'hermes';home.mkdir(exist_ok=True)
  installs=R/'runtime/hermes-installer/installs'
  for item in installs.iterdir():
   target=home/'installs'/item.name;target.mkdir(parents=True,exist_ok=True)
   for name in ['facts.json','inputs']:
    s=item/name
    if s.is_dir():shutil.copytree(s,target/name,dirs_exist_ok=True)
    elif s.exists():shutil.copy2(s,target/name)
   f=target/'facts.json'
   if f.exists():f.write_text(f.read_text().replace('/runtime/installer-state/hermes/installs/','/state/hermes/installs/'))
   (target/'environments').mkdir(exist_ok=True)
  p=home/'config.yaml'
 if family=='hermes':c.pop('max_tokens',None)
 save(p,c)

def sandbox(state,workspace,family,command,relay_dir=None,extra_mounts=()):
 args=C.sandbox(state,workspace,relay_dir,family,command)
 index=args.index('--');added=[]
 if family=='hermes':
  added+=['--ro-bind',str(R/'runtime/hermes-stable'),'/runtime/hermes-source','--ro-bind',str(R/'runtime/hermes-tools'),'/runtime/hermes-tools','--ro-bind',str(R/'runtime/hermes-installer'),'/runtime/installer-state/hermes']
  writable=state/'benchmark-hermes-writable-installs.json'
  if writable.exists():
   allowed_roots=[R/name for name in ['runs-extensions','runs-state-ops','runs-upgrades','runs-storage-faults','runs-protocols','runs-import-compat','runs-install-rebuild','evidence/hermes-pm-mutation-preflight']]
   if not any(Path(state).resolve().is_relative_to(root) for root in allowed_roots):raise ValueError('Writable install stores are restricted to trusted operator fixtures')
   cache=Path(json.loads(writable.read_text())['cache'])
   if not cache.resolve().is_relative_to(R/'runtime') or cache.parts[-2:]!=('cache','uv'):raise ValueError('Native mutation cache is not a prepared runtime uv cache')
   added+=['--bind',str(cache),'/state/hermes/cache/uv']
  for item in (R/'runtime/hermes-installer/installs').iterdir():
   if writable.exists():continue
   if (item/'environments').exists():
    added+=['--ro-bind',str(item/'environments'),f'/state/hermes/installs/{item.name}/environments']
    for generation in (item/'environments').iterdir():
     if generation.is_dir():
      (generation/'.leases').mkdir(exist_ok=True)
      lease=state/'runtime-leases'/item.name/generation.name;lease.mkdir(parents=True,exist_ok=True)
      added+=['--bind',str(lease),f'/state/hermes/installs/{item.name}/environments/{generation.name}/.leases']
 added+=['--ro-bind',str(R/'runtime/test-wheels'),'/test-wheels']
 for src,dst,ro in extra_mounts:added+=['--ro-bind' if ro else '--bind',str(src),dst]
 if (workspace/'run_tests.py').exists():added+=['--ro-bind',str(workspace/'run_tests.py'),'/workspace/run_tests.py']
 # Public tests and protocol input assets are immutable to subject processes.
 for dirname in ['project/testing','project/tests']:
  path=workspace/dirname
  if path.exists():added+=['--ro-bind',str(path),'/workspace/'+dirname]
 return args[:index]+added+args[index:]

def command(family,prompt='/workspace/PROMPT.md',resume=None):
 if family=='openclaw':
  cmd=C.product_command(family);cmd[cmd.index('--timeout')+1]='900';cmd[cmd.index('--message-file')+1]=prompt
  return cmd
 activation='task_activation="$(python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes --usage-file /state/usage.json chat --provider deepseek --model deepseek-flash --reasoning high --query-file '+prompt+' --format stream-json --in /workspace'
 if resume:activation+=' --resume '+resume
 return ['bash','-c','cd /runtime/hermes-source; '+activation]
