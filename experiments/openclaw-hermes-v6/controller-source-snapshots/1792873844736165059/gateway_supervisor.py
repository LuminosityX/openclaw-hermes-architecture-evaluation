"""Evaluator-only persistent namespace owner for precise service-owner crash tests.
Private Unix control; no grading/answers. Killing the product owner does not implicitly kill the namespace or its old tool children.
"""
import json,os,signal,socketserver,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
command=json.loads(sys.argv[1]);target_port=int(sys.argv[2]) if len(sys.argv)>2 else None;child=None;lock=threading.RLock();done=threading.Event();last_signalled_pid=None
def alive(pid):
 try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
 except OSError:return False
def owned_descendants():
 if child is None:return []
 todo=[child.pid];result=[]
 while todo:
  pid=todo.pop();result.append(pid)
  try:todo.extend(map(int,Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
  except OSError:pass
 return result
def listening_owners():
 if target_port is None:return []
 sockets=set()
 for table in ['/proc/net/tcp','/proc/net/tcp6']:
  try:
   for line in Path(table).read_text().splitlines()[1:]:
    fields=line.split()
    if len(fields)>9 and fields[3]=='0A' and int(fields[1].rsplit(':',1)[1],16)==target_port:sockets.add('socket:['+fields[9]+']')
  except OSError:pass
 owners=[]
 for item in Path('/proc').iterdir():
  if not item.name.isdigit():continue
  try:
   for fd in (item/'fd').iterdir():
    try:match=os.readlink(fd) in sockets
    except OSError:continue
    if match:owners.append(int(item.name));break
  except OSError:pass
 return sorted(owners)
def status():
 with lock:
  pid=child.pid if child else None;code=child.poll() if child else None;command=None
  if pid is not None and code is None:
   try:command=Path(f'/proc/{pid}/cmdline').read_bytes().replace(bytes([0]),b' ').decode(errors='replace')[:240]
   except OSError:pass
  return dict(owner_pid=pid,owner_returncode=code,owner_started=child is not None,supervisor_pid=os.getpid(),pid_namespace=os.readlink('/proc/self/ns/pid'),owner_command=command,listening_owner_pids=listening_owners(),owned_descendant_pids=owned_descendants(),last_signalled_pid=last_signalled_pid,last_signalled_pid_alive=alive(last_signalled_pid) if last_signalled_pid else None)

def start():
 global child
 with lock:
  if child and child.poll() is None:return status()
  child=subprocess.Popen(command,stdin=subprocess.DEVNULL,start_new_session=True);return status()
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.0'
 def log_message(self,*a):pass
 def emit(self,data,code=200):
  b=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):self.emit(status())
 def do_POST(self):
  global last_signalled_pid
  body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
  if self.path=='/start':return self.emit(start())
  if self.path=='/signal':
   with lock:
    target=int(body['pid']) if body.get('pid') is not None else child.pid if child else None
    if target is not None and target not in owned_descendants():return self.emit({'error':'Signal target is not an owned product descendant'},400)
    if target is not None and alive(target):os.kill(target,int(body.get('signal',signal.SIGTERM)));last_signalled_pid=target
   return self.emit(status())
  if self.path=='/exec':
   argv=body.get('command');timeout=min(300,max(1,float(body.get('timeout',90))))
   if not isinstance(argv,list) or not argv or not all(isinstance(x,str) for x in argv) or argv[0] not in ['python3','/usr/bin/python3','node','bash']:return self.emit({'error':'invalid deterministic-controller command'},400)
   proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
   try:out,err=proc.communicate(timeout=timeout)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate();return self.emit({'exit_code':proc.returncode,'stdout':out[-1000000:],'stderr':err[-100000:],'controller_timeout':True})
   return self.emit({'exit_code':proc.returncode,'stdout':out[-1000000:],'stderr':err[-100000:]})
  if self.path=='/shutdown':
   with lock:
    if child and child.poll() is None:os.kill(child.pid,signal.SIGTERM)
   self.emit(status());done.set();return
  self.emit({'error':'unknown control'},404)
socket=Path('/state/harness.sock');socket.unlink(missing_ok=True);server=Server(str(socket),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();start()
try:
 while not done.wait(.2):pass
finally:
 if child and child.poll() is None:
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:
   os.kill(child.pid,signal.SIGKILL);child.wait()
 server.shutdown();server.server_close();socket.unlink(missing_ok=True)
