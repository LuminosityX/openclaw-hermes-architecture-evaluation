"""Six independent official gateways; controlled provider, no paid inference."""
import io,json,os,subprocess,time,hashlib,threading
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save
from run_native_suite import M
RUN_ROOT=R/'runs-scale'
RESULT_NAME='scale.json'
PROFILE='original-unequal-tool-scope'
MEASURE_CAPACITY=True
source=(R/'scripts/vendor_scale.py').read_text()
a=source.index("DRIVER=r'''")+len("DRIVER=r'''");b=source.index("'''\n\ndef main",a);DRIVER=source[a:b]
DRIVER=DRIVER.replace("family=sys.argv[1];S=", "cold_begin=time.monotonic();family=sys.argv[1];S=")
DRIVER=DRIVER.replace("['maxConcurrent']=8", "['maxConcurrent']=16").replace("'max_concurrent_runs':8", "'max_concurrent_runs':16")
DRIVER=DRIVER.replace("range(5)","range(2)").replace("[1,2,4,8] if repeat%2==0 else [8,4,2,1]","[1,2,4,8,16] if (repeat+int(sys.argv[2]))%2==0 else [16,8,4,2,1]")
DRIVER=DRIVER.replace("'stream':False", "'stream':True")
old="conn.request('POST','/v1/chat/completions',body,{'Content-Type':'application/json','Authorization':'Bearer synthetic-scale-token'});res=conn.getresponse();raw=res.read().decode();data=json.loads(raw)\n    content=''.join(str(c.get('message',{}).get('content','')) for c in data.get('choices',[]));ok=res.status==200 and token in content\n    return dict(token=token,status=res.status,correct=ok,seconds=time.monotonic()-start,response=data)"
new="""conn.request('POST','/v1/chat/completions',body,{'Content-Type':'application/json','Authorization':'Bearer synthetic-scale-token'});res=conn.getresponse();content='';first=None;chunks=[]
    for raw in res:
     line=raw.decode().strip()
     if line.startswith('data: ') and line!='data: [DONE]':
      try:
       data=json.loads(line[6:]);chunks.append(data)
       text=''.join(str(c.get('delta',{}).get('content','') or '') for c in data.get('choices',[]))
       if text and first is None:first=time.monotonic()-start
       content+=text
      except ValueError:pass
    ok=res.status==200 and token in content
    return dict(token=token,status=res.status,correct=ok,seconds=time.monotonic()-start,request_started_monotonic=start,first_text_seconds=first,chunks=chunks)"""
if old not in DRIVER:raise RuntimeError('Driver contract changed')
DRIVER=DRIVER.replace(old,new)
DRIVER=DRIVER.replace("warmup=request(0);", "warmup=request(0);warmup['cold_start_to_text_seconds']=(warmup['request_started_monotonic']-cold_begin+warmup['first_text_seconds']) if warmup.get('first_text_seconds') is not None else None;")

class MeasuredFixture(M.Fixture):
 def __init__(self,*args,**kwargs):
  self.provider_intervals=[];self.interval_lock=threading.Lock()
  super().__init__(*args,**kwargs)
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_POST(self):
    payload=self.rfile.read(int(self.headers.get('Content-Length',0)));body=json.loads(payload);self.rfile=io.BytesIO(payload)
    # Measure the configured work at the provider boundary, not a declared config cap.
    is_main=bool(body.get('tools'));begin=time.monotonic_ns()
    try:return super().do_POST()
    finally:
     if is_main:
      end=time.monotonic_ns()
      with owner.interval_lock:
       owner.provider_intervals.append(dict(begin_ns=begin,end_ns=end))
       save(owner.run/'provider-intervals.json',owner.provider_intervals)
  return H

def overlap(intervals):
 events=[(row['begin_ns'],1) for row in intervals]+[(row['end_ns'],-1) for row in intervals];active=peak=0
 for _,delta in sorted(events):active+=delta;peak=max(peak,active)
 return peak

def main():
 os.chdir(OLD);results=[]
 for unit in range(1,7):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):
   run=RUN_ROOT/f'u{unit}'/family
   if (run/'result.json').exists():results.append(json.loads((run/'result.json').read_text()));continue
   if run.exists():raise RuntimeError('Partial run retained: '+str(run))
   run.mkdir(parents=True);configuration(family,run/'state');(run/'workspace').mkdir();(run/'workspace/PROMPT.md').write_text('Synthetic gateway capacity benchmark.');(run/'workspace/http_driver.py').write_text(DRIVER)
   fixture=MeasuredFixture(run,family,'scale');cmd=sandbox(run/'state',run/'workspace',family,['python3','/workspace/http_driver.py',family,str(unit)],fixture.socket_dir)
   save(run/'launch.json',dict(command=cmd,profile=PROFILE,real_model=False,provider_latency_seconds=.25,independent_unit=unit,source_sha256=hashlib.sha256(DRIVER.encode()).hexdigest()))
   print('SCALE_START',unit,family,flush=True)
   try:
    with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(cmd,stdout=out,stderr=err,timeout=420)
    f=run/'workspace/scale-results.json';batches=json.loads(f.read_text()) if f.exists() else []
    f=run/'workspace/warmup.json';warm=json.loads(f.read_text()) if f.exists() else {}
    from run_state_ops import db_inventory
    inventory=db_inventory(run/'state','SCALE_');save(run/'native-persistence-inventory.json',inventory)
    rec=dict(family=family,independent_unit=unit,profile=PROFILE,exit_code=p.returncode,real_model=False,paid_calls=0,warmup=warm,batches=batches,native_persistence_inventory='native-persistence-inventory.json',first_native_tools=next((x['tools'] for x in fixture.calls if x.get('main')),[]),actual_max_simultaneous_provider_requests=overlap(fixture.provider_intervals),provider_intervals=fixture.provider_intervals,configured_concurrency_cap=16,passed=p.returncode==0 and warm.get('correct') and len(batches)==10 and all(x['completed']==x['concurrency'] for x in batches))
    save(run/'result.json',rec);results.append(rec);save(R/'results'/RESULT_NAME,results);print('SCALE_DONE',unit,family,rec['passed'],flush=True)
    if not rec['passed']:raise RuntimeError('Native capacity preflight failed; inspect before expanding')
   finally:fixture.close()
 print('SCALE_COMPLETE',len(results),flush=True)
 if MEASURE_CAPACITY:
  from run_capacity_guards import main as capacity_guards
  capacity_guards()
if __name__=='__main__':main()
