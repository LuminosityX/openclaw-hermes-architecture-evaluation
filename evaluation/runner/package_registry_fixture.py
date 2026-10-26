"""Tiny owned npm dependency registry; no public package or external network."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
import tarfile
import threading
import time
from urllib.parse import urlsplit

DEPENDENCY='eval-owned-dependency'
PLUGIN='eval-owned-reconstruction'
VERSION='1.0.0'


def archive(files):
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as output:
        for name,content in sorted(files.items()):
            raw=content.encode();entry=tarfile.TarInfo('package/'+name);entry.size=len(raw);entry.mtime=0;entry.mode=0o644
            output.addfile(entry,io.BytesIO(raw))
    return buffer.getvalue()


def dependency_archive():
    return archive({'package.json':json.dumps(dict(name=DEPENDENCY,version=VERSION,type='module',exports='./index.js')),
        'index.js':"export const dependencyVersion='OWNED_DEPENDENCY_1.0.0';\n"})


def plugin_archive():
    source="""import {dependencyVersion} from 'eval-owned-dependency';
export default {id:'eval-owned-reconstruction',name:'Owned dependency reconstruction',register(api){
 api.registerTool({name:'dependency_probe',description:'Report the actually imported owned dependency and commit one owned receipt.',parameters:{type:'object',properties:{token:{type:'string'}},required:['token']},
 async execute(id,args){const r=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,dependency_version:dependencyVersion,pid:process.pid})});
 return {content:[{type:'text',text:dependencyVersion+' '+JSON.stringify(await r.json())}]};}});
}};
"""
    return archive({'package.json':json.dumps(dict(name=PLUGIN,version=VERSION,type='module',dependencies={DEPENDENCY:VERSION},openclaw=dict(extensions=['./index.js']))),
        'openclaw.plugin.json':json.dumps(dict(id=PLUGIN,name='Owned reconstruction fixture',activation=dict(onStartup=True),contracts=dict(tools=['dependency_probe']),configSchema=dict(type='object',properties={},additionalProperties=False))),
        'index.js':source})


class PackageRegistry:
    def __init__(self):
        self.raw=dependency_archive();self.mode='healthy';self.events=[];self.lock=threading.Lock();self.tarball_started=threading.Event();self.release=threading.Event();self.release.set()
        self.server=ThreadingHTTPServer(('127.0.0.1',18091),self.handler());self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def event(self,**values):
        with self.lock:self.events.append(dict(monotonic_ns=time.monotonic_ns(),**values))

    def handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,status,raw,kind='application/json'):
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                path=urlsplit(self.path).path;mode=owner.mode;owner.event(path=path,mode=mode)
                if mode=='offline':return self.send(503,b'{"error":"OWNED_REGISTRY_OFFLINE"}')
                if path=='/'+DEPENDENCY:
                    if mode=='missing':return self.send(404,b'{"error":"OWNED_DEPENDENCY_MISSING"}')
                    integrity='sha512-'+base64.b64encode(hashlib.sha512(b'incorrect' if mode=='checksum' else owner.raw).digest()).decode()
                    version=dict(name=DEPENDENCY,version=VERSION,type='module',exports='./index.js',dist=dict(tarball='http://127.0.0.1:18091/'+DEPENDENCY+'/-/'+DEPENDENCY+'-'+VERSION+'.tgz',integrity=integrity,shasum=hashlib.sha1(owner.raw).hexdigest()))
                    data=dict(name=DEPENDENCY,**{'dist-tags':{'latest':VERSION}},versions={VERSION:version})
                    return self.send(200,json.dumps(data).encode())
                if path.endswith('/'+DEPENDENCY+'-'+VERSION+'.tgz'):
                    owner.tarball_started.set()
                    if mode=='gate':owner.release.wait(timeout=45)
                    if mode=='partial':
                        self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(len(owner.raw)));self.end_headers();self.wfile.write(owner.raw[:len(owner.raw)//2]);self.wfile.flush();self.close_connection=True;return
                    try:return self.send(200,owner.raw,'application/octet-stream')
                    except (BrokenPipeError,ConnectionResetError):return
                return self.send(404,b'{"error":"ONLY_OWNED_FIXTURE_PACKAGE_EXISTS"}')
        return Handler

    def close(self):self.release.set();self.server.shutdown();self.server.server_close()
