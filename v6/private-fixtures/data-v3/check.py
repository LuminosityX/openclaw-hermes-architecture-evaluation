import csv,json,subprocess,sys,tempfile
from pathlib import Path
want=json.loads(Path('/private/expected.json').read_text());checks=[]
def verify(path,label):
 try:
  with (path/'summary.csv').open(encoding='utf-8-sig',newline='') as f: got=list(csv.DictReader(f))
  checks.append({'name':label+'_summary','passed':got==want['summary']})
  audit=json.loads((path/'audit.json').read_text());checks.append({'name':label+'_audit','passed':all(audit.get(k)==v for k,v in want['audit'].items())})
 except Exception as e:checks.append({'name':label,'passed':False,'error':type(e).__name__})
verify(Path('/workspace/output'),'original')
with tempfile.TemporaryDirectory() as t:
 r=subprocess.run([sys.executable,'/workspace/reconcile_data.py','--input-dir','/workspace/sources','--output-dir',t],capture_output=True,text=True,timeout=20)
 checks.append({'name':'rerun_exit','passed':r.returncode==0});verify(Path(t),'rerun')
try:
 report=Path('/workspace/output/report.md').read_text();checks.append({'name':'sources','passed':'policy-2026.txt' in report and sum(f'part-{j}.csv' in report for j in range(3))>=2})
except Exception:checks.append({'name':'sources','passed':False})
print(json.dumps({'passed':all(x['passed'] for x in checks),'checks':checks}));sys.exit(0 if all(x['passed'] for x in checks) else 1)
