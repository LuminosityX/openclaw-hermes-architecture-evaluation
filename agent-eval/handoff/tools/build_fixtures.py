#!/usr/bin/env python3
"""Deterministic offline fixture builder. Never invokes a model."""
import csv, io, json, random, re, textwrap
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def put(path,text):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError(f"Refusing to overwrite {p}")
    p.write_text(textwrap.dedent(text).lstrip(),encoding="utf-8")
def jput(path,obj):put(path,json.dumps(obj,ensure_ascii=False,indent=2)+"\n")

PAGINATION_GOOD='''
def paginate(items, page, page_size):
    if type(page) is not int or type(page_size) is not int or page < 1 or page_size < 1:
        raise ValueError("positive integer page and page_size required")
    total = (len(items) + page_size - 1) // page_size
    start = (page - 1) * page_size
    return {"items": list(items[start:start + page_size]), "total_pages": total, "has_next": page < total}
'''
PAGINATION_BAD='''
def paginate(items, page, page_size):
    if page < 1 or page_size < 1:
        raise ValueError("positive page and page_size required")
    total = len(items) // page_size
    start = page * page_size
    return {"items": list(items[start:start + page_size]), "total_pages": total, "has_next": page <= total}
'''
TRANSITION_MODEL='''
ALLOWED = {"todo": {"doing"}, "doing": {"done", "todo"}, "done": set()}
def can_transition(source, target):
    return source == target
'''
TRANSITION_MODEL_GOOD='''
ALLOWED = {"todo": {"doing"}, "doing": {"done", "todo"}, "done": set()}
def can_transition(source, target):
    return source in ALLOWED and target in ALLOWED and (source == target or target in ALLOWED[source])
'''
TRANSITION_SERVICE_GOOD='''
from .model import ALLOWED, can_transition
def transition_many(store, ids, target):
    if target not in ALLOWED:
        raise ValueError("unknown target")
    if not isinstance(ids, (list, tuple)) or any(not isinstance(x, str) for x in ids):
        raise ValueError("ids must be a list or tuple of strings")
    unique = list(dict.fromkeys(ids))
    staged = []
    for ident in unique:
        item = store.get(ident)
        if not can_transition(item["status"], target):
            raise ValueError("invalid transition")
        item["status"] = target
        staged.append(item)
    for item in staged:
        store.save(item)
    return [store.get(x) for x in unique]
'''

def clean_csv(rows, regions):
    clean=[];seen=set();invalid=duplicates=0
    by={r:{"rows":0,"quantity":0,"amount_cents":0} for r in sorted(regions)}
    for raw in rows:
        r={k:(v or "").strip() for k,v in raw.items()}
        if not r["id"] or r["region"] not in regions or not re.fullmatch(r"[0-9]+",r["quantity"]) or int(r["quantity"])<1 or not re.fullmatch(r"[0-9]+\.[0-9]{2}",r["unit_price"]):
            invalid+=1;continue
        if r["id"] in seen:duplicates+=1;continue
        seen.add(r["id"]);quantity=int(r["quantity"]);a,b=r["unit_price"].split('.');cents=int(a)*100+int(b)
        r["quantity"]=str(quantity);r["unit_price"]=f"{cents//100}.{cents%100:02d}";clean.append(r)
        by[r["region"]]["rows"]+=1;by[r["region"]]["quantity"]+=quantity;by[r["region"]]["amount_cents"]+=quantity*cents
    summary={"input_rows":len(rows),"kept_rows":len(clean),"invalid_rows":invalid,"duplicate_rows":duplicates,
             "total_quantity":sum(x["quantity"] for x in by.values()),"total_amount_cents":sum(x["amount_cents"] for x in by.values()),"by_region":by}
    return {"columns":["id","region","quantity","unit_price"],"clean":clean,"summary":summary}

