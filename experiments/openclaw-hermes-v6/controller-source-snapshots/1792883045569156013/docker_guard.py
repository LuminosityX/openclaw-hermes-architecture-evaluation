"""Evaluator-only Docker proxy: translate task mounts and scope IDs, never product isolation evidence."""
import http.client,json,os,re,select,socket,socketserver,threading,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
ENGINE='/root/output/openclaw-hermes-benchmark-20261022/runtime/docker/docker.sock'
IMAGE='python:3.12-slim-bookworm'
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
class UnixHTTP(http.client.HTTPConnection):
 def __init__(self):super().__init__('localhost',timeout=120)
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect(ENGINE)
class EventLog(list):
 def __init__(self,path):super().__init__();self.path=Path(path);self.lock=threading.Lock()
 def append(self,value):
  value=dict(at_ns=time.monotonic_ns(),**value)
  with self.lock:
   super().append(value);self.path.parent.mkdir(parents=True,exist_ok=True)
   with self.path.open('a') as f:f.write(json.dumps(value)+'\n')
class DockerGuard:
 def __init__(self,path,mappings):
  self.path=Path(path);self.mappings={str(k):str(Path(v).resolve()) for k,v in mappings.items()};self.ids=set();self.names=set();self.execs=set();log_path=Path(self.mappings['/workspace']).parent/'docker-guard-live.jsonl' if '/workspace' in self.mappings else self.path.with_suffix('.events.jsonl');self.events=EventLog(log_path);self.path.unlink(missing_ok=True);self.server=Server(str(self.path),self.handler());threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def translate(self,p):
  for source,target in sorted(self.mappings.items(),key=lambda x:-len(x[0])):
   if p==source or p.startswith(source+'/'):
    out=os.path.realpath(target+p[len(source):])
    if out==target or out.startswith(target+'/'):return out
  raise ValueError('Mount outside synthetic task domain: '+p)
 def handler(self):
  owner=self
  class H(socketserver.BaseRequestHandler):
   def handle(self):
    conn=self.request;raw=b''
    while b'\r\n\r\n' not in raw:
     b=conn.recv(65536)
     if not b:return
     raw+=b
     if len(raw)>4000000:return
    head,body=raw.split(b'\r\n\r\n',1);lines=head.decode('latin1').split('\r\n');method,path,_=lines[0].split(' ',2);headers={k:v.strip() for k,v in (l.split(':',1) for l in lines[1:] if ':' in l)};length=int(next((v for k,v in headers.items() if k.lower()=='content-length'),'0'))
    owner.events.append(dict(method=method,path=path,request_framing={k.lower():v for k,v in headers.items() if k.lower() in ['content-length','transfer-encoding','connection','upgrade']},initial_body_bytes=len(body),blocked=None))
    while len(body)<length:
     b=conn.recv(min(65536,length-len(body)))
     if not b:return
     body+=b
    route=re.sub(r'^/v[0-9.]+','',unquote(urlsplit(path).path));reason=None;capture=None;d=None;local_absence=False
    try:
     if route=='/containers/create':
      d=json.loads(body[:length]);h=d.get('HostConfig') or {};d['HostConfig']=h
      # Hermes probes cgroup delegation with an unmounted sleep0 container. Force that evaluator-only probe offline.
      if d.get('Cmd')==['sleep','0'] and not d.get('Entrypoint') and not h.get('Binds') and not h.get('Mounts'):
       h['NetworkMode']='none';d['HostConfig']=h;d['NetworkingConfig']={'EndpointsConfig':{}};owner.events.append(dict(method=method,path=path,evaluator_only_probe_network='none',blocked=None))
      if h.get('Privileged') or h.get('PidMode')=='host' or h.get('IpcMode')=='host' or h.get('NetworkMode') not in [None,'none']:raise ValueError('Forbidden namespace/privilege')
      h['Binds']=[owner.translate(b.split(':',1)[0])+':'+b.split(':',1)[1] for b in (h.get('Binds') or [])]
      for m in (h.get('Mounts') or []):
       if m.get('Type')!='bind':raise ValueError('Only synthetic bind mounts allowed')
       m['Source']=owner.translate(m.get('Source',''))
      if h.get('Devices') or any(c.upper().removeprefix('CAP_') not in ['CHOWN','FOWNER','DAC_OVERRIDE','SETUID','SETGID'] for c in (h.get('CapAdd') or [])):raise ValueError('Forbidden host capability')
      if d.get('Image')!=IMAGE:raise ValueError('Unapproved image')
      if h.get('VolumesFrom') or h.get('DeviceRequests') or h.get('SecurityOpt') and any('unconfined' in x for x in h['SecurityOpt']):raise ValueError('Forbidden host access')
      body=json.dumps(d).encode();capture='container'
     elif route=='/containers/json':
      filters=json.loads(parse_qs(urlsplit(path).query).get('filters',['{}'])[0]);filters['id']=list(owner.ids) or ['__no_owned_container__'];from urllib.parse import urlencode
      q=parse_qs(urlsplit(path).query);q['filters']=[json.dumps(filters)];path=urlsplit(path).path+'?'+urlencode({k:v[0] for k,v in q.items()})
     elif route.startswith('/containers/'):
      key=route.split('/')[2]
      if key not in owner.names and not any(identifier==key or len(key)>=12 and identifier.startswith(key) for identifier in owner.ids):
       if method=='GET' and route.endswith('/json'):local_absence=True
       else:raise ValueError('Container outside this experiment')
      if route.endswith('/exec'):capture='exec'
     elif route.startswith('/exec/'):
      key=route.split('/')[2]
      if not any(identifier==key or len(key)>=12 and identifier.startswith(key) for identifier in owner.execs):raise ValueError('Exec outside experiment')
     elif route.startswith('/images/') and route.endswith('/json') and method=='GET':
      # `docker inspect name` tries a container and then an image with that
      # name. An unowned lookup is absent in this private view, never forwarded.
      if route[len('/images/'):-len('/json')]!=IMAGE:local_absence=True
     elif method=='GET' and any(route.startswith(prefix) for prefix in ['/networks/','/volumes/','/services/','/tasks/','/nodes/','/configs/','/secrets/','/plugins/']):
      # Generic Docker inspection walks several object kinds. This experiment
      # owns none of these objects, so expose only local absence, never host data.
      local_absence=True
     elif route not in ['/_ping','/version','/info']:raise ValueError('Unused Docker endpoint')
    except Exception as e:reason=str(e)
    owner.events.append(dict(method=method,path=path,blocked=reason,synthetic_no_owned_container=local_absence))
    def send(status,headers,payload):
     text=http.client.responses.get(status,'Result');conn.sendall(f'HTTP/1.1 {status} {text}\r\n'.encode()+b''.join((k+': '+v+'\r\n').encode('latin1') for k,v in headers)+b'Content-Length: '+str(len(payload)).encode()+b'\r\nConnection: close\r\n\r\n'+payload)
    if reason:return send(403,[('Content-Type','application/json')],json.dumps({'message':reason}).encode())
    if local_absence:return send(404,[('Content-Type','application/json')],json.dumps({'message':'No such Docker object in this experiment'}).encode())
    headers={k:v for k,v in headers.items() if k.lower() not in ['host','connection','content-length']};headers['Content-Length']=str(len(body))
    hijack=route.endswith('/start') and route.startswith('/exec/') or '/attach' in route
    if hijack:
     upstream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
     try:
      upstream.connect(ENGINE);headers['Connection']='Upgrade';headers['Upgrade']='tcp';upstream.sendall((method+' '+path+' HTTP/1.1\r\nHost: localhost\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode('latin1')+body)
      channels=[conn,upstream]
      while channels:
       ready,_,_=select.select(channels,[],[],60)
       if not ready:return
       for src in ready:
        b=src.recv(65536);destination=upstream if src is conn else conn
        if not b:
         channels.remove(src)
         try:destination.shutdown(socket.SHUT_WR)
         except OSError:pass
         continue
        destination.sendall(b)
     finally:upstream.close()
    else:
     client=UnixHTTP()
     try:
      client.request(method,path,body,headers);response=client.getresponse()
      if route.startswith('/containers/') and route.endswith('/wait'):
       # Docker's SDK subscribes to wait before it sends start. It needs the
       # response HEADERS immediately; buffering until exit deadlocks that flow.
       owner.events.append(dict(method=method,path=path,response_status=response.status,streamed_wait_headers=True,blocked=None))
       status_text=http.client.responses.get(response.status,'Result');h=[(k,v) for k,v in response.getheaders() if k.lower() not in ['content-length','transfer-encoding','connection','trailer']]
       conn.sendall(f'HTTP/1.1 {response.status} {status_text}\r\n'.encode()+b''.join((k+': '+v+'\r\n').encode('latin1') for k,v in h)+b'Connection: close\r\n\r\n')
       while True:
        chunk=response.read1(65536)
        if not chunk:break
        conn.sendall(chunk)
       return
      payload=response.read();owner.events.append(dict(method=method,path=path,response_status=response.status,error_preview=payload.decode(errors='replace')[:1200] if response.status>=400 else None,blocked=None))
      if capture and response.status<300:
       value=json.loads(payload);identifier=value.get('Id')
       if identifier:
        (owner.ids if capture=='container' else owner.execs).add(identifier)
        if capture=='container':
         name=parse_qs(urlsplit(path).query).get('name',[''])[0]
         if name:owner.names.add(name)
      send(response.status,[(k,v) for k,v in response.getheaders() if k.lower() not in ['content-length','transfer-encoding','connection']],payload)
     finally:client.close()
  return H
 def close(self):self.server.shutdown();self.server.server_close();self.path.unlink(missing_ok=True)
