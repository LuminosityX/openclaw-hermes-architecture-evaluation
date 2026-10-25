import json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
coordinator_pid=2672892
while True:
 try:os.kill(coordinator_pid,0)
 except ProcessLookupError:break
 time.sleep(2)
done=list(R.glob('runs/*/*/result.json'))
if len(done)!=12:raise SystemExit('Main batch incomplete; mechanism tests not started automatically')
(R/'evidence/stop-resource-observer').touch()
for name in ['run_mechanisms.py','run_scale.py']:
 print('START_NEXT_SUITE',name,flush=True)
 r=subprocess.run(['python3',str(R/'scripts'/name)])
 print('FINISH_SUITE',name,r.returncode,flush=True)