def build():
    for v in range(1,4):
        variant=f"v{v}";base=f"tasks/W1/{variant}";private=f"evaluator_private/W1/{variant}"
        seed=100+v
        put(f"{base}/pagination.py",PAGINATION_BAD)
        put(f"{base}/test_public.py",'''
import unittest
from pagination import paginate
class PublicTests(unittest.TestCase):
    def test_shape(self):
        result=paginate([1,2,3,4,5,6],1,2)
        self.assertEqual(set(result),{"items","total_pages","has_next"})
        self.assertLessEqual(len(result["items"]),2)
    def test_invalid(self):
        with self.assertRaises(ValueError):paginate([1],0,1)
if __name__=="__main__":unittest.main()
''')
        jput(f"{base}/example.json",{"items":[f"case{v}-{i}" for i in range(7+v)],"page":1+v,"page_size":2+v})
        put(f"{base}/PROMPT.md",'''
# 任务W1：分页缺陷修复
修复 pagination.py 的 paginate(items, page, page_size)，保持公开接口和返回字段。
page 从1开始；page和page_size必须是正整数，bool/浮点/字符串均应抛ValueError。
total_pages向上取整，空集合为0；越界页返回空items；has_next仅表示还有非空后续页。
不得修改输入集合；支持list与tuple；返回items为list。
请运行本地测试，可补充自己的测试，提交代码和简短验证说明。不要删除或改写已有公开测试来绕过要求。
不需要联网或安装依赖。验收还包含本工作区外的独立测试。
''')
        put(f"{private}/reference.py",PAGINATION_GOOD)
        put(f"{private}/check.py",f'''
import copy,random,sys,unittest
sys.path.insert(0,sys.argv.pop(1))
from pagination import paginate
class HiddenTests(unittest.TestCase):
    def test_cases(self):
        rng=random.Random({seed})
        for _ in range(50):
            n=rng.randint(0,31);size=rng.randint(1,9);page=rng.randint(1,12)
            items=[{{"key":rng.randint(0,1000)}} for _ in range(n)];before=copy.deepcopy(items)
            expected={{"items":items[(page-1)*size:page*size],"total_pages":(n+size-1)//size,"has_next":page<(n+size-1)//size}}
            self.assertEqual(paginate(items,page,size),expected)
            self.assertEqual(items,before)
            self.assertEqual(paginate(tuple(items),page,size),expected)
    def test_invalid(self):
        for bad in [0,-1,True,False,1.5,"2",None]:
            with self.assertRaises(ValueError):paginate([1],bad,2)
            with self.assertRaises(ValueError):paginate([1],1,bad)
if __name__=="__main__":unittest.main()
''')

        base=f"tasks/W2/{variant}";private=f"evaluator_private/W2/{variant}"
        put(f"{base}/queueboard/__init__.py",'')
        put(f"{base}/queueboard/model.py",TRANSITION_MODEL)
        put(f"{base}/queueboard/store.py",'''
from copy import deepcopy
class TaskStore:
    def __init__(self,tasks): self._tasks={x["id"]:deepcopy(x) for x in tasks}
    def get(self,ident): return deepcopy(self._tasks[ident])
    def save(self,item): self._tasks[item["id"]]=deepcopy(item)
    def all(self): return [deepcopy(x) for x in self._tasks.values()]
''')
        put(f"{base}/queueboard/service.py",'''
def transition_many(store, ids, target):
    raise NotImplementedError("implement atomic batch transition")
''')
        put(f"{base}/test_public.py",'''
import unittest
from queueboard.store import TaskStore
class PublicTests(unittest.TestCase):
    def test_store_copy(self):
        s=TaskStore([{"id":"a","status":"todo","title":"keep"}]);x=s.get("a");x["title"]="changed"
        self.assertEqual(s.get("a")["title"],"keep")
if __name__=="__main__":unittest.main()
''')
        jput(f"{base}/sample_tasks.json",[{"id":f"{variant}-task{i}","title":f"Task {i}","status":["todo","doing","done"][i%3]} for i in range(6)])
        put(f"{base}/PROMPT.md",'''
# 任务W2：原子批量状态变更
在queueboard中实现model.can_transition与service.transition_many(store, ids, target)。
合法状态为todo、doing、done；合法变更为todo→doing、doing→todo、doing→done及合法状态自身；done不能退回。
ids须为list或tuple且元素均为字符串，否则ValueError；未知target为ValueError；未知id为KeyError。
重复id按首次出现去重；结果按去重后的请求顺序返回；空ids返回[]（仍需校验target）。
先校验整批，再写入：任何id或状态不合法都不能改变任何原记录。只更新status，保留title等其他字段。
保持TaskStore公开接口和已有测试，增加自己的测试并运行，提交实现与验证说明。不需要联网或第三方依赖。
''')
        put(f"{private}/reference_model.py",TRANSITION_MODEL_GOOD);put(f"{private}/reference_service.py",TRANSITION_SERVICE_GOOD)
        put(f"{private}/check.py",f'''
import copy,sys,unittest
sys.path.insert(0,sys.argv.pop(1))
from queueboard.model import can_transition
from queueboard.store import TaskStore
from queueboard.service import transition_many
class HiddenTests(unittest.TestCase):
    def fresh(self):return TaskStore([{{"id":"a{v}","status":"todo","title":"A","extra":7}},{{"id":"b{v}","status":"doing","title":"B"}},{{"id":"c{v}","status":"done","title":"C"}}])
    def test_model(self):
        for s in ["todo","doing","done","bad"]:
            for t in ["todo","doing","done","bad"]:
                good=s in ("todo","doing","done") and t in ("todo","doing","done") and (s==t or (s,t) in [("todo","doing"),("doing","todo"),("doing","done")])
                self.assertEqual(can_transition(s,t),good)
    def test_order_and_fields(self):
        s=self.fresh();r=transition_many(s,["b{v}","a{v}","b{v}"],"doing")
        self.assertEqual([x["id"] for x in r],["b{v}","a{v}"]);self.assertEqual(s.get("a{v}")["extra"],7)
        r[1]["title"]="bad";self.assertEqual(s.get("a{v}")["title"],"A")
    def test_atomic(self):
        for ids,target,exc in [(["a{v}","missing"],"doing",KeyError),(["a{v}","c{v}"],"doing",ValueError),(["a{v}"],"unknown",ValueError)]:
            s=self.fresh();before=s.all()
            with self.assertRaises(exc):transition_many(s,ids,target)
            self.assertEqual(s.all(),before)
    def test_inputs(self):
        for ids in ["a{v}",[1],None]:
            with self.assertRaises(ValueError):transition_many(self.fresh(),ids,"doing")
        self.assertEqual(transition_many(self.fresh(),[],"todo"),[])
        with self.assertRaises(ValueError):transition_many(self.fresh(),[],"bad")
if __name__=="__main__":unittest.main()
''')

        base=f"tasks/W3/{variant}";private=f"evaluator_private/W3/{variant}"
        rng=random.Random(20261024+v);regions=["east","north","west"];rows=[]
        for i in range(1,181):
            row={"id":f"V{v}-{i:04d}","region":rng.choice(regions),"quantity":str(rng.randint(1,9)),"unit_price":f"{rng.randint(0,150)}.{rng.randint(0,99):02d}"}
            if i%13==0:row["quantity"]="0"
            elif i%17==0:row["unit_price"]="12.345"
            elif i%19==0:row["region"]="unknown"
            elif i%23==0:row["id"]=" "
            if i%11==0:row["id"]=" "+row["id"]+" ";row["region"]=" "+row["region"]
            rows.append(row)
            if i%29==0:rows.append(dict(row))
        buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=["id","region","quantity","unit_price"]);w.writeheader();w.writerows(rows)
        put(f"{base}/input.csv",buf.getvalue());jput(f"{private}/expected.json",clean_csv(rows,regions))
        put(f"{base}/PROMPT.md",'''
# 任务W3：数据清洗与汇总
读取input.csv，输出output/clean.csv和output/summary.json。可编写脚本，不需要联网。
对所有字段先去首尾空白。有效行要求：id非空；region为east/north/west之一；quantity为仅含数字且>=1的整数；unit_price为非负十进制、恰好两位小数。
先校验有效性，再按id保留首个有效记录。无效行计invalid_rows；后续有效重复id计duplicate_rows。
clean.csv保持原有效行顺序，列顺序id,region,quantity,unit_price；quantity规范为十进制整数，价格规范为两位小数。
summary.json仅包含以下字段：input_rows、kept_rows、invalid_rows、duplicate_rows、total_quantity、total_amount_cents、by_region。
金额用整数分计算quantity×unit_price；by_region必须含east/north/west，每项仅包含字段rows、quantity、amount_cents（没有数据也保留0）。
提交输出文件及简短核验说明。不要修改input.csv。只统计本输入文件的数据。
''')

        base=f"tasks/W4/{variant}";private=f"evaluator_private/W4/{variant}"
        cap=[180,240,360][v-1];con=[4,6,8][v-1];old=cap//2
        docs={
        "DOC-01":f"# 旧生产公告\n日期：2026-09-20。Atlas导出服务：每批最多{old}项，并发2。生产规则。",
        "DOC-02":f"# 当前生产规则\n日期：2026-10-18。替代DOC-01。Atlas每批最多{cap}项，账户并发上限{con}。新规则已在生产生效。",
        "DOC-03":f"# 测试环境实验\n日期：2026-10-20。在staging环境完成每批{cap*2}项测试。尚未批准用于生产，不能据此对客户承诺。",
        "DOC-04":"# 社区反馈\n日期：2026-10-21。用户声称导出没有任何上限，但没有提供生产配置或验证记录；这不是官方规则。",
        "DOC-05":"# 运维记录\n日期：2026-10-22。昨天的队列阻塞已经处理。新增告警用于发现长时间等待；该记录不构成永不阻塞或永不丢失的保证。"}
        for ident,body in docs.items():put(f"{base}/sources/{ident}.md",body+"\n")
        put(f"{base}/PROMPT.md",'''
# 任务W4：有证据的服务说明
仅根据sources内冻结资料，生成中文report.md，包含“结论”“依据”“冲突与未确认”三个部分。
回答当前生产每批上限和并发；能否承诺测试环境中的更大容量；如何处理旧公告与社区说法；运维记录能证明什么。
每个实质结论用[DOC-编号]引用相应资料。区分生产、测试、传闻与未确认事实。不访问互联网，不创造额外事实。
报告要简洁并适合交给未读过资料的同事，不要只罗列原文。
''')
        jput(f"{private}/rubric.json",{"required_sections":["结论","依据","冲突与未确认"],"required_citations":["DOC-02","DOC-03","DOC-05"],
            "mandatory_claims":[f"当前生产每批上限{cap}，并发{con}，依据DOC-02",f"{cap*2}仅测试环境，不可承诺生产，依据DOC-03",f"DOC-01的{old}/2已过期，DOC-04缺少验证", "新增告警不保证永不阻塞或丢失，依据DOC-05"],
            "critical_failures":["将staging容量当生产","采用旧上限为当前","承诺零故障/零丢失","虚构来源或引文"],"decision":"人工逐项审阅；关键失败任一成立则不通过；不能仅凭关键词自动算通过"})

        base=f"tasks/W5/{variant}";nonce=f"PORTABLE-TASK-{v}-1024"
        put(f"{base}/context.md",f"任务校验号：{nonce}\n只处理本测试项目；批准前不得执行受控写入；最后输出handoff_result.json。\n")
        put(f"{base}/PROMPT.md",f'''
# 任务W5：跨端工作
读取context.md，为本项目生成简短执行计划并保留校验号{nonce}。协调者会在另一个官方入口追加指令并通过原生审批界面批准一个受控操作。
暂不要执行需要审批的操作；等待平台上的真实后续输入，不得自己生成“用户已批准”的记录。
收到实际后续指令后继续同一任务，最终生成handoff_result.json，记录校验号、最终收到的要求和可核验产物。
''')
        put(f"{base}/MANUAL_CHECKLIST.md",'''
# 仅评估协调者使用
1. 用产品正式权限规则让一个安全受控写入需要原生审批；先确认规则确实会触发，不能只靠提示词等待。
2. 从桌面/初始入口开始；记录session/task/执行主机ID和计划输出。
3. 用另一官方入口打开同一任务，追加“最终结果增加reviewed_on_second_surface=true”，批准准确动作。
4. 返回初始入口，核对校验号、要求、审批操作参数、执行主机和产物一致。
5. 单列补输上下文、重新建任务、消息转发、人工复制文件等步骤，不能冒充无缝接续。
6. 如无可用第二端账户/设备，状态记未执行而非产品不支持。纯生成JSON文件不是自动通过。
''')

        base=f"tasks/W6/{variant}"
        put(f"{base}/long_job.py",'''
import argparse,json,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--steps',type=int,default=12);p.add_argument('--delay',type=float,default=5);a=p.parse_args()
if not 1<=a.steps<=30 or not 0<=a.delay<=10:raise SystemExit('out of fixture bounds')
out=Path('job_output');out.mkdir(exist_ok=True);journal=out/(a.run_id+'.jsonl')
with journal.open('x') as f:
    for step in range(1,a.steps+1):
        f.write(json.dumps({'run_id':a.run_id,'step':step,'time_ns':time.time_ns()})+'\\n');f.flush();time.sleep(a.delay)
    f.write(json.dumps({'run_id':a.run_id,'completed':True,'steps':a.steps})+'\\n');f.flush()
print(json.dumps({'run_id':a.run_id,'completed':True,'journal':str(journal)}))
''')
        put(f"{base}/PROMPT.md",f'''
# 任务W6：后台工作生命周期
运行本目录long_job.py：run-id读取工作区RUN_ID.txt中的实际运行ID，steps={9+v*3}，delay=5。
使用该产品正式支持的执行方式完成任务，不改脚本、不缩短延迟、不编造完成记录。
工作结束后检查日志完整性，输出job_report.json，包含run_id、completed、实际step数和日志路径。
协调者会按测试卡关闭客户端或断开连接；如执行中断，明确报告未知/未完成与可用恢复方式，不把重跑旧命令掩盖成原执行续接。
''')
        put(f"{base}/MANUAL_CHECKLIST.md",'''
# 仅评估协调者使用
开始后等待至少两个step，再关闭查看客户端；记录实际Agent和命令是否仍活跃，返回同一任务核对完整日志。
关闭客户端、网络断开、执行主机离线是三种独立变体，不能一次混做。
run-id每次唯一，脚本拒绝覆盖旧日志；重跑须新运行ID并记人工补救。
对官方云任务只能做用户可控制的断连/返回，不假装杀掉供应商内部进程。
该夹具是命令生命周期测试，不能单独推出多轮模型任务崩溃可恢复。
''')

if __name__=='__main__':build();print('Built 18 public task workspaces and private evaluators; no product tests run.')
