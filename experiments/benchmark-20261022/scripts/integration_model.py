import json,pathlib,re,time
from http.server import ThreadingHTTPServer
from scripted_model import Handler as Original,content_text
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Handler(Original):
 def do_POST(self):
  size=int(self.headers.get('Content-Length','0'));raw=self.rfile.read(size);body=json.loads(raw);messages=body.get('messages',[]);text='\n'.join(content_text(m.get('content')) for m in messages if m.get('role')=='user');match=re.search(r'INTEGRATION_DELEGATE_CASE=([\w-]+)',text)
  if not match:
   import io
   self.rfile=io.BytesIO(raw);return super().do_POST()
  case=match.group(1);results=[m for m in messages if m.get('role')=='tool'];names=[t['function']['name'] for t in body.get('tools',[])];name=next((n for n in names if n in ['sessions_spawn','delegate_task']),None);calls=[]
  if not results and name:
   child=f'BENCH_RUN_ID=integration-child-{case} BENCH_TOOL_COUNT=1 BENCH_DELAY_MS=0 Execute the requested terminal tool and return its result.'
   args={'task':child,'mode':'run','runtime':'subagent','cleanup':'keep','label':f'integration-{case}','runTimeoutSeconds':60} if name=='sessions_spawn' else {'goal':child,'background':False}
   calls=[{'id':f'spawn-{case}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]
  final=json.dumps({'case':case,'spawn_tool':name,'tool_results':len(results),'delegation_results':[m.get('content') for m in results]});message={'role':'assistant','content':None if calls else final};reason='tool_calls' if calls else 'stop'
  if calls:message['tool_calls']=calls
  with (ROOT/'raw/extended-integration/delegation-model.jsonl').open('a') as f:f.write(json.dumps({'case':case,'tool_names':names,'calls':calls,'tool_results':results})+'\n')
  identifier=f'chatcmpl-integration-{case}'
  if not body.get('stream'):return self.send_json({'id':identifier,'object':'chat.completion','created':int(time.time()),'model':'bench-scripted','choices':[{'index':0,'message':message,'finish_reason':reason}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}})
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();delta={'role':'assistant'}
  if calls:delta['tool_calls']=[{'index':i,**c} for i,c in enumerate(calls)]
  else:delta['content']=final
  for d,finish in [(delta,None),({},reason)]:self.wfile.write(('data: '+json.dumps({'id':identifier,'object':'chat.completion.chunk','created':int(time.time()),'model':'bench-scripted','choices':[{'index':0,'delta':d,'finish_reason':finish}]})+'\n\n').encode())
  self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
print(json.dumps({'status':'listening','port':38691}),flush=True);ThreadingHTTPServer(('127.0.0.1',38691),Handler).serve_forever()
