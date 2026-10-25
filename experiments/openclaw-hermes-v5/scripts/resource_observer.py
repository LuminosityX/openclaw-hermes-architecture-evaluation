"""Read-only process-tree sampler. Does not start a subject or call a model."""
import json,os,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];HZ=os.sysconf('SC_CLK_TCK');current=None;record=None;last_seen=time.monotonic()
def flush():
 if record:
  p=R/'runs'/record['task']/record['family']/'sampled-resources.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(record,indent=2));t.replace(p)
def snapshot():
 result={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   raw=(p/'stat').read_text().rsplit(')',1)[1].split()
   result[int(p.name)]=(int(raw[1]),int(raw[11])+int(raw[12]),int(raw[19]))
  except (OSError,ValueError,IndexError):pass
 return result
while not (R/'evidence/stop-resource-observer').exists():
 try:a=json.loads((R/'evidence/active.json').read_text())
 except (OSError,ValueError):time.sleep(1);continue
 if not a.get('pid'):
  flush();current=None;record=None;time.sleep(1);continue
 key=(a['task'],a['family'],a['pid']);ps=snapshot()
 if key!=current:
  flush();current=key;start=ps.get(a['pid'],(0,0,0))[2];uptime=float(Path('/proc/uptime').read_text().split()[0])
  record={'task':a['task'],'family':a['family'],'root_pid':a['pid'],'first_observation_age_seconds':uptime-start/HZ,'full_from_start':0<=uptime-start/HZ<=3,'peak_sum_pss_kib':0,'peak_sum_rss_kib':0,'samples':0,'observed_cpu_ticks':{},'scope':'Sampled process tree every second; PSS summed; short-lived children may be missed; CPU is an observed lower bound, not total CPU accounting.'}
 ids={a['pid']}
 for _ in range(20):
  more={pid for pid,v in ps.items() if v[0] in ids}-ids
  if not more:break
  ids|=more
 pss=rss=0
 for pid in ids:
  if pid in ps:record['observed_cpu_ticks'][f'{pid}:{ps[pid][2]}']=ps[pid][1]
  try:
   for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines():
    if line.startswith('Pss:'):pss+=int(line.split()[1])
    elif line.startswith('Rss:'):rss+=int(line.split()[1])
  except (OSError,ValueError):pass
 record['samples']+=1;record['peak_sum_pss_kib']=max(record['peak_sum_pss_kib'],pss);record['peak_sum_rss_kib']=max(record['peak_sum_rss_kib'],rss)
 record['observed_cpu_seconds_lower_bound']=sum(record['observed_cpu_ticks'].values())/HZ;flush();time.sleep(1)
flush()
