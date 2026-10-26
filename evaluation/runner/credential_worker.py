"""Real stdio MCP child with a synthetic scoped credential, never a user secret."""
import hashlib
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request,urlopen

credential=os.environ['EVAL_API_KEY']


def post(path,body):
    request=Request('http://127.0.0.1:18085/'+path,data=json.dumps(dict(body,pid=os.getpid())).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+credential})
    try:
        with urlopen(request,timeout=5) as response:return response.status,json.loads(response.read())
    except HTTPError as error:return error.code,json.loads(error.read())


if __name__=='__main__':
    post('credential-boot',dict(credential_sha256=hashlib.sha256(credential.encode()).hexdigest()))
    for line in sys.stdin:
        if len(line)>65536:raise ValueError('Owned stdio request bound')
        body=json.loads(line);identifier=body.get('id');method=body.get('method');params=body.get('params',{})
        if identifier is None:continue
        if method=='initialize':result=dict(protocolVersion=params.get('protocolVersion','2025-03-26'),capabilities=dict(tools={}),serverInfo=dict(name='owned-credential-worker',version='1.0.0'))
        elif method=='tools/list':result=dict(tools=[dict(name='eval_probe',description='Use a synthetic capability at its owned independent verifier',inputSchema=dict(type='object',properties=dict(token=dict(type='string')),required=['token']))])
        elif method=='tools/call':
            status,response=post('credential-effect',dict(token=params['arguments']['token']))
            result=dict(content=[dict(type='text',text=json.dumps(response))],isError=status!=200)
        elif method=='ping':result={}
        else:
            print(json.dumps(dict(jsonrpc='2.0',id=identifier,error=dict(code=-32601,message='Method not found'))),flush=True);continue
        print(json.dumps(dict(jsonrpc='2.0',id=identifier,result=result)),flush=True)
