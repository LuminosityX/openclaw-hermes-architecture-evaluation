import csv, hashlib, json, random, textwrap
from pathlib import Path
R=Path(__file__).resolve().parents[1]

REFERENCE='''from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

def instant(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("timestamp requires timezone")
    return d.astimezone(timezone.utc)

def reconcile(events, cutoff=None):
    latest={}
    end=instant(cutoff) if cutoff else None
    for e in events:
        if end is not None and instant(e["at"])>end: continue
        prev=latest.get(e["event_id"])
        if prev is None or int(e["revision"])>int(prev["revision"]):latest[e["event_id"]]=e
    orders={};rejected=[]
    for e in sorted(latest.values(),key=lambda x:(instant(x["at"]),x["event_id"])):
        typ=e["type"];oid=e["order_id"];cur=e["currency"]
        amount=Decimal(e["amount"]).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        reason=None;o=orders.get(oid)
        if amount<0:reason="negative_amount"
        elif typ=="create":
            if o:reason="duplicate_order"
            else:orders[oid]={"order_id":oid,"currency":cur,"limit":amount,"captured":Decimal(0),"refunded":Decimal(0),"void":False}
        elif o is None:reason="missing_order"
        elif cur!=o["currency"]:reason="currency_mismatch"
        elif typ not in ("capture","refund","void"):reason="unknown_type"
        elif o["void"]:reason="voided_order"
        elif typ=="capture":
            if o["captured"]+amount>o["limit"]:reason="over_capture"
            else:o["captured"]+=amount
        elif typ=="refund":
            if o["refunded"]+amount>o["captured"]:reason="over_refund"
            else:o["refunded"]+=amount
        else:
            if o["captured"]!=o["refunded"]:reason="outstanding_capture"
            else:o["void"]=True
        if reason:rejected.append({"event_id":e["event_id"],"reason":reason})
    out=[];totals={}
    for oid,o in sorted(orders.items()):
        c,r=o["captured"],o["refunded"];net=c-r
        status="void" if o["void"] else "refunded" if c>0 and net==0 else "paid" if c==o["limit"] and r==0 and c>0 else "partial" if c>0 else "open"
        out.append({"order_id":oid,"currency":o["currency"],"captured":f"{c:.2f}","refunded":f"{r:.2f}","net":f"{net:.2f}","status":status})
        t=totals.setdefault(o["currency"],[Decimal(0),Decimal(0),Decimal(0)])
        for i,v in enumerate((c,r,net)):t[i]+=v
    return {"orders":out,"rejected":rejected,"totals":[dict(currency=k,captured=f"{v[0]:.2f}",refunded=f"{v[1]:.2f}",net=f"{v[2]:.2f}") for k,v in sorted(totals.items())]}
'''
(R/'private/reference.py').write_text(REFERENCE)
ns={};exec(REFERENCE,ns)
def event(eid,oid,typ,amt,at='2026-01-01T00:00:00Z',cur='USD',rev=1):
    return dict(event_id=eid,order_id=oid,type=typ,amount=str(amt),at=at,currency=cur,revision=rev)
def scenario(seed):
    rng=random.Random(seed);out=[]
    for i in range(35):
        oid=f'order-{seed}-{i:03}';cur=['USD','CNY','EUR'][i%3];limit=str(rng.randint(1000,9999)/100)
        out += [event(f'{i:03}-a',oid,'create',limit,cur=cur),event(f'{i:03}-b',oid,'capture',limit,'2026-01-01T01:00:00Z',cur),event(f'{i:03}-c',oid,'refund','0.005','2026-01-01T02:00:00Z',cur)]
        if i%3==0:out += [dict(out[-2]),event(f'{i:03}-b',oid,'capture','0.01','2026-01-01T01:00:00Z',cur,2)]
        if i%4==0:out += [event(f'{i:03}-d',oid,'refund','999','2026-01-01T03:00:00Z',cur)]
        if i%5==0:out += [event(f'{i:03}-e',oid,'capture','1','2026-01-01T04:00:00Z','BAD')]
        if i%7==0:out += [event(f'{i:03}-f',oid,'void','0','2026-01-01T05:00:00Z',cur)]
    out += [event('orphan','absent','refund','2'),event('negative','absent','capture','-1')]
    rng.shuffle(out);return out
