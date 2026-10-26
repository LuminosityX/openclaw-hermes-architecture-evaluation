"""Actual native-core semantic fixtures on GitHub Linux and Windows hosts."""
from collections import deque
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from portable_support import owned_child_environment,stop_owned_process

TOKEN='synthetic-portable-evaluation-only'


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False)+'\n',encoding='utf8')


class PortableFixture:
    def __init__(self):
        self.plans={};self.returns={};self.events=[];self.issued=set();self.native_tool_schemas={}
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,body,status=200):
                raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024**2:return self.send(dict(error='bounded-portable-provider'),413)
                raw=self.rfile.read(size);body=json.loads(raw)
                owner.native_tool_schemas.update({t['function']['name']:t['function'].get('parameters') for t in body.get('tools',[]) if isinstance(t.get('function'),dict)})
                marked=[(i,m.group()) for i,v in enumerate(body.get('messages',[])) if v.get('role')=='user' and (m:=re.search(r'PILOT_[A-Z0-9_]+',str(v.get('content',''))))]
                index,token=marked[-1] if marked else (0,None)
                if token not in owner.plans:return self.send(dict(error=dict(message='Unregistered owned semantic operation',type='invalid_request_error')),400)
                plan=owner.plans[token];results=[v for v in body.get('messages',[])[index+1:] if v.get('role')=='tool']
                owner.events.append(dict(kind='actual-native-provider-request',token=token,tool_results=len(results),request_sha256=hashlib.sha256(raw).hexdigest(),monotonic_ns=time.monotonic_ns()))
                if results:
                    owner.returns[token]=results;matched=plan['expected'] in json.dumps(results,ensure_ascii=False)
                    message=dict(role='assistant',content=('ACCEPTED:' if matched else 'INCOMPLETE:')+token);finish='stop'
                elif token in owner.issued:
                    message=dict(role='assistant',content='REFERENCE_NOTIFICATION_OBSERVED');finish='stop'
                else:
                    owner.issued.add(token);tool=plan['tool'];arguments=plan['arguments'];names=[v.get('function',{}).get('name') for v in body.get('tools',[])]
                    if tool not in names and 'tool_call' in names:arguments=dict(id=tool,args=arguments);tool='tool_call'
                    message=dict(role='assistant',content=None,tool_calls=[dict(id='portable_'+hashlib.sha256(token.encode()).hexdigest()[:20],type='function',function=dict(name=tool,arguments=json.dumps(arguments,ensure_ascii=False)))]);finish='tool_calls'
                common=dict(id='owned-portable-'+hashlib.sha256(token.encode()).hexdigest()[:20],created=1760000000,model='fixture-model')
                if not body.get('stream'):return self.send(dict(**common,object='chat.completion',choices=[dict(index=0,message=message,finish_reason=finish)],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)))
                delta=dict(message)
                if delta.get('tool_calls'):delta['tool_calls']=[dict(index=i,**call) for i,call in enumerate(delta['tool_calls'])]
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                try:
                    for value,reason in [(delta,None),({},finish)]:self.wfile.write(('data: '+json.dumps(dict(**common,object='chat.completion.chunk',choices=[dict(index=0,delta=value,finish_reason=reason)]),ensure_ascii=False)+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):owner.events.append(dict(kind='portable-provider-peer-closed',token=token,monotonic_ns=time.monotonic_ns()))
        self.server=ThreadingHTTPServer(('127.0.0.1',18080),Handler);self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def plan(self,token,tool,arguments,expected=''):self.plans[token]=dict(tool=tool,arguments=arguments,expected=expected)
    def close(self):self.server.shutdown();self.server.server_close()


def configure(root):
    (root/'state').mkdir(parents=True);(root/'workspace').mkdir()
    (root/'workspace/public-ready.txt').write_text('OWNED_PORTABLE_READY',encoding='utf8')
    config=dict(gateway=dict(mode='local',bind='loopback',port=18789,auth=dict(mode='token',token=TOKEN),controlUi=dict(enabled=False),http=dict(endpoints=dict(chatCompletions=dict(enabled=True)))),
        models=dict(providers=dict(fixture=dict(baseUrl='http://127.0.0.1:18080/v1',apiKey='synthetic-only',api='openai-completions',models=[dict(id='fixture-model',name='Owned cross-OS semantic fixture',reasoning=False,input=['text'],contextWindow=128000,maxTokens=1024)]))),
        agents=dict(ownership='explicit',entries=dict(main=dict(workspace=str(root/'workspace'),agentDir=str(root/'state/agents/main/agent'))),defaults=dict(workspace=str(root/'workspace'),model=dict(primary='fixture/fixture-model',fallbacks=[]),skipBootstrap=True,thinkingDefault='off',sandbox=dict(mode='off'))),
        plugins=dict(enabled=False),tools=dict(allow=['read','write','exec','process'],toolSearch=False,exec=dict(host='gateway',mode='full',timeoutSeconds=20)),
        cron=dict(enabled=False),logging=dict(level='info',consoleLevel='warn',file=str(root/'native-gateway.log')))
    save(root/'config.json',config);return config


class PortableGateway:
    def __init__(self,root,node,modules,config=None,state=None):
        self.root=root;self.node=str(node);self.cli=str(modules/'openclaw/openclaw.mjs');self.config=config or configure(root);self.env=owned_child_environment(root)
        if state:self.env['OPENCLAW_STATE_DIR']=str(state)
        self.tail=deque(maxlen=100);self.guard_failure=None;self.stopped=threading.Event()
        self.process=subprocess.Popen([self.node,self.cli,'gateway','run','--bind','loopback','--port','18789'],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',start_new_session=os.name!='nt')
        self.reader=threading.Thread(target=self.read,daemon=True);self.reader.start();self.monitor=threading.Thread(target=self.watch,daemon=True);self.monitor.start()

    def read(self):
        for line in self.process.stdout:self.tail.append(line)

    def watch(self):
        while not self.stopped.wait(.2):
            try:total=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink())
            except OSError:continue
            if total>128*1024**2:
                self.guard_failure='Owned native semantic state exceeded the 128 MiB sampled disk guard';stop_owned_process(self.process);return

    def ready(self):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=.5)
            try:
                connection.request('GET','/readyz');response=connection.getresponse();response.read(4096)
                if response.status==200:return
            except (OSError,http.client.HTTPException):pass
            finally:connection.close()
            if self.process.poll() is not None:break
            time.sleep(.1)
        raise RuntimeError('Actual native '+os.name+' Gateway readiness failed: '+''.join(self.tail)[-2000:])

    def request(self,token,session):
        connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=45);started=time.monotonic_ns()
        try:
            body=json.dumps(dict(model='openclaw',stream=False,messages=[dict(role='user',content='Execute the deterministic operation for '+token)]),ensure_ascii=False).encode()
            connection.request('POST','/v1/chat/completions',body,{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN,'x-openclaw-session-key':session})
            response=connection.getresponse();raw=response.read(256*1024+1)
            if len(raw)>256*1024:raise RuntimeError('Portable native response bound')
            parsed=json.loads(raw);text=''.join(str(c.get('message',{}).get('content','')) for c in parsed.get('choices',[]))
            return dict(status=response.status,accepted='ACCEPTED:'+token in text,latency_ms=(time.monotonic_ns()-started)/1e6,response_excerpt=raw.decode(errors='replace')[:1600])
        except (OSError,ValueError,http.client.HTTPException) as error:return dict(status=None,accepted=False,error=type(error).__name__)
        finally:connection.close()

    def cli_call(self,*arguments,timeout=60):
        result=subprocess.run([self.node,self.cli,*map(str,arguments)],env=self.env,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
        return dict(arguments=list(map(str,arguments)),returncode=result.returncode,stdout=result.stdout[:262144],stderr=result.stderr[-3000:],stdout_truncated=len(result.stdout)>262144)

    def rpc(self,method,params):
        result=self.cli_call('gateway','call',method,'--params',json.dumps(params),'--json',timeout=30)
        if result['returncode']:raise RuntimeError('Actual native cross-OS RPC failed: '+json.dumps(result)[-1800:])
        try:return json.loads(result['stdout'])
        except ValueError:raise RuntimeError('Native cross-OS RPC returned no machine-readable payload')

    def history(self,session):return self.rpc('chat.history',dict(sessionKey=session,limit=100,maxBytes=131072))

    def stop(self):
        self.stopped.set();stop_owned_process(self.process);self.reader.join(timeout=2);self.monitor.join(timeout=2)
