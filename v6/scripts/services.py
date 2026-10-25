import copy,json,threading,time
from urllib.parse import urlsplit,unquote,parse_qs
from audit_relay_unlimited import Relay
from runtime import save
class Business:
 def __init__(self,spec,path):self.spec=spec;self.path=path;self.billing=copy.deepcopy(spec['initial']);self.events=[];self.lock=threading.Lock()
 def reset(self):
  with self.lock:self.billing=copy.deepcopy(self.spec['initial']);self.events=[];self.persist()
 def persist(self):save(self.path,dict(billing=self.billing,events=self.events))
 def handle(self,method,path,data):
  p=urlsplit(path);route=p.path
  with self.lock:
   if method=='GET' and route=='/orders':
    n=int(parse_qs(p.query).get('cursor',['0'])[0]);rows=self.spec['orders'];return 200,dict(items=rows[n:n+17],next_cursor=n+17 if n+17<len(rows) else None)
   if method=='GET' and route=='/billing':return 200,list(self.billing.values())
   if route.startswith('/billing/'):
    key=unquote(route[len('/billing/'):])
    if method=='PUT':
     if not isinstance(data,dict) or data.get('id')!=key:return 400,{'error':'id mismatch'}
     before=self.billing.get(key);changed=before!=data
     if changed:self.billing[key]=data;self.events.append(dict(kind='put',key=key,before=before,after=data,time_ns=time.monotonic_ns()))
     self.persist();return 200,dict(changed=changed)
    if method=='DELETE':
     before=self.billing.pop(key,None)
     if before is not None:self.events.append(dict(kind='delete',key=key,before=before,time_ns=time.monotonic_ns()))
     self.persist();return 200,dict(changed=before is not None)
   return 404,{'error':'not found'}
class AuditedRelay(Relay):
 def __init__(self,*a,business=None,**kw):self.business=business;super().__init__(*a,**kw)
 def handler(self):
  Base=super().handler();owner=self
  class Handler(Base):
   def forward(self):
    if not self.path.startswith('/ds/'):
     # Local business discovery/mistyped paths are ordinary HTTP responses, not inference policy violations.
     if not owner.business or not self.path.startswith('/biz/'):
      body=b'{"error":"not found"}';self.send_response(404);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers();self.wfile.write(body);self.close_connection=True;return
     length=int(self.headers.get('Content-Length','0'))
     if length>1000000:return self.deny('Business payload too large')
     try:data=json.loads(self.rfile.read(length)) if length else None
     except ValueError:data=None
     status,result=owner.business.handle(self.command,self.path[4:],data);body=json.dumps(result,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers();self.wfile.write(body);self.close_connection=True;return
    return super().forward()
   def do_PUT(self):self.forward()
   def do_DELETE(self):self.forward()
  return Handler
