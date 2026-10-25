import argparse,json,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--steps',type=int,default=12);p.add_argument('--delay',type=float,default=5);a=p.parse_args()
if not 1<=a.steps<=30 or not 0<=a.delay<=10:raise SystemExit('out of fixture bounds')
out=Path('job_output');out.mkdir(exist_ok=True);journal=out/(a.run_id+'.jsonl')
with journal.open('x') as f:
    for step in range(1,a.steps+1):
        f.write(json.dumps({'run_id':a.run_id,'step':step,'time_ns':time.time_ns()})+'\n');f.flush();time.sleep(a.delay)
    f.write(json.dumps({'run_id':a.run_id,'completed':True,'steps':a.steps})+'\n');f.flush()
print(json.dumps({'run_id':a.run_id,'completed':True,'journal':str(journal)}))
