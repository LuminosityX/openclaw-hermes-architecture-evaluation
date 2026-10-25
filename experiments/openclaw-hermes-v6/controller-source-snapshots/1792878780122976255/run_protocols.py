"""Fixed wire-contract fixtures for Chat, Anthropic and Responses; native products execute the tools."""
import json,os,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan,shell
class Wire(Plan):
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_POST(self):
    anthropic=self.path.rstrip('/').endswith('/messages');responses=self.path.rstrip('/').endswith('/responses')
    if not(anthropic or responses):return super().do_POST()
    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));schemas=body.get('tools',[]);names=[s.get('name',s.get('function',{}).get('name','')) for s in schemas];calls=[];index=owner.index
    if names:
     owner.index+=1
     if index<len(owner.steps):calls=owner.steps[index](names,body)
    with owner.lock:owner.calls.append(dict(path=self.path,time_ns=time.monotonic_ns(),main=bool(names),request=body,returned_calls=calls));save(owner.run/'wire-requests.json',owner.calls)
    text='WIRE_COMPLETE_中文 🧪';events=[];result={}
    if anthropic:
     blocks=[{'type':'tool_use','id':f'wire_{index}_{j}','name':name,'input':args} for j,(name,args) in enumerate(calls)] if calls else [{'type':'text','text':text}];stop='tool_use' if calls else 'end_turn';result={'id':'msg_wire_'+str(index),'type':'message','role':'assistant','model':'deepseek-flash','content':blocks,'stop_reason':stop,'stop_sequence':None,'usage':{'input_tokens':0,'output_tokens':0}}
     events=[('message_start',{'type':'message_start','message':{**result,'content':[],'stop_reason':None}})]
     for j,block in enumerate(blocks):
      start={**block,'input':{}} if block['type']=='tool_use' else {**block,'text':''};delta={'type':'input_json_delta','partial_json':json.dumps(block['input'])} if block['type']=='tool_use' else {'type':'text_delta','text':block['text']}
      events+=[('content_block_start',{'type':'content_block_start','index':j,'content_block':start}),('content_block_delta',{'type':'content_block_delta','index':j,'delta':delta}),('content_block_stop',{'type':'content_block_stop','index':j})]
     events+=[('message_delta',{'type':'message_delta','delta':{'stop_reason':stop,'stop_sequence':None},'usage':{'output_tokens':0}}),('message_stop',{'type':'message_stop'})]
    else:
     output=[{'type':'function_call','id':f'fc_wire_{index}_{j}','call_id':f'call_wire_{index}_{j}','name':name,'arguments':json.dumps(args),'status':'completed'} for j,(name,args) in enumerate(calls)] if calls else [{'type':'message','id':'msg_wire_'+str(index),'role':'assistant','status':'completed','content':[{'type':'output_text','text':text,'annotations':[]}]}]
     result={'id':'resp_wire_'+str(index),'object':'response','created_at':int(time.time()),'model':'deepseek-flash','status':'completed','output':output,'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0,'input_tokens_details':{'cached_tokens':0}},'error':None,'incomplete_details':None}
     events=[('response.created',{'type':'response.created','response':{**result,'status':'in_progress','output':[],'usage':None}})]
     for j,item in enumerate(output):
      initial={**item,'arguments':''} if item['type']=='function_call' else {**item,'content':[]};events.append(('response.output_item.added',{'type':'response.output_item.added','output_index':j,'item':initial}))
      if item['type']=='function_call':events+=[('response.function_call_arguments.delta',{'type':'response.function_call_arguments.delta','item_id':item['id'],'output_index':j,'delta':item['arguments']}),('response.function_call_arguments.done',{'type':'response.function_call_arguments.done','item_id':item['id'],'output_index':j,'arguments':item['arguments']})]
      else:
       part=item['content'][0];events+=[('response.content_part.added',{'type':'response.content_part.added','item_id':item['id'],'output_index':j,'content_index':0,'part':{**part,'text':''}}),('response.output_text.delta',{'type':'response.output_text.delta','item_id':item['id'],'output_index':j,'content_index':0,'delta':text}),('response.output_text.done',{'type':'response.output_text.done','item_id':item['id'],'output_index':j,'content_index':0,'text':text}),('response.content_part.done',{'type':'response.content_part.done','item_id':item['id'],'output_index':j,'content_index':0,'part':part})]
      events.append(('response.output_item.done',{'type':'response.output_item.done','output_index':j,'item':item}))
     events.append(('response.completed',{'type':'response.completed','response':result}))
    if not body.get('stream'):return self.send(result)
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
    try:
     for seq,(name,event) in enumerate(events):
      if responses:event['sequence_number']=seq
      self.wfile.write(('event: '+name+'\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode())
     self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  return H

def run_case(unit,protocol,family):
 run=R/'runs-protocols'/protocol/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial wire attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled provider wire contract test.');(work/'deliver.py').write_text("from pathlib import Path\nPath('/workspace/DELIVERED.txt').write_text('协议兼容 🧪')\nprint('RESULT_协议兼容 🧪')\n")
 p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text());cmd=command(family)
 if family=='openclaw':
  provider=c['models']['providers']['deepseek'];provider['api']={'chat':'openai-completions','anthropic':'anthropic-messages','responses':'openai-responses'}[protocol];provider['baseUrl']='http://127.0.0.1:18080/ds/v1' if protocol!='chat' else 'http://127.0.0.1:18080/ds';provider['models'][0].pop('compat',None) if protocol!='chat' else None
 else:
  mode={'chat':'chat_completions','anthropic':'anthropic_messages','responses':'codex_responses'}[protocol];url='http://127.0.0.1:18080/ds/v1';c['model'].update(provider='fixture-api',base_url=url,api_mode=mode);c['providers']={'fixture-api':{'api':url,'api_key':'synthetic-provider-key','api_mode':mode}};cmd[-1]=cmd[-1].replace('--provider deepseek','--provider fixture-api')
 save(p,c)
 if family=='hermes' and protocol=='anthropic':
  from native_hermes_mutation_support import prepare_extra
  prepare_extra(run,'anthropic')
 fixture=Wire(run,family,[shell('python3 /workspace/deliver.py')]);args=sandbox(run/'state',work,family,cmd,fixture.socket_dir);save(run/'launch.json',dict(command=args,protocol=protocol,paid_calls=0));print('WIRE_START',protocol,unit,family,flush=True)
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(args,stdout=out,stderr=err,timeout=100)
  f=work/'DELIVERED.txt';rec=dict(unit=unit,family=family,protocol=protocol,exit_code=p.returncode,tool_effect_correct=f.exists() and f.read_text()=='协议兼容 🧪',main_requests=sum(x['main'] for x in fixture.calls),real_model=False,scope='Local wire and real tool execution only, no claim about provider model quality.')
  main_calls=[x for x in fixture.calls if x['main']];rec['observed_native_protocol_paths']=[x.get('path','chat-fixture-handler') for x in main_calls]
  rec['wire_route_verified']=bool(main_calls) and (all('messages' in x['request'] and not x.get('path') for x in main_calls) if protocol=='chat' else all(x.get('path','').rstrip('/').endswith('/messages' if protocol=='anthropic' else '/responses') for x in main_calls))
  rec['passed']=p.returncode==0 and rec['tool_effect_correct'] and rec['main_requests']>=2 and rec['wire_route_verified'];save(run/'result.json',rec);print('WIRE_DONE',protocol,unit,family,rec['passed'],flush=True)
  if not rec['passed']:raise RuntimeError('Provider adapter/wire preflight failed; inspect setup before assigning unsupported or product failure')
  return rec
 finally:fixture.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for protocol in ['chat','anthropic','responses']:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,protocol,family));save(R/'results/protocols.json',results)
 print('WIRE_CONTRACTS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
