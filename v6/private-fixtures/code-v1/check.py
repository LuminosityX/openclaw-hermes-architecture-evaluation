import copy,csv,json,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,'/workspace')
from ledger import reconcile
from ledger.io import read_events
cases=json.loads(Path('/private/cases.json').read_text());checks=[]
for c in cases:
 data=copy.deepcopy(c['events']);before=copy.deepcopy(data)
 try:checks.append({'name':c['name'],'passed':reconcile(data,c['cutoff'])==c['expected'] and data==before})
 except Exception as e:checks.append({'name':c['name'],'passed':False,'error':type(e).__name__})
with tempfile.TemporaryDirectory() as t:
 p=Path(t)/'quoted.csv';rows=cases[1]['events'];rows=copy.deepcopy(rows)
 for r in rows:r['order_id']='测试,订单'
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 try:
  got=read_events(p);checks.append({'name':'csv_bom_quotes','passed':len(got)==2 and got[0]['order_id']=='测试,订单'})
 except Exception as e:checks.append({'name':'csv_bom_quotes','passed':False,'error':type(e).__name__})
 out=Path(t)/'nested/result.json'
 r=subprocess.run([sys.executable,'-m','ledger',str(p),'--cutoff','2026-01-01T01:00:00Z','--output',str(out)],capture_output=True,text=True,timeout=10,cwd='/workspace')
 try:good=r.returncode==0 and json.loads(out.read_text())['orders'][0]['captured']=='10.00' and not r.stdout.strip()
 except Exception:good=False
 checks.append({'name':'cli_output','passed':good})
print(json.dumps({'passed':all(x['passed'] for x in checks),'checks':checks}))
sys.exit(0 if all(x['passed'] for x in checks) else 1)
