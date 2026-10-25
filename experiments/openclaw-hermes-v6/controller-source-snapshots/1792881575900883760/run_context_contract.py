"""K02 negative context-limit error contract on the actual common Chat entry.
No real inference. Observe reasoning fields without requiring vendor-specific
opaque signatures; explicit safe failure and correct retry are distinct outcomes.
"""
import json,os,re,subprocess,time
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan,shell
class Context(Plan):
 def __init__(self,*a,unit,**kw):self.unit=unit;self.fault_sent=False;self.issued=False;super().__init__(*a,**kw)
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_POST(self):
    b=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));names=[t.get('function',{}).get('name','') for t in b.get('tools',[])];text=json.dumps(b.get('messages',[]),ensure_ascii=False);goal='CTX_GOAL_U'+str(owner.unit);effect='CTX_EFFECT_U'+str(owner.unit);calls=[];content='Controlled summary: '+goal if goal in text else 'Current goal was not present in the supplied context.';fault=bool(names) and not owner.fault_sent
    if fault:owner.fault_sent=True
    elif names:
     if goal not in text:content='MODEL_CANNOT_IDENTIFY_CURRENT_GOAL'
     elif not owner.issued:
      owner.issued=True;calls=shell('python3 /workspace/probe.py')(names,b)
     else:content='CTX_COMPLETE_U'+str(owner.unit) if any(effect in json.dumps(m,ensure_ascii=False) for m in b.get('messages',[]) if m.get('role')=='tool') else 'MODEL_HAS_NO_EFFECT_RECEIPT'
    with owner.lock:owner.calls.append(dict(path=self.path,main=bool(names),request=b,context_limit_injected=fault,returned_calls=calls,goal_present=goal in text));save(owner.run/'context-wire-requests.json',owner.calls)
    if fault:return self.send({'error':{'message':'This request exceeds the maximum context length (controlled context_length_exceeded).','type':'invalid_request_error','code':'context_length_exceeded'}},400)
    toolcalls=[{'id':'ctx'+str(owner.unit)+str(i),'type':'function','function':{'name':n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(calls)];reason='tool_calls' if calls else 'stop';message={'role':'assistant','content':None if calls else content,'reasoning_content':'CTX_THINKING_FIELD'}
    if toolcalls:message['tool_calls']=toolcalls
    usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
    if not b.get('stream'):return self.send({'id':'context-contract','object':'chat.completion','created':int(time.time()),'model':'deepseek-flash','choices':[{'index':0,'message':message,'finish_reason':reason}],'usage':usage})
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();deltas=[{'role':'assistant','reasoning_content':'CTX_THINKING_FIELD'}, {'tool_calls':[dict(index=i,**v) for i,v in enumerate(toolcalls)]} if toolcalls else {'content':content},{}]
    try:
     for i,d in enumerate(deltas):self.wfile.write(('data: '+json.dumps({'id':'context-contract','object':'chat.completion.chunk','created':int(time.time()),'model':'deepseek-flash','choices':[{'index':0,'delta':d,'finish_reason':reason if i==2 else None}],'usage':usage if i==2 else None})+'\n\n').encode())
     self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  return H

def one(unit,family):
 run=R/'runs-context-contract'/f'u{unit}'/family
 if(run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial context-contract fixture retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('CTX_GOAL_U'+str(unit)+'：执行本地 /workspace/probe.py，在收到它的执行回执后完成，不要重复执行。');(work/'probe.py').write_text("from pathlib import Path\np=Path('/workspace/COUNT');p.write_text(str(int(p.read_text())+1) if p.exists() else '1')\nprint('CTX_EFFECT_U"+str(unit)+"')\n")
 if family=='hermes':
  p=run/'state/hermes/config.yaml';c=json.loads(p.read_text());c['background_review']={'enabled':False};save(p,c)
 fixture=Context(run,family,unit=unit);print('CONTEXT_CONTRACT_START',unit,family,flush=True)
 try:
  with(run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(sandbox(run/'state',work,family,command(family),fixture.socket_dir),stdout=out,stderr=err,timeout=150)
  output=(run/'stdout.jsonl').read_text();stderr=(run/'stderr.log').read_text();parsed=[]
  for line in output.splitlines():
   try:parsed.append(json.loads(line))
   except ValueError:pass
  if family=='openclaw':
   try:j=json.loads(output);visible='\n'.join(str(x.get('text','')) for x in j.get('payloads',[]))+str(j.get('error',''))
   except ValueError:visible=output
  else:
   final=[x for x in parsed if x.get('type') in ['result','error']];visible=json.dumps(final[-1],ensure_ascii=False) if final else output
  count=int((work/'COUNT').read_text()) if(work/'COUNT').exists() else 0;done=count==1 and 'CTX_COMPLETE_U'+str(unit) in visible;explicit=not done and count==0 and bool(re.search(r'context_length_exceeded|maximum context length|context.*(limit|overflow|exceed)',visible if p.returncode==0 else visible+'\n'+stderr,re.I));rec=dict(unit=unit,family=family,exit_code=p.returncode,context_error_actually_injected=fixture.fault_sent,effect_count=count,completed_after_context_error=done,explicit_context_failure_without_effect=explicit,main_requests=sum(x['main'] for x in fixture.calls),real_model=False,scope='Current Chat protocol only: one standard provider context_length_exceeded response before any effect, then normal responses. Correct retry with actual receipt or explicit failure is valid; no claim of the true upstream token capacity or all vendor-specific thinking signatures.')
  rec['passed']=fixture.fault_sent and (done or explicit) and count<=1;save(run/'result.json',rec);print('CONTEXT_CONTRACT_DONE',unit,family,rec['passed'],done,explicit,flush=True)
  if not rec['passed']:raise RuntimeError('Context error contract needs native output/fixture adjudication before expansion')
  return rec
 finally:fixture.close()

def main():
 from stage_provenance import snapshot
 snapshot('current-chat-context-error-contract-K02');os.chdir(OLD);rows=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):rows.append(one(unit,family));save(R/'results/context-contract.json',rows)
 print('CONTEXT_CONTRACT_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
