"""Prepare paired deterministic data tasks, with answers outside Agent workspaces."""
import csv
import hashlib
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
rng=random.Random(20261022)
regions=['east','west','north','south']
orders=[]
totals={region:0 for region in regions}
counts={region:0 for region in regions}
for index in range(120):
    region=regions[index%4]
    status=rng.choice(['paid','paid','cancelled','pending'])
    amount=rng.randrange(100,100000)
    orders.append({'order_id':f'order-{index:04d}','region':region,'status':status,'amount_cents':amount})
    if status=='paid':totals[region]+=amount;counts[region]+=1
expected={'paid_amount_cents_by_region':totals,'paid_count_by_region':counts}
prompt='''读取当前工作目录的 orders.csv，仅统计 status 为 paid 的记录。按 region 汇总 amount_cents（整数分）及订单数量，把结果写入当前目录 result.json，严格使用以下 JSON 结构：{"paid_amount_cents_by_region":{"east":整数,"west":整数,"north":整数,"south":整数},"paid_count_by_region":{"east":整数,"west":整数,"north":整数,"south":整数}}。请实际生成文件并检查结果。只访问当前任务目录，不访问网络，不安装依赖。'''
for framework in ['openclaw','hermes']:
    workspace=ROOT/f'fixtures/real-pilot/{framework}/csv-aggregation'
    workspace.mkdir(parents=True,exist_ok=True)
    with (workspace/'orders.csv').open('w',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=['order_id','region','status','amount_cents']);writer.writeheader();writer.writerows(orders)
    (workspace/'task.txt').write_text(prompt)
spec={'schema_version':1,'case_id':'csv-aggregation-v1','input_rows':len(orders),'input_sha256':hashlib.sha256((ROOT/'fixtures/real-pilot/openclaw/csv-aggregation/orders.csv').read_bytes()).hexdigest(),'expected':expected,'task_prompt':prompt,'verification':'Parse result.json from each workspace and require exact dictionary equality; answers are not installed in Agent workspaces.','real_model':{'base_url':'https://api.deepseek.com','model':'deepseek-flash','thinking':'disabled','temperature':0,'max_output_tokens_per_request':4096},'status':'prepared_not_run'}
(ROOT/'results/real-pilot-spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
print(json.dumps({'status':'prepared_not_run','case':spec['case_id'],'input_rows':len(orders),'input_sha256':spec['input_sha256']}))
