"""Trusted E08 transport with changed in-namespace state/workspace/home paths and UID/GID.
No product source modifications; immutable runtime caches are mounted under the new paths.
"""
import hashlib,json
from pathlib import Path
from runtime import R,OLD,sandbox,save,read_config
STATE='/moved-state';WORK='/newworkspace'
def prepare_entry():
 source=(OLD/'namespace_entry.py').read_text();source=source.replace('active_forwards = 0',"EVAL_STATE = Path(os.environ.get('EVAL_BOOTSTRAP_STATE', '/state'))\nactive_forwards = 0")
 for name in ['control.sock','isolation_check.json','network_drain.json']:source=source.replace("'/state/"+name+"'", "str(EVAL_STATE / '"+name+"')")
 source=source.replace("'/workspace/PROMPT.md'", "str(Path(os.environ.get('EVAL_BOOTSTRAP_WORKSPACE', '/workspace')) / 'PROMPT.md')")
 target=R/'scripts/namespace_entry_relocated.py'
 if not target.exists() or target.read_text()!=source:target.write_text(source)
 return target

def sandbox_relocated(state,workspace,family,command,relay_dir=None,extra_mounts=()):
 state=Path(state);(state/'user-home').mkdir(exist_ok=True)
 # These are explicitly regenerable dependency activation facts, not conversation/workspace state.
 for facts in (state/'hermes/installs').glob('*/facts.json') if (state/'hermes/installs').exists() else []:
  source=facts.read_text();facts.write_text(source.replace('/state/hermes/',STATE+'/hermes/'))
 original=sandbox(state,workspace,family,command,relay_dir,extra_mounts);at=original.index('--');options=original[:at];mapped=[]
 def path(value):
  if value=='/state' or value.startswith('/state/'):return STATE+value[len('/state'):]
  if value=='/workspace' or value.startswith('/workspace/'):return WORK+value[len('/workspace'):]
  return value
 for arg in options:mapped.append(path(arg))
 cmd=[arg.replace('/state/',STATE+'/').replace('/workspace',WORK) for arg in original[at+1:]]
 mapped+=['--uid','1000','--gid','1000','--setenv','HOME',STATE+'/user-home','--setenv','EVAL_BOOTSTRAP_STATE',STATE,'--setenv','EVAL_BOOTSTRAP_WORKSPACE',WORK,'--ro-bind',str(prepare_entry()),'/bootstrap/namespace_entry.py']
 save(state/'relocation-layout.json',dict(state=STATE,workspace=WORK,home=STATE+'/user-home',uid=1000,gid=1000,original_layout={'state':'/state','workspace':'/workspace','home':'/root','uid':0,'gid':0},scope='New Linux namespace/user-visible paths and user identity; no claim of cross-OS migration. Shared immutable dependencies are reactivated, not copied machine virtual environments.'))
 return mapped+['--']+cmd

def rebind_configuration(state,family):
 p=Path(state)/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=read_config(p)
 if family=='openclaw':
  c.setdefault('agents',{}).setdefault('defaults',{})['workspace']=WORK
  for entry in c.get('agents',{}).get('entries',{}).values():
   if entry.get('workspace')=='/workspace':entry['workspace']=WORK
   if str(entry.get('agentDir','')).startswith('/state/'):entry['agentDir']=STATE+entry['agentDir'][len('/state'):]
 else:c.setdefault('terminal',{})['cwd']=WORK
 save(p,c)
