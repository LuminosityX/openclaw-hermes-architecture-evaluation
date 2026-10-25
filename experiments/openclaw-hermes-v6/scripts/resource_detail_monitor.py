"""Non-invasive controller sampling. cgroup peak remains authoritative; PSS peaks are sampled lower bounds."""
import hashlib,json,os,time
from pathlib import Path
from runtime import R,save
started=time.time();last_run=None;index=0
while True:
 try:
  active=json.loads((R/'evidence/active.json').read_text());run=Path(active['run']) if active.get('pid') else None
  if run and (run/'launch.json').exists():
   command=json.loads((run/'launch.json').read_text())['command'];i=next(i for i,x in enumerate(command) if 'cgroup_exec.py' in x);group=Path(command[i+1]);now=time.time()
   if run!=last_run:
    last_run=run;index=0;save(run/'memory-detail-method.json',dict(monitor_started_unix=started,first_sample_unix=now,interval_seconds=1,pss_interval_seconds=5,source='Real cgroup memory.stat and all cgroup.procs smaps_rollup',note='Cgroup peak is exact; PSS maximum is a sampled lower bound. A run that began before this monitor started is incomplete for PSS/detail analysis, and must be excluded from those comparisons.'))
   stats={k:int(v) for k,v in (x.split() for x in (group/'memory.stat').read_text().splitlines())};record=dict(unix=now,anon_bytes=stats.get('anon'),file_cache_bytes=stats.get('file'),kernel_bytes=stats.get('kernel'),current_bytes=int((group/'memory.current').read_text()),peak_bytes=int((group/'memory.peak').read_text()))
   if index%5==0:
    pids=list(map(int,(group/'cgroup.procs').read_text().split()));processes=[]
    for pid in pids:
     try:
      d={x.split(':',1)[0]:int(x.split(':',1)[1].split()[0])*1024 for x in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines() if ':' in x and x.split(':',1)[1].strip().split()[0].isdigit()};processes.append(dict(pid=pid,comm=Path(f'/proc/{pid}/comm').read_text().strip(),rss_bytes=d.get('Rss'),pss_bytes=d.get('Pss')))
     except (OSError,IndexError,ValueError):pass
    record['processes']=processes;record['pss_sum_bytes']=sum(p['pss_bytes'] or 0 for p in processes)
   with (run/'memory-detail.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
   index+=1
 except (OSError,ValueError,KeyError,StopIteration):pass
 time.sleep(1)
