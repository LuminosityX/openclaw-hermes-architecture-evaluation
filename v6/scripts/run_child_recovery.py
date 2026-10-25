"""Native child-result handoff fault. Public terminal hooks gate after durable child output.
A marker alone never establishes recovery: require child output in native state and exactly one child execution.
"""
import concurrent.futures,json,os,subprocess,threading,time,shlex,uuid
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save
from controlled import Plan
from gateway import Gateway
from run_recovery import stop_owner
from run_state_ops import cli,db_inventory
from run_approvals import oc_cli
OC_HOOK=r'''
import fs from 'node:fs';export default {id:'childgate',register(api){api.on('subagent_ended',async event=>{fs.writeFileSync('/workspace/CHILD_TERMINAL_GATE.json',JSON.stringify(event));if(!fs.existsSync('/workspace/FAULT_HAS_HAPPENED'))await new Promise(resolve=>{let t=setInterval(()=>{if(fs.existsSync('/workspace/FAULT_HAS_HAPPENED')){clearInterval(t);resolve();}},100);});});}};
'''
H_HOOK=r'''
import json,time
from pathlib import Path
def ended(**data):
 Path('/workspace/CHILD_TERMINAL_GATE.json').write_text(json.dumps(data,default=str))
 while not Path('/workspace/FAULT_HAS_HAPPENED').exists():time.sleep(.05)
def register(ctx):ctx.register_hook('subagent_stop',ended)
'''
class Children(Plan):
 def __init__(self,*a,unit=1,**kw):self.unit=unit;self.child_steps={};self.parent_starts=0;self.parent_finals=0;super().__init__(*a,**kw)
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));names=[t.get('function',{}).get('name','') for t in body.get('tools',[])];messages=body.get('messages',[]);user='\n'.join(str(m.get('content','')) for m in messages if m.get('role')=='user');child='CHILD_WORK_' in user and 'PARENT_WORK_' not in user;results=[m for m in messages if m.get('role')=='tool'];calls=[];text='controlled auxiliary'
    if names:
     if child:
      if not results:
       shell=next((n for n in names if n in ['exec','terminal']),None)
       if not shell:raise RuntimeError('Child shell not available in positive recovery fixture')
       args={'command':'python3 /workspace/child.py','background':False}
       if shell=='exec':args.update(awaitResults=True,yieldMs=10000)
       calls=[(shell,args)]
      else:text='CHILD_RESULT_OK_U'+str(owner.unit)
     elif any('CHILD_RESULT_OK_U'+str(owner.unit) in str(m.get('content','')) for m in messages):text='PARENT_FINISHED_U'+str(owner.unit);owner.parent_finals+=1
     elif not results:
      if 'delegate_task' in names:calls=[('delegate_task',{'tasks':[{'goal':'CHILD_WORK_U'+str(owner.unit)+' Execute the controlled child.py once and return its outcome.','context':'Working directory /workspace. This is a synthetic child-result recovery test.'}]})]
      else:
       spawn=next((n for n in names if n in ['sessions_spawn','spawn_agent']),None)
       if not spawn:raise RuntimeError('Native delegation tool not advertised')
       args={'task':'CHILD_WORK_U'+str(owner.unit)+' Execute the controlled child.py once and return its outcome.','runtime':'subagent','mode':'run','context':'isolated','cleanup':'keep','runTimeoutSeconds':90,'completionTarget':'parent'}
       if spawn=='spawn_agent':args={'message':args['task']}
       calls=[(spawn,args)]
      owner.parent_starts+=1
     elif 'sessions_yield' in names:calls=[('sessions_yield',{})]
     else:text='PARENT_WAITING_FOR_CHILD'
    encoded=[{'id':'childfixture-'+str(len(owner.calls))+'-'+str(i),'type':'function','function':{'name':name,'arguments':json.dumps(args)}} for i,(name,args) in enumerate(calls)]
    with owner.lock:owner.calls.append(dict(time_ns=time.monotonic_ns(),main=bool(names),is_child=child,request=body,returned_calls=encoded,returned_text=text if not calls else None));save(owner.run/'child-fixture-requests.json',owner.calls)
    msg={'role':'assistant','content':None if encoded else text,'reasoning_content':''};reason='tool_calls' if encoded else 'stop'
    if encoded:msg['tool_calls']=encoded
    if not body.get('stream'):return self.send({'id':'childfixture','object':'chat.completion','model':'deepseek-flash','created':int(time.time()),'choices':[{'index':0,'message':msg,'finish_reason':reason}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}})
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();delta={'role':'assistant','reasoning_content':''}
    if encoded:delta['tool_calls']=[dict(index=i,**x) for i,x in enumerate(encoded)]
    else:delta['content']=text
    try:
     for d,f in [(delta,None),({},reason)]:self.wfile.write(('data: '+json.dumps({'id':'childfixture','object':'chat.completion.chunk','model':'deepseek-flash','created':int(time.time()),'choices':[{'index':0,'delta':d,'finish_reason':f}]})+'\n\n').encode())
     self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  return H

