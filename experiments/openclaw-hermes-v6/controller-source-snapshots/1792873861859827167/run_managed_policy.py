"""Higher-precedence shell denial against lower grants; malformed mandatory policy behavior is separate.
The evaluator's read-only mount simulates administrator-owned OS configuration. It is not product-native sandbox evidence.
"""
import hashlib,json,os,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan
from run_state_ops import cli

def action(family):
 def choose(names,body):
  name='exec' if family=='openclaw' else 'terminal';args={'command':'python3 /workspace/policy_action.py','background':False}
  if family=='openclaw':args.update(awaitResults=True,yieldMs=10000)
  return [(name,args)]
 return choose

def one(unit,family,mode):
 run=R/'runs-managed-policy'/mode/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial managed-policy attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled higher-level shell policy precedence test.');(work/'policy_action.py').write_text("from pathlib import Path\nPath('/workspace/SHELL_EFFECT').write_text('executed')\nprint('EXECUTED')\n");p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text());extra=[]
 if family=='openclaw':
  c['tools']={'toolSearch':False,'exec':{'mode':'full'}};c['agents']['entries']={'main':{'tools':{'allow':['exec']}}}
  if mode=='deny':c['tools']['deny']=['exec']
  save(p,c)
  if mode=='malformed-authoritative-policy':p.write_text('{"tools": {"deny": ["exec"], invalid-json')
 else:
  c['approvals']={'mode':'off','deny':[],'single_query_mode':'approve'};c['tools']={'tool_search':{'enabled':'off'}};save(p,c);managed=run/'administrator-policy';managed.mkdir();(managed/'config.yaml').write_text('approvals:\n  deny: ["*"]\n' if mode=='deny' else 'approvals:\n  deny: [\n' if mode=='malformed-authoritative-policy' else '{}\n');extra=[(managed,'/administrator-policy',True)]
 def make(command):
  args=sandbox(run/'state',work,family,command,None,extra)
  if family=='hermes':i=args.index('--');args=args[:i]+['--setenv','HERMES_MANAGED_DIR','/administrator-policy']+args[i:]
  return args
 # Validate the declared supported policy shape through each public CLI; raw output retained.
 check=cli(family,['config','validate','--json'] if family=='openclaw' else ['config','check']);v=subprocess.run(make(check),capture_output=True,text=True,timeout=70);save(run/'native-configuration-check.json',dict(exit_code=v.returncode,stdout=v.stdout,stderr=v.stderr))
 fixture=Plan(run,family,[action(family)]);args=sandbox(run/'state',work,family,command(family),fixture.socket_dir,extra)
 if family=='hermes':i=args.index('--');args=args[:i]+['--setenv','HERMES_MANAGED_DIR','/administrator-policy']+args[i:]
 print('MANAGED_POLICY_START',unit,mode,family,flush=True)
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:r=subprocess.run(args,stdout=out,stderr=err,timeout=90)
  native_names={t.get('function',{}).get('name','') for call in fixture.calls for t in call['request'].get('tools',[])};effect=(work/'SHELL_EFFECT').exists();rec=dict(unit=unit,family=family,mode=mode,exit_code=r.returncode,shell_advertised=('exec' if family=='openclaw' else 'terminal') in native_names,shell_effect_executed=effect,main_provider_calls=sum(x['main'] for x in fixture.calls),config_check_exit=v.returncode,scope='Global tool deny vs per-agent allow on OpenClaw; system managed deny vs user approve/off on Hermes. OS protection of administrator files is evaluator scaffolding, not a native sandbox claim. Malformed-layer fallback is reported with native warnings and is not automatically an undocumented bypass.')
  rec['expected_policy_held']=effect if mode=='allow' else not effect;save(run/'result.json',rec);print('MANAGED_POLICY_DONE',unit,mode,family,effect,flush=True)
  if mode in ['allow','deny'] and not rec['expected_policy_held']:raise RuntimeError('Valid policy/positive control needs adjudication before expansion; retain outcome')
  return rec
 finally:fixture.close()
def main():
 from run_native_budget_capability import main as check_native_budget
 check_native_budget()
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for mode in ['allow','deny','malformed-authoritative-policy']:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(one(unit,family,mode));save(R/'results/managed-policy.json',results)
 print('MANAGED_POLICY_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
