"""Independent exact-rational data oracle; no Decimal and no candidate/reference script execution."""
import csv,json,re
from fractions import Fraction
from pathlib import Path

def cents(text,even):
 value=Fraction(text)*100;sign=-1 if value<0 else 1;n,d=abs(value.numerator),value.denominator;q,r=divmod(n,d)
 if 2*r>d or 2*r==d and (not even or q%2):q+=1
 return sign*q

def fmt(value):return ('-' if value<0 else '')+str(abs(value)//100)+'.'+str(abs(value)%100).zfill(2)
def expected(sources,even=None):
 sources=Path(sources);policy=(sources/'policy-2026.txt').read_text();match=re.search(r'文档ID\s+([A-Z0-9-]+)',policy)
 if not match:raise ValueError('Current policy ID not established')
 even=('ROUND_HALF_EVEN' in policy) if even is None else even;rows=[]
 for p in sources.glob('*.csv'):
  with p.open(encoding='utf-8-sig',newline='') as f:rows.extend(csv.DictReader(f))
 latest={}
 for row in rows:
  current=latest.get(row['record_id'])
  if current is None or int(row['revision'])>=int(current['revision']):latest[row['record_id']]=row
 groups={};invalid=[];void=0;included=0
 for key,row in latest.items():
  if row['status']=='void':void+=1;continue
  try:
   gross,refund=cents(row['gross'],even),cents(row['refund'],even)
   if gross<0 or refund<0 or refund>gross:raise ValueError('invalid amount')
  except (ValueError,ZeroDivisionError,OverflowError):invalid.append(key);continue
  group=groups.setdefault((row['region'],row['currency']),[0,0,0,0]);group[0]+=1;group[1]+=int(row['units']);group[2]+=gross;group[3]+=refund;included+=1
 summary=[dict(region=k[0],currency=k[1],record_count=str(v[0]),units=str(v[1]),gross=fmt(v[2]),refund=fmt(v[3]),net=fmt(v[2]-v[3])) for k,v in sorted(groups.items())]
 audit=dict(policy_id=match[1],raw_rows=len(rows),unique_records=len(latest),duplicate_or_superseded_rows=len(rows)-len(latest),void_records=void,invalid_records=sorted(invalid),included_records=included)
 return dict(summary=summary,audit=audit)
