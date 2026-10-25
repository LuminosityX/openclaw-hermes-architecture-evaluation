import json,subprocess,time
from pathlib import Path
from runtime import R,save
ROOT=Path('/sys/fs/cgroup/oc-hermes-v6')
def create(name):
 ROOT.mkdir(exist_ok=True);(ROOT/'cgroup.subtree_control').write_text('+cpu +memory +pids');g=ROOT/name;g.mkdir();(g/'memory.max').write_text(str(5*1024**3));(g/'pids.max').write_text('512');return g
def read(g):
 cpu={k:int(v) for k,v in (x.split() for x in (g/'cpu.stat').read_text().splitlines())}
 return dict(cpu=cpu,peak_memory_bytes=int((g/'memory.peak').read_text()),current_memory_bytes=int((g/'memory.current').read_text()),pids=(g/'cgroup.procs').read_text().split())
def wrap(g,cmd):return ['python3',str(R/'scripts/cgroup_exec.py'),str(g),*cmd]
def selfcheck():
 g=create('selftest-'+str(time.time_ns()));code="import time,subprocess,sys; b=bytearray(32*1024*1024); ps=[subprocess.Popen([sys.executable,'-c','import time;b=bytearray(32*1024*1024);s=time.process_time();\\nwhile time.process_time()-s<.2:pass\\ntime.sleep(.4)'.replace('\\\\n','\\n')]) for _ in range(2)];s=time.process_time();\nwhile time.process_time()-s<.2:pass\nfor p in ps:p.wait()\ntime.sleep(.3)"
 # Simple separate child program avoids shell interpolation.
 child=R/'evidence/resource_child.py';child.write_text('import time\nb=bytearray(32*1024*1024)\ns=time.process_time()\nwhile time.process_time()-s<.2:pass\ntime.sleep(.5)\n')
 parent=R/'evidence/resource_parent.py';parent.write_text('import time,subprocess,sys\nb=bytearray(32*1024*1024)\nps=[subprocess.Popen([sys.executable,'+repr(str(child))+']) for _ in range(2)]\ns=time.process_time()\nwhile time.process_time()-s<.2:pass\nfor p in ps:p.wait()\ntime.sleep(.3)\n')
 p=subprocess.run(wrap(g,['python3',str(parent)]),capture_output=True,text=True);v=read(g);v['passed']=p.returncode==0 and .5<v['cpu']['usage_usec']/1e6<1.5 and v['peak_memory_bytes']>90*1024**2;save(R/'evidence/resource-selftest.json',v);assert v['passed'],v;print('RESOURCE_SELFCHECK',v)
if __name__=='__main__':selfcheck()
