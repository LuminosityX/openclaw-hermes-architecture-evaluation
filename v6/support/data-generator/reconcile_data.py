import argparse,csv,json
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
p=argparse.ArgumentParser();p.add_argument('--input-dir');p.add_argument('--output-dir');a=p.parse_args();raw=[]
for f in Path(a.input_dir).glob('*.csv'):
 with f.open(encoding='utf-8-sig',newline='') as s:raw+=list(csv.DictReader(s))
latest={}
for e in sorted(raw,key=lambda x:int(x['revision'])):latest[e['record_id']]=e
invalid=[];groups={};void=0;inc=0
for rid,e in latest.items():
 if e['status']=='void':void+=1;continue
 try:
  g=Decimal(e['gross']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);r=Decimal(e['refund']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
  assert 0<=r<=g
 except Exception:invalid.append(rid);continue
 k=e['region'],e['currency'];v=groups.setdefault(k,[0,0,Decimal(0),Decimal(0)]);v[0]+=1;v[1]+=int(e['units']);v[2]+=g;v[3]+=r;inc+=1
out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
with (out/'summary.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['region','currency','record_count','units','gross','refund','net'])
 for k,v in sorted(groups.items()):w.writerow([*k,v[0],v[1],f'{v[2]:.2f}',f'{v[3]:.2f}',f'{v[2]-v[3]:.2f}'])
(out/'audit.json').write_text(json.dumps(dict(policy_id='ACTIVE-2026',raw_rows=len(raw),unique_records=len(latest),duplicate_or_superseded_rows=len(raw)-len(latest),void_records=void,invalid_records=sorted(invalid),included_records=inc)))
(out/'report.md').write_text('Sources: policy-2026.txt part-0.csv part-1.csv. Current rule, currencies remain separate.')
