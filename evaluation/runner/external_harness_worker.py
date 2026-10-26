"""Owned deterministic external executor; no model or hidden answers."""
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.request import Request,urlopen


def calculate(task):
    if task.get('operation')!='add' or any(type(task.get(k)) is not int or abs(task[k])>10**6 for k in ['left','right']):
        raise ValueError('Only bounded public integer addition is supported')
    return task['left']+task['right']


def announce(kind,**values):
    raw=json.dumps(dict(kind=kind,pid=os.getpid(),**values)).encode()
    with urlopen(Request('http://127.0.0.1:18080/harness-event',data=raw,headers={'Content-Type':'application/json'}),timeout=5) as response:
        if response.status!=200:raise RuntimeError('Owned executor observer failed')


def attempt(request):
    task=request['task'];identity=json.dumps(task,sort_keys=True);key=hashlib.sha256(identity.encode()).hexdigest()
    directory=Path(request['state_directory']);directory.mkdir(parents=True,exist_ok=True)
    path=directory/(key+'.json')
    if path.exists():
        if path.stat().st_size>8192:raise ValueError('Owned checkpoint bound')
        state=json.loads(path.read_text())
        if state['task']!=task:raise ValueError('Checkpoint input identity mismatch')
        resumed=True
    else:
        state=dict(task=task,value=calculate(task),calculation_count=1)
        temporary=path.with_suffix('.tmp-'+str(os.getpid()))
        with temporary.open('x') as handle:
            json.dump(state,handle);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
        descriptor=os.open(directory,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        resumed=False
        if request.get('fail_once'):
            announce('external-checkpoint-then-exit',task_id=task['task_id'],checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),exit_code=73)
            return 73
        if task.get('pause_after_checkpoint'):
            announce('external-checkpoint-wait',task_id=task['task_id'],checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            with urlopen(Request('http://127.0.0.1:18080/harness-pause',data=json.dumps(dict(pid=os.getpid(),task_id=task['task_id'])).encode(),headers={'Content-Type':'application/json'}),timeout=28) as response:
                if response.status!=200:raise RuntimeError('Owned checkpoint pause failed')
    result=dict(value=state['value'],task_id=task['task_id'],resumed=resumed,calculation_count=state['calculation_count'],pid=os.getpid(),checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    announce('external-attempt-result',**{k:v for k,v in result.items() if k!='pid'})
    print(json.dumps(result),flush=True);return 0


def stdio():
    for line in sys.stdin:
        if len(line)>65536:raise ValueError('Owned MCP input bound')
        body=json.loads(line);identifier=body.get('id');method=body.get('method');params=body.get('params',{})
        if identifier is None:continue
        if method=='initialize':result=dict(protocolVersion=params.get('protocolVersion','2025-03-26'),capabilities=dict(tools={}),serverInfo=dict(name='owned-arithmetic-executor',version='1.0.0'))
        elif method=='tools/list':result=dict(tools=[dict(name='eval_probe',description='Compute bounded public integer addition in an owned external process',inputSchema=dict(type='object',properties=dict(token=dict(type='string'),left=dict(type='integer'),right=dict(type='integer')),required=['token','left','right']))])
        elif method=='tools/call':
            args=params['arguments'];value=calculate(dict(operation='add',left=args['left'],right=args['right']))
            announce('external-tool-result',token=args['token'],value=value)
            with urlopen(Request('http://127.0.0.1:18080/effect',data=json.dumps(dict(token=args['token'],pid=os.getpid())).encode(),headers={'Content-Type':'application/json'}),timeout=5) as response:receipt=json.loads(response.read())['receipt']
            result=dict(content=[dict(type='text',text=json.dumps(dict(answer='ANSWER:'+str(value),receipt=receipt,pid=os.getpid())))],isError=False)
        elif method=='ping':result={}
        else:
            print(json.dumps(dict(jsonrpc='2.0',id=identifier,error=dict(code=-32601,message='Method not found'))),flush=True);continue
        print(json.dumps(dict(jsonrpc='2.0',id=identifier,result=result)),flush=True)


if __name__=='__main__':
    if sys.argv[1:] == ['--attempt']:
        raw=sys.stdin.read(65537)
        if len(raw)>65536:raise ValueError('Owned executor request bound')
        sys.exit(attempt(json.loads(raw)))
    stdio()
