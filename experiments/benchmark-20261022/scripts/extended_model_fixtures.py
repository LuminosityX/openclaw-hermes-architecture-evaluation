"""Deterministic paired tasks for actual model/harness evaluation, with external answers."""
import csv
import hashlib
import io
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
cases=[]
rng=random.Random(20261023)
def add(row,label,files,prompt,expected,skills=False):
    case_id=f'row{row:02d}-{label}'
    workspaces={}
    for framework in ['openclaw','hermes']:
        path=ROOT/f'fixtures/extended-models/{framework}/{case_id}'
        path.mkdir(parents=True,exist_ok=True)
        for name,content in files.items():
            target=path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
        workspaces[framework]=str(path)
    cases.append({'row':row,'case_id':case_id,'prompt':prompt+'\n只访问当前任务目录，不访问网络、不安装依赖。请完成后停止。','expected':expected,'output_file':'result.json','workspaces':workspaces,'skills':skills})

for i in range(10):
    numbers=[rng.randrange(-500,1000) for _ in range(40)]
    if i%3==0:
        data={'numbers':numbers};expected={'sum_positive_even':sum(n for n in numbers if n>0 and n%2==0),'count_negative':sum(n<0 for n in numbers)}
        prompt='读取input.json，计算numbers中正偶数之和、负数个数。写result.json，键严格为sum_positive_even和count_negative，值为整数。'
    elif i%3==1:
        data={'records':[{'id':f'r{j%7}','version':j,'value':n} for j,n in enumerate(numbers)]}
        expected={'latest':{f'r{j}':next(x['value'] for x in reversed(data['records']) if x['id']==f'r{j}') for j in range(7)}}
        prompt='读取input.json，每个records.id仅保留version最大记录的value。写result.json，格式为{"latest":{"r0":整数,...,"r6":整数}}。'
    else:
        data={'values':[str(n)+'  ' for n in numbers]};expected={'unique_sorted':sorted(set(numbers))}
        prompt='读取input.json，将values去空白转整数、去重并按数值升序排序，写result.json，格式为{"unique_sorted":[整数,...]}。'
    files={'input.json':json.dumps(data)}
    if i>=5:
        files['check.py']='import json\nfrom pathlib import Path\np=Path("result.json")\nassert p.exists(), "MISSING_RESULT: generate result.json then run check.py again"\nx=json.loads(p.read_text())\nassert isinstance(x,dict)\nprint("RESULT_PRESENT")\n'
        prompt='首先执行python3 check.py；如报缺少结果，请继续完成任务，再次执行检查。'+prompt
    add(7,f'normal-and-feedback-{i:02d}',files,prompt,expected)

skills=[('csv-audit','统计CSV表格中的金额、数量和异常记录'),('text-clean','清理文本中的空白、标点和大小写'),('invoice-check','核验发票号码、税额和付款信息'),('meeting-plan','整理会议议程和参会安排'),('config-review','检查应用配置字段、默认值和格式')]
utterances=['请帮我核对这张票据的税额和付款字段','这份逗号分隔数据需要按组汇总金额','把这段文字多余空格和大小写统一一下','为下周讨论整理一份议程和参会安排','检查这个应用设置文件有没有缺字段','发票编号和应付款金额需要校对','统计CSV里的记录数和异常行','整理会议讨论顺序以及人员安排','把配置参数的默认值和类型核对一下','清理文本标点并统一字母大小写']
targets=['invoice-check','csv-audit','text-clean','meeting-plan','config-review','invoice-check','csv-audit','meeting-plan','config-review','text-clean']
for i,(utterance,target) in enumerate(zip(utterances,targets)):
    files={}
    markers={}
    for name,description in skills:
        marker=hashlib.sha256(f'{i}:{name}:skill-routing'.encode()).hexdigest()[:18];markers[name]=marker
        files[f'skills/{name}/SKILL.md']=f'---\nname: {name}\ndescription: {description}\n---\n\nThis is a synthetic intent-routing task. If this skill matches the user request, write result.json with exactly {{"skill":"{name}","marker":"{marker}"}}. Do not perform external operations.\n'
    add(11,f'skill-intent-{i:02d}',files,utterance+'。这是技能路由测试：请选择最匹配的现有技能，读取其完整说明，并按说明生成result.json；无需真实操作外部业务。',{'skill':target,'marker':markers[target]},skills=True)

docs={}
facts={}
for i in range(20):
    name=f'policy-{i:02d}.md';code=f'P-{rng.randrange(10000,99999)}';quota=rng.randrange(100,900)
    facts[i]={'code':code,'quota':quota,'source':f'docs/{name}'}
    docs[f'docs/{name}']=f'# Procedure {i:02d}\nCurrent version: 2026-10-22\nApproval code: {code}\nDaily quota: {quota}\nThis document supersedes previous versions.\n'
    docs[f'docs/archive-{i:02d}.md']=f'# Procedure {i:02d}\nObsolete version: 2025-01-01\nApproval code: OLD-{i}\nDaily quota: 1\n'
docs['docs/INDEX.md']='\n'.join(f'- Procedure {i:02d}: policy-{i:02d}.md (current), archive-{i:02d}.md (obsolete)' for i in range(20))
for i in range(10):
    a,b=2*i,2*i+1
    expected={'procedures':[{'id':a,**facts[a]},{'id':b,**facts[b]}],'quota_sum':facts[a]['quota']+facts[b]['quota']}
    prompt=f'当前目录docs中有知识资料和过期版本。请检索流程{a:02d}与{b:02d}的当前审批code和daily quota，注明相对路径source，并计算两项quota之和。写result.json，严格结构为{{"procedures":[{{"id":{a},"code":"...","quota":整数,"source":"docs/..."}},{{"id":{b},"code":"...","quota":整数,"source":"docs/..."}}],"quota_sum":整数}}。以当前版本为准。'
    add(15,f'knowledge-grounded-{i:02d}',docs,prompt,expected)

(ROOT/'results/extended-model-cases.json').write_text(json.dumps({'cases':cases,'seed':20261023},ensure_ascii=False,indent=2))
print(json.dumps({'cases':len(cases),'rows':sorted({x['row'] for x in cases})}))
