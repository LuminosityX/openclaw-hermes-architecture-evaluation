import json,os,signal,subprocess,time,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];old=Path('/root/output/openclaw-hermes-benchmark-20261022');pidfile=R/'runtime/service-pids.json';pids=json.loads(pidfile.read_text());os.kill(pids['hermes'],signal.SIGTERM);time.sleep(1)
with (R/'logs/hermes-matched.log').open('ab')as log:p=subprocess.Popen([str(old/'envs/hermes/bin/python'),str(R/'scripts/hermes_gateway.py')],cwd=R,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
pids['hermes']=p.pid;pidfile.write_text(json.dumps(pids));time.sleep(2)
from run_http import control,request
records=[]
for i in range(3):
    for f in(['hermes','openclaw']if i%2==0 else['openclaw','hermes']):
        run_id=f+'-tool-allowed-'+str(i);control(f,run_id);records.append(request(f,run_id,'tool'))
(R/'results/tool-matched-runs.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
