"""Owned stdio MCP fixture; same receipt effect as the in-process probe."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import sys
import threading
import time
from urllib.request import Request, urlopen

WRITE = threading.Lock()


def post(path, body):
    with urlopen(Request('http://127.0.0.1:18080'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=5) as response:
        return json.load(response)


def respond(request):
    if 'id' not in request:
        return
    method=request.get('method')
    params=request.get('params',{})
    if method=='initialize':
        result=dict(protocolVersion=params.get('protocolVersion','2024-11-05'),capabilities=dict(tools=dict(listChanged=False)),serverInfo=dict(name='pilot-probe',version='1.0.0'))
    elif method=='ping':
        result={}
    elif method=='tools/list':
        result=dict(tools=[dict(name='eval_probe',description='Execute a deterministic local pilot receipt operation',
            inputSchema=dict(type='object',properties=dict(token=dict(type='string'),action=dict(type='string')),required=['token']))])
    elif method=='tools/call':
        args=params['arguments']
        if args.get('action')=='canary':
            post('/fault',dict(token=args['token'],action='canary',pid=os.getpid(),uid=os.getuid()))
        if args.get('action') in {'block','crash','throw'}:
            post('/fault',dict(token=args['token'],action=args['action'],pid=os.getpid()))
            if args['action']=='crash':
                os._exit(42)
            if args['action']=='throw':
                with WRITE:
                    print(json.dumps(dict(jsonrpc='2.0',id=request['id'],error=dict(code=-32000,message='SOURCE_FOLLOWUP_THROW'))),flush=True)
                return
            until=time.monotonic()+.6
            while time.monotonic()<until:
                pass
        metadata=dict(pid=os.getpid(),uid=os.getuid(),is_main_thread=threading.current_thread() is threading.main_thread(),thread_id=threading.get_ident())
        if args.get('action')=='canary':
            metadata['canary_readable']=Path('/scratch/source-owned-canary').read_text()=='SYNTHETIC_SOURCE_CANARY'
        receipt=post('/effect',dict(token=args['token'],**metadata))
        result=dict(content=[dict(type='text',text=json.dumps(receipt))],isError=False)
    else:
        with WRITE:
            print(json.dumps(dict(jsonrpc='2.0',id=request['id'],error=dict(code=-32601,message='Method not found'))),flush=True)
        return
    with WRITE:
        print(json.dumps(dict(jsonrpc='2.0',id=request['id'],result=result)),flush=True)


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=8) as pool:
        for line in sys.stdin:
            pool.submit(respond,json.loads(line))
