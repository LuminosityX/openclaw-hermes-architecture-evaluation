"""Forward to the user's real DeepSeek service; optionally inject one real HTTP failure."""
import json,sys,time,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import requests
OLD=Path('/root/output/openclaw-hermes-benchmark-20261022')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(OLD/'scripts'))
from configure_deepseek import configured_key
KEY=configured_key()
if not KEY:raise SystemExit('DeepSeek credential is not configured')
ROOT.joinpath('raw').mkdir(parents=True,exist_ok=True)
LOCK=threading.Lock();ACTIVE={};SEQ=0
def record(data):
    with LOCK:
        with (ROOT/'raw/provider-audit.jsonl').open('a') as f:f.write(json.dumps(data,ensure_ascii=False).replace(KEY,'[REDACTED]')+'\n')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send_json(self,status,data,headers=None):
        b=json.dumps(data).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)))
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(b)
    def do_GET(self):self.send_json(200,{'ready':True})
    def do_POST(self):
        global SEQ
        data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        if self.path=='/control':
            with LOCK:ACTIVE[data['framework']]={'run_id':data['run_id'],'fault':data.get('fault',0),'injected':False}
            return self.send_json(200,{'ok':True})
        framework=self.path.split('/')[1]
        with LOCK:
            current=ACTIVE.setdefault(framework,{'run_id':'warmup','fault':0,'injected':False});info=dict(current);SEQ+=1;request_id=SEQ
            inject=bool(current.get('fault') and not current['injected'])
            if inject:current['injected']=True
        start=time.monotonic();base={'framework':framework,'run_id':info['run_id'],'request_id':request_id,'request_start':start,'model':data.get('model'),'stream':data.get('stream'),'message_count':len(data.get('messages',[])),'tool_count':len(data.get('tools',[])),'request_chars':len(json.dumps(data,ensure_ascii=False))}
        if inject:
            record({**base,'status':info['fault'],'injected':True,'end':time.monotonic()})
            return self.send_json(info['fault'],{'error':{'type':'rate_limit_error' if info['fault']==429 else 'server_error','message':'Benchmark injected transient HTTP failure; next request forwards to real DeepSeek'}},{'Retry-After':'1'})
        data['model']='deepseek-flash';data['temperature']=0;data['thinking']={'type':'disabled'};data.pop('reasoning_effort',None)
        if data.get('stream'):data['stream_options']={'include_usage':True}
        chunks=[];first=None;status=None
        try:
            with requests.post('https://api.deepseek.com/chat/completions',json=data,headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'},stream=True,timeout=(15,120)) as upstream:
                status=upstream.status_code;self.send_response(status);self.send_header('Content-Type',upstream.headers.get('Content-Type','application/json'));self.end_headers()
                for chunk in upstream.iter_content(chunk_size=None):
                    if not chunk:continue
                    if first is None:first=time.monotonic()
                    chunks.append(chunk)
                    try:self.wfile.write(chunk);self.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError):pass
            raw=b''.join(chunks).decode('utf-8','replace');usage={};texts=[];tools=[]
            if data.get('stream'):
                for line in raw.splitlines():
                    if line.startswith('data: ') and line[6:]!='[DONE]':
                        try:
                            part=json.loads(line[6:]);usage=part.get('usage')or usage
                            for c in part.get('choices',[]):
                                delta=c.get('delta',{});texts.append(delta.get('content')or '');tools.extend(delta.get('tool_calls')or [])
                        except (ValueError,TypeError):pass
            else:
                try:
                    response=json.loads(raw);usage=response.get('usage')or {}
                    for c in response.get('choices',[]):
                        m=c.get('message',{});texts.append(m.get('content')or '');tools.extend(m.get('tool_calls')or [])
                except ValueError:pass
            record({**base,'status':status,'injected':False,'first_provider_byte':first,'end':time.monotonic(),'usage':usage,'response_text':''.join(texts),'tool_call_fragments':len(tools),'request_messages':data.get('messages',[])})
        except Exception as exc:
            record({**base,'status':status,'end':time.monotonic(),'error_type':type(exc).__name__})
            if status is None:
                try:self.send_json(502,{'error':{'message':'Upstream transport failed','type':type(exc).__name__}})
                except OSError:pass
print(json.dumps({'ready':True,'port':40490}),flush=True)
ThreadingHTTPServer(('127.0.0.1',40490),Handler).serve_forever()
