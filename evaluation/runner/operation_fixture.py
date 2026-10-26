"""Scripted public tool plans. Oracles inspect actual tool returns and OS receipts."""
import hashlib
import io
import json
import re

import protocol_cases
import service_path_cases


class OperationFixture(service_path_cases.InstrumentedFixture):
    def __init__(self):
        self.plans={};self.tool_returns={}
        super().__init__()

    def plan(self,token,tool,arguments,expected):
        self.register(token)
        self.plans[token]=dict(tool=tool,arguments=arguments,expected=expected)

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path=='/fault':
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=16384:return self.send(dict(error='fixture-bound'),413)
                    body=json.loads(self.rfile.read(size))
                    if body.get('token') not in owner.tasks:return self.send(dict(error='unregistered-task'),400)
                    owner.event('fault-start',**body)
                    return self.send(dict(observed=True))
                if not self.path.endswith('/chat/completions'):return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024**2:return self.send(dict(error='fixture-bound'),413)
                raw=self.rfile.read(size);body=json.loads(raw)
                users=[(i,re.search(r'PILOT_[A-Z0-9_]+',str(m.get('content','')))) for i,m in enumerate(body.get('messages',[])) if m.get('role')=='user']
                marked=[(i,m.group()) for i,m in users if m]
                index,token=marked[-1] if marked else (0,None)
                if token not in owner.plans:
                    original=self.rfile;self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                plan=owner.plans[token]
                results=[m for m in body.get('messages',[])[index+1:] if m.get('role')=='tool']
                names=[t.get('function',{}).get('name') for t in body.get('tools',[])]
                owner.event('native-operation-provider-request',token=token,tool=plan['tool'],tool_results=len(results),
                    advertised_tools=names,request_sha256=hashlib.sha256(raw).hexdigest())
                if results:
                    owner.tool_returns[token]=results
                    visible=plan['expected'] in json.dumps(results,ensure_ascii=False)
                    script=dict(status=200,content=('ACCEPTED:' if visible else 'INCOMPLETE:')+token,finish='stop')
                else:
                    tool=plan['tool'];arguments=plan['arguments']
                    if tool not in names and 'tool_call' in names:
                        arguments=dict(id=tool,args=arguments);tool='tool_call'
                    script=dict(status=200,tool_name=tool,arguments=json.dumps(arguments),finish='tool_calls')
                if not body.get('stream'):
                    message=dict(role='assistant',content=script.get('content'))
                    if script.get('tool_name'):message['tool_calls']=[dict(id='op_'+hashlib.sha256(token.encode()).hexdigest()[:16],
                        type='function',function=dict(name=script['tool_name'],arguments=script['arguments']))]
                    return self.send(dict(id='operation-fixture',object='chat.completion',model='fixture-model',
                        choices=[dict(index=0,message=message,finish_reason=script['finish'])],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)))
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                try:
                    for frame in protocol_cases.completion_frames(script,token):
                        self.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass
        return Handler
