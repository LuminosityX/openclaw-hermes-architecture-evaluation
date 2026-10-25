"""Transport-only authenticated OpenClaw operator client on an existing owner.
The files are evaluator transport records, never credited as product persistence.
"""
import json,os,signal,subprocess,time
from pathlib import Path
from runtime import sandbox
from run_approvals import BRIDGE,operator_rpc

class Operator:
 def __init__(self,gateway):self.gateway=gateway;self.process=None
 def start(self):
  g=self.gateway;r=g.run;helper=Path(__file__).parent/'native_approval_observer.mjs';(r/'state/approval-observer-ready.json').unlink(missing_ok=True)
  args=sandbox(r/'state',r/'workspace','openclaw',['python3','/bridge.py',str(g.port),json.dumps(['node','/approval-observer.mjs'])],g.relay.socket_dir,[(BRIDGE,'/bridge.py',True),(helper,'/approval-observer.mjs',True),(r/'state/control.sock','/gateway-control.sock',False)])
  self.log=(r/'native-operator-transport.log').open('a');self.process=subprocess.Popen(args,stdout=self.log,stderr=self.log,start_new_session=True);until=time.monotonic()+20
  while not(r/'state/approval-observer-ready.json').exists() and time.monotonic()<until and self.process.poll() is None:time.sleep(.05)
  if not(r/'state/approval-observer-ready.json').exists():raise RuntimeError('Native authenticated operator transport did not connect')
  return self
 def rpc(self,method,params,label):return operator_rpc(self.gateway,method,params,label)
 def stop(self):
  if self.process and self.process.poll() is None:
   os.killpg(self.process.pid,signal.SIGTERM)
   try:self.process.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait()
  if hasattr(self,'log'):self.log.close()
 def __enter__(self):return self.start()
 def __exit__(self,*args):self.stop()
