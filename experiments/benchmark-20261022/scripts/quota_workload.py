"""Run inside a task-owned, resource-limited container. Never run on the host."""
import errno
import json
from pathlib import Path
import subprocess
import sys
import time

CG = Path('/sys/fs/cgroup')
if not (CG / 'memory.max').exists():
    print(json.dumps({'status': 'unsupported', 'reason': 'cgroup v2 files unavailable'}))
    raise SystemExit(0)
memory_max = (CG / 'memory.max').read_text().strip()
swap_max = (CG / 'memory.swap.max').read_text().strip()
pids_max = (CG / 'pids.max').read_text().strip()
cpu_max = (CG / 'cpu.max').read_text().strip()
if swap_max != '0' or memory_max != '536870912' or pids_max != '128' or cpu_max.split()[0] == 'max':
    raise SystemExit('Refusing stress without expected container memory/PID/CPU limits')

def counters(filename):
    return {line.split()[0]: int(line.split()[1]) for line in (CG / filename).read_text().splitlines()}

results = []
before = counters('cpu.stat')
start = time.monotonic()
children = [subprocess.Popen([sys.executable, '-c', 'import time\nend=time.monotonic()+1.5\nx=1\nwhile time.monotonic()<end:\n x=(x*17+3)%10000019']) for _ in range(4)]
for child in children:
    child.wait(timeout=10)
wall = time.monotonic()-start
after = counters('cpu.stat')
usage_seconds = (after['usage_usec']-before['usage_usec'])/1e6
throttled = after.get('nr_throttled',0)-before.get('nr_throttled',0)
quota, period = map(int, cpu_max.split())
cpu_ok = quota == period and throttled > 0 and usage_seconds <= wall*1.25 + 0.1
results.append({'resource':'cpu','correct':cpu_ok,'cpu_max':cpu_max,'wall_seconds':wall,'cpu_usage_seconds':usage_seconds,'throttled_periods':throttled})

before = counters('memory.events')
child = subprocess.run([sys.executable, '-c', 'data=bytearray(640*1024*1024)\nprint(len(data))'],capture_output=True,text=True,timeout=15)
after = counters('memory.events')
oom_kills = after.get('oom_kill',0)-before.get('oom_kill',0)
results.append({'resource':'memory','correct':child.returncode == -9 and oom_kills >= 1,'memory_max':memory_max,'memory_swap_max':swap_max,'requested_bytes':640*1024*1024,'child_returncode':child.returncode,'oom_kills':oom_kills})

children = []
before = counters('pids.events')
limit_error = None
peak = 0
try:
    for _ in range(160):
        try:
            children.append(subprocess.Popen(['/bin/sleep','20'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            peak = max(peak,int((CG/'pids.current').read_text()))
        except OSError as error:
            limit_error = error.errno
            break
    after = counters('pids.events')
    max_events = after.get('max',0)-before.get('max',0)
    results.append({'resource':'pids','correct':limit_error == errno.EAGAIN and max_events > 0 and peak <=128,'pids_max':pids_max,'children_started':len(children),'observed_peak_pids':peak,'spawn_errno':limit_error,'max_events':max_events})
finally:
    for child in children:
        child.terminate()
    for child in children:
        child.wait(timeout=5)
print(json.dumps({'status':'complete','results':results,'all_correct':all(x['correct'] for x in results)}))
