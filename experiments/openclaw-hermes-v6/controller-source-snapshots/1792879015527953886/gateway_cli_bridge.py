"""Public evaluator transport only: CLI talks to the existing namespace gateway via Unix socket."""
import json,select,socket,socketserver,subprocess,sys,threading
class H(socketserver.BaseRequestHandler):
 def handle(self):
  upstream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
  try:
   upstream.connect('/gateway-control.sock')
   while True:
    ready,_,_=select.select([self.request,upstream],[],[],30)
    if not ready:return
    for source in ready:
     b=source.recv(65536)
     if not b:return
     (upstream if source is self.request else self.request).sendall(b)
  finally:upstream.close()
class S(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
server=S(('127.0.0.1',int(sys.argv[1])),H);threading.Thread(target=server.serve_forever,daemon=True).start()
try:result=subprocess.run(json.loads(sys.argv[2]));raise SystemExit(result.returncode)
finally:server.shutdown()
