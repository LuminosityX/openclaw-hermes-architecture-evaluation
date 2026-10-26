"""Native provider/MCP fault adapters. Only scripted endpoints are faulted."""
import http.client
import json
import socket
import threading
import time

import pilot

SCENARIOS={
    'REL-14-S01':'fragmented-arguments',
    'REL-14-S02':'missing-usage',
    'REL-14-S03':'retry-503',
    'REL-14-S04':'opaque-reasoning',
    'REL-15-S01':'retry-429',
    'REL-15-S02':'503-then-disconnect',
    'REL-15-S03':'deadline-after-commit',
    'REL-15-S04':'fallback-unavailable',
    'REL-15-S05':'context-limit',
}


def scripted_response(scenario,token,attempt,body):
    """Versioned transcript contract, independently testable without OpenClaw."""
    mode=SCENARIOS[scenario]
    if mode=='retry-429' and attempt==1:
        return dict(status=429,retry_after='1',error='rate_limit_exceeded')
    if mode in {'retry-503','503-then-disconnect'} and attempt==1:
        return dict(status=503,error='service_unavailable')
    if mode=='503-then-disconnect' and attempt==2:
        return dict(disconnect=True)
    if mode=='fallback-unavailable':
        return dict(status=503,error='service_unavailable')
    if mode=='context-limit':
        return dict(status=400,error='context_length_exceeded')
    results=[m for m in body.get('messages',[]) if m.get('role')=='tool']
    if results:
        result_text=json.dumps(results,ensure_ascii=False)
        accepted='RECEIPT:'+token in result_text
        return dict(status=200,content=('ACCEPTED:' if accepted else 'INCOMPLETE:')+token,finish='stop')
    name='probe__eval_probe' if mode=='deadline-after-commit' else 'eval_probe'
    arguments=json.dumps(dict(token=token,action='late' if mode=='deadline-after-commit' else 'effect'),ensure_ascii=False)
    return dict(status=200,tool_name=name,arguments=arguments,finish='tool_calls',
                fragment=mode=='fragmented-arguments',reasoning='SYNTHETIC_OPAQUE_REASONING_'+token if mode=='opaque-reasoning' else None)


