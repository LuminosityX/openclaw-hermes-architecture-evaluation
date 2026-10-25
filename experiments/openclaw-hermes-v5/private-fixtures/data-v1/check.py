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

# Perturb an active unique record in a new input directory, so replay is not just copying a cached output.
import shutil,copy
with tempfile.TemporaryDirectory() as t:
 src=Path(t)/'input';shutil.copytree('/workspace/sources',src)
 for p in src.glob('*.csv'):
  with p.open(encoding='utf-8-sig',newline='') as f: reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
  for row in rows:
   if row['record_id']=='EDGE0':row['units']=str(int(row['units'])+3)
  with p.open('w',encoding='utf-8',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
 out=Path(t)/'changed-output'
 r=subprocess.run([sys.executable,'/workspace/reconcile_data.py','--input-dir',str(src),'--output-dir',str(out)],capture_output=True,text=True,timeout=20)
 old=copy.deepcopy(want)
 for row in want['summary']:
  if row['region']=='华东' and row['currency']=='CNY':row['units']=str(int(row['units'])+3)
 checks.append({'name':'perturbed_exit','passed':r.returncode==0});verify(out,'perturbed');want=old

print(json.dumps({'passed':all(x['passed'] for x in checks),'checks':checks}));sys.exit(0 if all(x['passed'] for x in checks) else 1)
