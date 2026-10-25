"""A deterministic OpenAI chat fixture. It specifies calls; native products execute them."""
import json,hashlib,socketserver,threading,time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from runtime import R,save
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
class Plan:
 def __init__(self,run,family,steps=(),fault=None,router=None):
  self.run=Path(run);self.family=family;self.steps=list(steps);self.calls=[];self.lock=threading.Lock();self.index=0;self.router=router;self.fault=fault;self.faulted=False;self.socket_dir=R/'evidence/sockets'/hashlib.sha256(str(run).encode()).hexdigest()[:10];self.socket_dir.mkdir(parents=True,exist_ok=True);p=self.socket_dir/'api.sock';p.unlink(missing_ok=True);self.server=Server(str(p),self.handler());threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def handler(self):
  owner=self
  class H(BaseHTTPRequestHandler):
   protocol_version='HTTP/1.0'
   def log_message(self,*a):pass
   def send(self,data,status=200):
    b=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
   def do_GET(self):self.send({'object':'list','data':[{'id':'deepseek-flash','object':'model'}]})
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));schemas=body.get('tools',[]);names=[x.get('function',{}).get('name','') for x in schemas];index=owner.index;calls=[];custom_text=None
    if names:
     owner.index+=1
     if owner.router is not None or index<len(owner.steps):
      step=owner.steps[index] if owner.router is None else owner.router;plan=step(names,body) if callable(step) else step
      if isinstance(plan,dict):custom_text=plan.get('text');plan=plan.get('calls',[])
      for j,(name,args) in enumerate(plan):calls.append({'id':f'controlled-{index}-{j}','type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}})
    with owner.lock:
     owner.calls.append(dict(time_ns=time.monotonic_ns(),index=index,main=bool(names),request=body,returned_calls=calls));save(owner.run/'controlled-requests.json',owner.calls)
    if names and owner.fault and not owner.faulted:
     owner.faulted=True
     if owner.fault in ['429','503']:
      owner.index-=1
      with owner.lock:owner.calls[-1]['injected_status']=int(owner.fault);owner.calls[-1]['returned_calls']=[];save(owner.run/'controlled-requests.json',owner.calls)
      b=json.dumps({'error':{'message':'Controlled temporary provider failure','type':'rate_limit_error' if owner.fault=='429' else 'server_error'}}).encode();self.send_response(int(owner.fault));self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.send_header('Retry-After','2');self.end_headers();self.wfile.write(b);return
     if owner.fault=='truncated_stream':
      self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();self.wfile.write(b'data: {"id":"partial","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"PARTIAL "},"finish_reason":null}]}\n\ndata: {');self.wfile.flush();self.close_connection=True;return
    content=(custom_text or 'CONTROLLED_COMPLETE') if names else 'controlled auxiliary';msg={'role':'assistant','content':None if calls else content,'reasoning_content':''};reason='tool_calls' if calls else 'stop'
    if calls:msg['tool_calls']=calls
    if not body.get('stream'):return self.send({'id':'controlled','object':'chat.completion','model':'deepseek-flash','created':int(time.time()),'choices':[{'index':0,'message':msg,'finish_reason':reason}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}})
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();delta={'role':'assistant','reasoning_content':''}
    if calls:delta['tool_calls']=[dict(index=i,**x) for i,x in enumerate(calls)]
    else:delta['content']=content
    try:
     for d,f in [(delta,None),({},reason)]:self.wfile.write(('data: '+json.dumps({'id':'controlled','object':'chat.completion.chunk','created':int(time.time()),'model':'deepseek-flash','choices':[{'index':0,'delta':d,'finish_reason':f}]})+'\n\n').encode())
     self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  return H
 def close(self):self.server.shutdown();self.server.server_close();(self.socket_dir/'api.sock').unlink(missing_ok=True)
def shell(command,**extra):
 def choose(names,body):
  name=next((n for n in names if n in ['exec','terminal']),None)
  if not name:raise RuntimeError('Native shell tool absent: '+str(names))
  args={'command':command}
  if name=='exec':args.update(awaitResults=True,yieldMs=10000)
  args.update(extra);return [(name,args)]
 return choose