def install_gate(run,family):
 p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text())
 if family=='openclaw':
  root=run/'state/plugins/childgate';root.mkdir(parents=True);save(root/'package.json',{'name':'childgate','version':'1.0.0','type':'module','openclaw':{'extensions':['./index.js']}});save(root/'openclaw.plugin.json',{'id':'childgate','activation':{'onStartup':True},'configSchema':{'type':'object','properties':{},'additionalProperties':False}});(root/'index.js').write_text(OC_HOOK);c['plugins']={'allow':['childgate'],'load':{'paths':['/state/plugins/childgate']},'entries':{'childgate':{'enabled':True}}};c['tools']={'toolSearch':False,'exec':{'mode':'full'},'alsoAllow':['sessions_spawn','sessions_yield','subagents']}
 else:
  root=run/'state/hermes/plugins/childgate';root.mkdir(parents=True);save(root/'plugin.yaml',dict(name='childgate',version='1.0.0',description='Controlled native child terminal handoff gate'));(root/'__init__.py').write_text(H_HOOK);c['plugins']={'enabled':['childgate'],'isolation':'in_process'};c['tools']={'tool_search':{'enabled':'off'}};c['delegation'].update(max_concurrent_children=2);c['platform_toolsets']={'api_server':['terminal','delegation']}
 save(p,c)
 if family=='openclaw':
  cmd=sandbox(run/'state',run/'workspace',family,cli(family,['plugins','install','--force','--accept-capabilities','--link','/state/plugins/childgate']));r=subprocess.run(cmd,capture_output=True,text=True,timeout=90);save(run/'gate-install.json',dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
  if r.returncode:raise RuntimeError('Native terminal hook plugin not installed')

def run_case(unit,family,inject=True,manual_followup=False):
 label='fault' if inject else 'positive';run=R/('runs-child-recovery-native-resume' if manual_followup else 'runs-child-recovery-native')/label/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial child handoff retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled native child handoff recovery.');(work/'child.py').write_text("from pathlib import Path\nwith Path('/workspace/child-executions.jsonl').open('a') as f:f.write('CHILD_EXECUTED\\n')\nprint('CHILD_TOOL_DONE')\n")
 if not inject:(work/'FAULT_HAS_HAPPENED').write_text('positive control: no fault')
 install_gate(run,family);fixture=Children(run,family,unit=unit);extra=[(R/'scripts/native_parent_ui.py','/probe/native_parent_ui.py',True),(R/'scripts/native_parent_resume.py','/probe/native_parent_resume.py',True)] if family=='hermes' else [];gateway=Gateway(run,family,fixture,persistent_namespace=True,extra_mounts=extra);pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);session='agent:main:main' if family=='openclaw' else 'child-handoff-u'+str(unit);rec=dict(unit=unit,family=family,inject=inject,real_model=False,manual_followup_enabled=manual_followup)
 print('CHILD_HANDOFF_START',label,unit,family,flush=True)
 try:
  gateway.start();prompt='PARENT_WORK_U'+str(unit)+' Delegate the controlled child work, then report the child result exactly once after it is available.'
  if family=='openclaw':
   admission=oc_cli(gateway,['gateway','call','chat.send','--params',json.dumps({'sessionKey':session,'message':prompt,'idempotencyKey':uuid.uuid4().hex,'deliver':False}),'--json'],'native-parent-admit');save(run/'native-parent-admission.json',admission)
  else:
   script='cd /runtime/hermes-source; task_activation="$(python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /probe/native_parent_ui.py '+shlex.quote(prompt);future=pool.submit(gateway.harness,'POST','/exec',{'command':['bash','-c',script],'timeout':180},timeout=190)
  until=time.monotonic()+90
  while not(work/'CHILD_TERMINAL_GATE.json').exists() and time.monotonic()<until:time.sleep(.1)
  if not(work/'CHILD_TERMINAL_GATE.json').exists():raise RuntimeError('Native child terminal hook did not fire; inspect delegation entry/toolsets before injecting')
  gate=json.loads((work/'CHILD_TERMINAL_GATE.json').read_text());inventory=db_inventory(run/'state','CHILD_RESULT_OK_U'+str(unit));save(run/'state-at-child-terminal.json',inventory);durable=any(x.get('token_hits') for x in inventory);rec.update(terminal_gate=gate,child_result_durable_before_fault=durable)
  if not durable:raise RuntimeError('Hook is before durable child result; move to a later native handoff seam before fault injection')
  if inject:
   parent_before=db_inventory(run/'state','PARENT_FINISHED_U'+str(unit));save(run/'parent-state-before-fault.json',parent_before)
   if fixture.parent_finals or any(row.get('token_hits') for row in parent_before):raise RuntimeError('Parent already consumed/completed the child result before the gate; this handoff seam is invalid, do not inject or credit recovery')
   rec['parent_not_completed_before_fault']=True
   stop_owner(gateway);(work/'FAULT_HAS_HAPPENED').write_text('owner fault has been applied; future terminal hooks do not block');gateway.restart_owner()
  until=time.monotonic()+30;parent_token='PARENT_FINISHED_U'+str(unit);after=[]
  while time.monotonic()<until:
   if fixture.parent_finals:
    after=db_inventory(run/'state',parent_token)
    if any(x.get('token_hits') for x in after):break
   time.sleep(.2)
  automatic=any(x.get('token_hits') for x in after);count=len((work/'child-executions.jsonl').read_text().splitlines()) if (work/'child-executions.jsonl').exists() else 0
  retained=db_inventory(run/'state','CHILD_RESULT_OK_U'+str(unit));save(run/'child-result-after-restart-audit.json',retained);rec['child_result_retained_after_restart']=any(row.get('token_hits') for row in retained);manual_started=time.monotonic();intervention={}
  if manual_followup and not automatic:
   if family=='hermes':
    admission=json.loads((run/'state/native-parent-admission.json').read_text());sid=admission['native_session_id'];child_sid=gate.get('child_session_id')
    if count!=1 or not rec['child_result_retained_after_restart'] or not child_sid:raise RuntimeError('Do not confirm an unknown parent before independent completed-child verification')
    verification={'child_execution_count':count,'child_result_retained':True,'child_completed_at_native_terminal_hook':True,'owner_fault':json.loads((run/'owner-fault.json').read_text())};save(run/'operator-child-completion-verification.json',verification)
    script='cd /runtime/hermes-source; task_activation="$(python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /probe/native_parent_resume.py '+shlex.join([sid,child_sid,parent_token,'operator-verified-completed-child']);intervention=gateway.harness('POST','/exec',{'command':['bash','-c',script],'timeout':80},timeout=90);save(run/'native-standard-resume-client.json',intervention)
   else:
    intervention=oc_cli(gateway,['gateway','call','chat.send','--params',json.dumps({'sessionKey':session,'message':'Continue the existing parent task and consume the completed child result; do not launch the child again.','idempotencyKey':uuid.uuid4().hex,'deliver':False}),'--json'],'native-standard-parent-resume')
   until=time.monotonic()+5
   while time.monotonic()<until:
    after=db_inventory(run/'state',parent_token)
    if any(row.get('token_hits') for row in after):break
    time.sleep(.2)
  completed_after_manual=automatic or any(row.get('token_hits') for row in after);count=len((work/'child-executions.jsonl').read_text().splitlines()) if (work/'child-executions.jsonl').exists() else 0
  rec.update(parent_finished_durably=automatic,completed_after_standard_resume=completed_after_manual,manual_resume_seconds=time.monotonic()-manual_started if intervention else None,manual_intervention=intervention,child_execution_count=count,child_relaunched=count>1,parent_dispatch_calls=fixture.parent_starts,parent_result_provider_responses=fixture.parent_finals,scope='Native terminal hook confirms child output already durable, then owner crashes before the blocked handoff returns. OpenClaw native operator chat.send and Hermes native canonical CLI session.create/prompt.submit run on the real already-started full Gateway. No model continuation in the automatic window; optional standard client reattachment, verified unknown acknowledgment and explicit continuation are separate operator interventions. No child-result text is injected by the evaluator.')
  save(run/'result.json',rec);print('CHILD_HANDOFF_DONE',label,unit,family,automatic,count,flush=True)
  if not inject and not(automatic and count==1):raise RuntimeError('Positive complete child workflow failed; do not grade fault outcomes before fixing entry/continuation')
  return rec
 finally:gateway.stop();fixture.close();pool.shutdown(wait=False,cancel_futures=True)
def main():
 os.chdir(OLD);results=[]
 for family in ['openclaw','hermes']:run_case(0,family,False)
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,family));save(R/'results/child-recovery.json',results)
 print('CHILD_HANDOFF_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
