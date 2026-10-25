import json,time,threading,re
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
R=Path(__file__).resolve().parents[1];P=R/'raw/extended-resources/provider-requests.jsonl';lock=threading.Lock()
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/health':o={'status':'ok'}
  else:o={'object':'list','data':[{'id':'local-fixture','object':'model','owned_by':'fixture'}]}
  b=json.dumps(o).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  raw=self.rfile.read(int(self.headers.get('Content-Length',0)));b=json.loads(raw);ms=b.get('messages',[]);t='\n'.join(('\n'.join(x.get('text','')for x in m.get('content')if isinstance(x,dict))if isinstance(m.get('content'),list)else(m.get('content')or''))for m in ms);match=re.search('CASE:(\\w+)',t);case=match.group(1)if match else 'unknown';checks={
   'plain':len(ms)==1,'unicode':'中文测试🐱'in t,'multiline':'line one\nline two'in t,'system':any(m['role']=='system'for m in ms),
   'multiturn':len(ms)==3 and ms[1]['role']=='assistant','stream':bool(b.get('stream')),'tool':b.get('tools',[{}])[0].get('function',{}).get('name')=='lookup',
   'json':b.get('response_format',{}).get('type')=='json_object','max_tokens':b.get('max_tokens')==8,'temperature':b.get('temperature')==0}
  valid=checks.get(case,False)and self.path=='/v1/chat/completions'and b.get('model')=='local-fixture';event={'case':case,'framework':self.headers.get('X-Benchmark-Framework'),'passed':bool(valid),'path':self.path,'wire_bytes':len(raw),'body':b}
  with lock,P.open('a')as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
  content=json.dumps({'case':case,'valid':valid},ensure_ascii=False);delta={'role':'assistant','content':content}
  if case=='tool':delta={'role':'assistant','content':None,'tool_calls':[{'id':'call-fixture','type':'function','function':{'name':'lookup','arguments':'{"key":"synthetic"}'}}]}
  if b.get('stream'):
   self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
   for d,end in [(delta,None),({},'stop')]:self.wfile.write(('data: '+json.dumps({'id':'fixture','object':'chat.completion.chunk','created':int(time.time()),'model':'local-fixture','choices':[{'index':0,'delta':d,'finish_reason':end}]})+'\n\n').encode())
   self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
  else:
   o={'id':'fixture','object':'chat.completion','created':int(time.time()),'model':'local-fixture','choices':[{'index':0,'message':delta,'finish_reason':'tool_calls'if case=='tool'else'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}};data=json.dumps(o).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
s=ThreadingHTTPServer(('127.0.0.1',38773),H);print('ready 38773',flush=True);s.serve_forever()
