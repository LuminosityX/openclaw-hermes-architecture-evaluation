"""Immutable tool workload; independently observed on its actual execution host."""
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

if len(sys.argv)!=2 or not re.fullmatch(r'PILOT_MULTI_[A-Z0-9_]{1,100}',sys.argv[1]):raise SystemExit('Owned multi-host task token required')
token=sys.argv[1]
body=dict(token=token,pid=os.getpid(),ppid=os.getppid(),cwd=str(Path.cwd()),pid_namespace=os.readlink('/proc/self/ns/pid'))
request=urllib.request.Request('http://127.0.0.1:18086/effect',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=90) as response:result=json.load(response)
path=Path.cwd()/('multihost-'+token+'.json');path.write_text(json.dumps(result)+'\n')
print('RECEIPT:'+token+' '+json.dumps(result),flush=True)