def cases(seed):
    base=[event('a','x','create','10'),event('b','x','capture','10','2026-01-01T01:00:00Z')]
    tests=[('empty',[],None),('paid',base,None),('duplicates',base+[dict(base[1])],None),('revision',base+[event('b','x','capture','5','2026-01-01T01:00:00Z',rev=2)],None),('cutoff_inclusive',base,'2026-01-01T01:00:00Z'),('cutoff_early',base,'2026-01-01T00:00:00Z'),('refund',base+[event('c','x','refund','10','2026-01-01T02:00:00Z')],None),('over_refund',base+[event('c','x','refund','11','2026-01-01T02:00:00Z')],None),('void_after_refund',base+[event('c','x','refund','10','2026-01-01T02:00:00Z'),event('d','x','void',0,'2026-01-01T03:00:00Z'),event('e','x','capture',1,'2026-01-01T04:00:00Z')],None),('round_half_up',[event('a','x','create','0.005'),event('b','x','capture','0.005','2026-01-01T01:00:00Z')],None),('timezone_order',[event('a','x','create','10','2026-01-01T09:00:00+08:00'),event('b','x','capture','10','2026-01-01T01:01:00Z')],None),('filter_before_revision',base+[event('b','x','capture','1','2026-02-01T00:00:00Z',rev=2)],'2026-01-02T00:00:00Z')]
    for j in range(12):tests.append((f'mixed_{j}',scenario(seed+j),None if j%2 else '2026-01-01T02:00:00Z'))
    return [dict(name=n,events=e,cutoff=c,expected=ns['reconcile'](e,c)) for n,e,c in tests]