def completion_frames(script,token):
    """SSE objects; argument fragments concatenate to the exact JSON input."""
    common=dict(id='protocol-'+token,object='chat.completion.chunk',created=1760000000,model='fixture-model')
    frames=[]
    def frame(delta,finish=None):
        frames.append(dict(**common,choices=[dict(index=0,delta=delta,finish_reason=finish)]))
    if script.get('tool_name'):
        arguments=script['arguments']
        cuts=[0,len(arguments)] if not script.get('fragment') else sorted(set([0,1,7,len(arguments)//2,len(arguments)-2,len(arguments)]))
        for index,(start,end) in enumerate(zip(cuts,cuts[1:])):
            call=dict(index=0,function=dict(arguments=arguments[start:end]))
            delta={}
            if index==0:
                call.update(id='call_'+token,type='function')
                call['function']['name']=script['tool_name']
                delta['role']='assistant'
                if script.get('reasoning'): delta['reasoning_content']=script['reasoning']
            delta['tool_calls']=[call]
            frame(delta)
    else:
        frame(dict(role='assistant',content=script.get('content','')))
    frame({},script['finish'])
    return frames


def selfcheck():
    body=dict(messages=[dict(role='user',content='fixture self-check')])
    token='PILOT_PROTOCOL_Unicode_π_换行'
    script=scripted_response('REL-14-S01',token,1,body)
    frames=completion_frames(script,token)
    assembled=''.join(c['function'].get('arguments','') for f in frames for c in f['choices'][0]['delta'].get('tool_calls',[]))
    assert json.loads(assembled)['token']==token
    assert len(frames)>3
    assert scripted_response('REL-15-S01',token,1,body)['status']==429
    assert scripted_response('REL-15-S01',token,2,body)['tool_name']=='eval_probe'
    assert scripted_response('REL-15-S02',token,2,body)['disconnect']
    return dict(fragment_reassembly=True,unicode_preserved=True,scripted_faults_validated=True)


class ProtocolFixture(pilot.Fixture):
    def __init__(self):
        self.scenario=None
        self.token=None
        self.attempt=0
        super().__init__()

    def activate(self,scenario,token):
        self.scenario=scenario
        self.token=token
        self.attempt=0

    def handler(self):
        base=super().handler()
        owner=self
        class Handler(base):
            def do_POST(self):
                if not self.path.endswith('/chat/completions'):
                    return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=8*1024**2: return self.send({'error':'invalid bounded fixture request'},413)
                body=json.loads(self.rfile.read(size))
                with owner.lock:
                    owner.attempt+=1
                    attempt=owner.attempt
                script=scripted_response(owner.scenario,owner.token,attempt,body)
                reasoning='SYNTHETIC_OPAQUE_REASONING_'+owner.token
                assistant_reasoning=[m.get('reasoning_content') for m in body.get('messages',[]) if m.get('role')=='assistant']
                event=owner.event('scripted-provider-request',scenario=owner.scenario,token=owner.token,attempt=attempt,
                    stream=bool(body.get('stream')),tool_results=sum(m.get('role')=='tool' for m in body.get('messages',[])),
                    request_bytes=size,opaque_reasoning_preserved=reasoning in assistant_reasoning,
                    path=self.path,script={k:v for k,v in script.items() if k in {'status','retry_after','error','disconnect','fragment'}})
                if script.get('disconnect'):
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if script['status']!=200:
                    payload=json.dumps({'error':{'message':script['error'],'type':script['error'],'code':script['error']}}).encode()
                    self.send_response(script['status'])
                    if script.get('retry_after'): self.send_header('Retry-After',script['retry_after'])
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                usage=dict(prompt_tokens=7,completion_tokens=5,total_tokens=12)
                include_usage=SCENARIOS[owner.scenario]!='missing-usage'
                if not body.get('stream'):
                    message=dict(role='assistant',content=script.get('content'))
                    if script.get('tool_name'):
                        message['tool_calls']=[dict(id='call_'+owner.token,type='function',function=dict(name=script['tool_name'],arguments=script['arguments']))]
                    if script.get('reasoning'): message['reasoning_content']=script['reasoning']
                    data=dict(id='protocol-'+owner.token,object='chat.completion',model='fixture-model',choices=[dict(index=0,message=message,finish_reason=script['finish'])])
                    if include_usage: data['usage']=usage
                    return self.send(data)
                frames=completion_frames(script,owner.token)
                if include_usage: frames.append(dict(id='protocol-'+owner.token,object='chat.completion.chunk',model='fixture-model',choices=[],usage=usage))
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.end_headers()
                try:
                    for frame in frames:
                        self.wfile.write(('data: '+json.dumps(frame,ensure_ascii=False)+'\n\n').encode())
                        self.wfile.flush()
                        if script.get('fragment'): time.sleep(.01)
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                    event['response_complete']=True
                except (BrokenPipeError,ConnectionResetError):
                    event['client_disconnected']=True
        return Handler


def configure(root,scenario):
    config=pilot.configuration(root,tool_search=False,route='mcp' if scenario=='REL-15-S03' else 'plugin')
    if scenario=='REL-15-S03': config['mcp']['servers']['probe']['requestTimeoutMs']=300
    if scenario=='REL-15-S04':
        provider=config['models']['providers']['fixture']
        provider['models'].append(dict(provider['models'][0],id='fallback-model',name='Unavailable fallback fixture'))
        config['agents']['defaults']['model']['fallbacks']=['fixture/fallback-model']
    pilot.save(root/'config.json',config)
    return config


def acceptance(scenario,request,events):
    providers=[e for e in events if e['kind']=='scripted-provider-request']
    effects=[e for e in events if e['kind']=='effect-commit']
    mode=SCENARIOS[scenario]
    checks=[]
    def check(name,value): checks.append(dict(name=name,verdict='pass' if value else 'fail',evidence=['native-request','independent-events']))
    check('at-least-one-native-provider-request',bool(providers))
    check('bounded-provider-attempts',len(providers)<=12)
    check('no-duplicate-committed-effects',len(effects)<=1)
    if mode in {'fallback-unavailable','context-limit'}:
        check('no-false-success',not request['accepted'])
        check('no-effect',not effects)
    elif mode=='deadline-after-commit':
        check('effect-before-deadline-error-observed',len(effects)==1)
        check('no-false-success-after-unreceived-result',not request['accepted'])
    else:
        check('one-correct-effect',len(effects)==1)
        check('completion-visible',request['accepted'])
    if mode=='fragmented-arguments': check('fragmented-stream-exercised',any(p['stream'] and p['script'].get('fragment') for p in providers))
    if mode=='opaque-reasoning': check('opaque-field-roundtrip',any(p['tool_results'] and p['opaque_reasoning_preserved'] for p in providers))
    if mode=='retry-429':
        check('retry-after-respected',len(providers)>1 and (providers[1]['monotonic_ns']-providers[0]['monotonic_ns'])>=900_000_000)
    if mode=='503-then-disconnect': check('both-faults-exercised',len(providers)>=3 and providers[1]['script'].get('disconnect'))
    return checks
