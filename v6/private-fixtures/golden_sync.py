import argparse,json,urllib.request,hashlib
from decimal import Decimal,ROUND_HALF_UP
p=argparse.ArgumentParser();p.add_argument('--base-url');p.add_argument('--output');a=p.parse_args()
def call(path,method='GET',data=None):
 b=json.dumps(data).encode() if data is not None else None
 return json.load(urllib.request.urlopen(urllib.request.Request(a.base_url+path,data=b,method=method,headers={'Content-Type':'application/json'})))
rows=[];cursor=0
while True:
 page=call('/orders?cursor='+str(cursor));rows+=page['items'];cursor=page['next_cursor']
 if cursor is None:break
latest={}
for r in rows:
 if r['id'] not in latest or r['revision']>latest[r['id']]['revision']:latest[r['id']]=r
billing={r['id']:r for r in call('/billing')};groups={};active=void=0
for key,r in latest.items():
 if r['status']=='void':
  void+=1
  if key in billing:call('/billing/'+key,'DELETE')
  continue
 active+=1;net=Decimal(r['gross']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)-Decimal(r['refund']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);out=dict(id=key,revision=r['revision'],currency=r['currency'],net=f'{net:.2f}')
 if billing.get(key)!=out:call('/billing/'+key,'PUT',out)
 g=groups.setdefault(r['currency'],[0,Decimal(0)]);g[0]+=1;g[1]+=net
final=sorted(call('/billing'),key=lambda x:x['id']);digest=hashlib.sha256(json.dumps(final,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
json.dump(dict(unique_orders=len(latest),active_orders=active,void_orders=void,by_currency=[dict(currency=k,records=v[0],net=f'{v[1]:.2f}') for k,v in sorted(groups.items())],billing_digest=digest),open(a.output,'w'))