CODING_PROMPT='''修复本目录的 Python 订单对账工具。它将被用于批处理，必须同时保留 import API 和命令行入口；不是只生成示例结果。
交付：ledger/core.py 的 reconcile(events, cutoff=None)、ledger/io.py 的 read_events(path)、python -m ledger INPUT.csv [--cutoff ISO] [--output PATH]，并在 CHANGELOG.md 简述改动和验证。
只用标准库。不得改变这里规定的输出接口；可修改实现并增加自己的测试。test_public.py 是可见冒烟测试，最终有独立验收。

事件字段：event_id,revision,order_id,type,amount,currency,at。所有输入时间合法且有时区，revision是正整数，相同id相同revision内容相同。CSV须支持引号、Unicode和BOM。
1. 若有cutoff，先按UTC时间保留at<=cutoff的事件，再按event_id仅保留最大revision；重复事件不能重复记账。最终按UTC时间、event_id排序执行，不得按输入顺序或时间字符串排序。
2. 金额用十进制，在每个事件入账前按ROUND_HALF_UP保留两位。禁止浮点误差和跨货币合并。
3. create建立订单限额；重复create拒绝。capture累计不能超过原限额，refund累计不能超过已capture金额，非法事件不能部分入账；退款不会释放capture的原限额。
4. void只允许captured==refunded时成功；成功后capture/refund/void均拒绝。create金额允许0。
5. 按以下顺序确定唯一拒绝原因：negative_amount；create分支duplicate_order；非create分支missing_order、currency_mismatch、unknown_type、voided_order，最后操作特定的over_capture、over_refund、outstanding_capture。
6. 每单状态优先顺序：void；captured>0且净额0为refunded；captured==limit且refunded==0且captured>0为paid；captured>0为partial；否则open。
7. 返回 {"orders":[{"order_id":...,"currency":...,"captured":"0.00","refunded":"0.00","net":"0.00","status":...}],"rejected":[{"event_id":...,"reason":...}],"totals":[{"currency":...,"captured":"0.00","refunded":"0.00","net":"0.00"}]}。orders按order_id排序，totals按currency排序，rejected按执行发生顺序。totals包括所有已建立订单（含void和零额）。金额均为两位小数字符串。
8. API不修改输入。CLI将唯一JSON结果写stdout或--output，诊断不可混入stdout；--output父目录不存在时创建。
请真实修改并测试代码，不要只给建议。
'''
for variant in range(1,4):
    p=R/'fixtures'/f'code-v{variant}';(p/'ledger').mkdir(parents=True,exist_ok=True)
    (p/'PROMPT.md').write_text(CODING_PROMPT)
    (p/'ledger/__init__.py').write_text('from .core import reconcile\n')
    (p/'ledger/core.py').write_text('''def reconcile(events, cutoff=None):
    orders={}
    for e in events:
        oid=e['order_id']
        if e['type']=='create': orders[oid]={'order_id':oid,'currency':e['currency'],'captured':0.,'refunded':0.,'net':0.,'status':'open'}
        elif oid in orders:
            key='captured' if e['type']=='capture' else 'refunded'
            orders[oid][key]+=float(e['amount'])
            orders[oid]['net']=orders[oid]['captured']-orders[oid]['refunded']
    return {'orders':list(orders.values()),'rejected':[],'totals':[]}
''')
    (p/'ledger/io.py').write_text('''def read_events(path):
    lines=open(path).read().splitlines();keys=lines[0].split(',')
    return [dict(zip(keys,line.split(','))) for line in lines[1:]]
''')
    (p/'ledger/__main__.py').write_text('''import sys,json
from .core import reconcile
from .io import read_events
print(json.dumps(reconcile(read_events(sys.argv[1]))))
''')
    (p/'test_public.py').write_text('''import unittest
from ledger import reconcile
class Smoke(unittest.TestCase):
 def test_empty(self):self.assertEqual(reconcile([]),{'orders':[],'rejected':[],'totals':[]})
if __name__=='__main__':unittest.main()
''')
    sample=scenario(100+variant)
    with (p/'sample.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(sample[0]));w.writeheader();w.writerows(sample)
    priv=R/'private'/f'code-v{variant}';priv.mkdir(exist_ok=True)
    (priv/'cases.json').write_text(json.dumps(cases(1000+variant*100)))
    (priv/'check.py').write_text('''import copy,csv,json,subprocess,sys,tempfile
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
''')

    # A separate deliverable task: versions, corrections and malformed input records.
    p=R/'fixtures'/f'data-v{variant}';(p/'sources').mkdir(parents=True,exist_ok=True)
    rng=random.Random(800+variant);raw=[];latest={}
    for i in range(1200):
        row=dict(record_id=f'R{i:05}',revision='1',status='active',region=['华东','华北','华南'][i%3],currency=['CNY','USD'][i%2],gross=f'{rng.randrange(1,50000)/100:.2f}',refund=f'{rng.randrange(0,100)/100:.2f}',units=str(rng.randrange(1,8)))
        raw.append(row);latest[row['record_id']]=row
        if i%7==0:
            row={**row,'revision':'2','gross':f'{rng.randrange(1,50000)/100:.2f}'};raw.append(row);latest[row['record_id']]=row
        if i%11==0:
            row={**row,'revision':'3','status':'void'};raw.append(row);latest[row['record_id']]=row
        if i%13==0:raw.append(dict(row))
    # Values that expose rounding order and invalid handling.
    for i,(g,r) in enumerate([('0.005','0'),('1.005','0.005'),('9.995','0.005'),('broken','0'),('-1','0'),('1','2')]):
        row=dict(record_id=f'EDGE{i}',revision='1',status='active',region='华东',currency='CNY',gross=g,refund=r,units='1');raw.append(row);latest[row['record_id']]=row
    rng.shuffle(raw)
    keys=list(raw[0])
    for j in range(3):
        with (p/'sources'/f'part-{j}.csv').open('w',encoding='utf-8-sig' if j==1 else 'utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(raw[j::3])
    (p/'sources/policy-2025.txt').write_text('文档ID OLD-2025。过期：用首次记录，银行家舍入，作废记录仍入账。不得用于2026报表。')
    (p/'sources/policy-2026.txt').write_text('文档ID ACTIVE-2026，当前有效。跨全部分片按record_id去重，取最高数字revision；同版本重复为同一记录。去重后去掉status=void；先将gross和refund分别用Decimal ROUND_HALF_UP舍入两位，再求净额。gross/refund不可解析、任一为负或refund>gross的当前active记录为invalid，不计入分组；作废记录不参加金额验证。按region,currency分组，合计record_count、units、gross、refund、net。不能跨币种相加。')
    (p/'PROMPT.md').write_text('''请根据sources内当前有效政策，核对全部CSV分片并交付可复现的业务报表。旧政策只是历史背景。只用Python标准库，不得硬编码输出；请创建reconcile_data.py，使 python reconcile_data.py --input-dir sources --output-dir output 能从输入重新生成全部产物。
产物：output/summary.csv，字段顺序region,currency,record_count,units,gross,refund,net，按region再currency的Unicode顺序排序，金额两位；output/audit.json，包含policy_id、raw_rows、unique_records、duplicate_or_superseded_rows、void_records、invalid_records（按record_id排序的ID列表）、included_records；output/report.md解释采用哪版政策、为何不能跨币种加总，并引用policy-2026.txt及至少两个CSV来源。
金额和去重语义以当前政策为准。请运行脚本，并独立核对各组净额与审计数量，不要只写计算建议。
''')
    from decimal import Decimal,ROUND_HALF_UP,InvalidOperation
    groups={};invalid=[];void=0;included=0
    for rid,row in latest.items():
        if row['status']=='void':void+=1;continue
        try:
            g=Decimal(row['gross']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);ref=Decimal(row['refund']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if g<0 or ref<0 or ref>g:raise ValueError()
        except (InvalidOperation,ValueError):invalid.append(rid);continue
        k=(row['region'],row['currency']);a=groups.setdefault(k,[0,0,Decimal(0),Decimal(0)]);a[0]+=1;a[1]+=int(row['units']);a[2]+=g;a[3]+=ref;included+=1
    expected=[dict(region=k[0],currency=k[1],record_count=str(a[0]),units=str(a[1]),gross=f'{a[2]:.2f}',refund=f'{a[3]:.2f}',net=f'{a[2]-a[3]:.2f}') for k,a in sorted(groups.items())]
    audit=dict(policy_id='ACTIVE-2026',raw_rows=len(raw),unique_records=len(latest),duplicate_or_superseded_rows=len(raw)-len(latest),void_records=void,invalid_records=sorted(invalid),included_records=included)
    priv=R/'private'/f'data-v{variant}';priv.mkdir(exist_ok=True)
    (priv/'expected.json').write_text(json.dumps(dict(summary=expected,audit=audit),ensure_ascii=False))
    (priv/'check.py').write_text('''import csv,json,subprocess,sys,tempfile
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
''')

manifest={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ['fixtures','private'] for p in (R/base).rglob('*') if p.is_file()}
(R/'evidence/input-manifest.json').write_text(json.dumps(manifest,indent=2))
(R/'evidence/protocol.json').write_text(json.dumps(dict(scope='Only OpenClaw and Hermes; new user instruction authorizes continuation',model='deepseek-flash',reasoning='high',cases='2 task types x 3 independent input variants x 2 products = 12 runs',order='paired alternating product order',timeout_seconds=600,outer_budget_CNY=50,new_incremental_exposure_cap_CNY=15,concurrency=1,no_new_paid_cloud=True,quality='all independent assertions and reproducibility; first attempt only; no human fixes',performance='completion wall time plus CPU and max RSS; count failures separately',cost='actual provider usage; published-price estimate, not exclusive invoice',fault_and_mechanism_tests='separate from clean task timings',limitations=['three variants are not three repetitions of an identical sample','no production SLA or all-task quality claim','outer evaluator isolation is not product-native isolation']),ensure_ascii=False,indent=2))
print('Prepared 6 public fixtures, 6 hidden acceptance packages, and frozen input hashes. No inference.')
