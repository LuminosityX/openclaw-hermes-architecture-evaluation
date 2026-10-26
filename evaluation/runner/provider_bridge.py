"""Namespace-local TCP to host Unix relay; only the completion path is forwarded."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading


class UnixConnection(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__('localhost',timeout=130)
        self.path=path

    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def bridge(path='/relay/provider.sock',port=18081):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.0'
        def log_message(self,*args): pass
        def do_POST(self):
            if self.path!='/v1/chat/completions':
                self.send_error(404)
                return
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8*1024**2:
                self.send_error(413)
                return
            connection=UnixConnection(path)
            try:
                with self.server.forward_lock:self.server.forwarded_requests+=1
                connection.request('POST',self.path,self.rfile.read(size),{'Content-Type':'application/json'})
                response=connection.getresponse()
                self.send_response(response.status)
                self.send_header('Content-Type',response.getheader('Content-Type','application/json'))
                self.end_headers()
                while True:
                    chunk=response.read1(8192)
                    if not chunk: break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except OSError: pass
            finally: connection.close()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.forwarded_requests=0;server.forward_lock=threading.Lock()
    server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
