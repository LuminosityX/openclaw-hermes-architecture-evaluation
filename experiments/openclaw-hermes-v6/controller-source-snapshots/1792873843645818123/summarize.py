"""Read-only evidence aggregation; no inferred product grades or model calls."""
import csv,html,json,math,statistics,time
from pathlib import Path
from runtime import R,save

def main():
 cases=[]
 for p in sorted((R/'runs/formal').glob('*/*/result.json')):
  d=json.loads(p.read_text());resources=json.loads((p.parent/'resources.json').read_text());cases.append({k:d.get(k) for k in ['task','variant','repeat','family','passed','failure','elapsed_seconds','model_calls','cost_estimated_CNY','cost_incomplete','checks_passed','checks_total']}|dict(peak_memory_MiB=resources['peak_memory_bytes']/1048576,cpu_seconds=resources['cpu']['usage_usec']/1e6,evidence=str(p.relative_to(R))))
 for case in cases:
  raw_flag=case['cost_incomplete'];file=R/case['evidence'];audit=file.parent/'usage-reconciliation.json'
  if audit.exists():case['cost_incomplete']=json.loads(audit.read_text())['cost_incomplete_reconciled']
  case['original_cost_incomplete_flag']=raw_flag
 grouped={}
 for c in cases:grouped.setdefault((c['task'],c['variant'],c['repeat']),{})[c['family']]=c
 paired=[]
 for (task,variant,repeat),fs in grouped.items():
  if set(fs)!=set(['openclaw','hermes']):continue
  a,b=fs['openclaw'],fs['hermes'];paired.append(dict(task=task,variant=variant,repeat=repeat,both_accepted=a['passed'] and b['passed'],seconds_oc=a['elapsed_seconds'],seconds_hermes=b['elapsed_seconds'],cost_oc=a['cost_estimated_CNY'],cost_hermes=b['cost_estimated_CNY'],memory_MiB_oc=a['peak_memory_MiB'],memory_MiB_hermes=b['peak_memory_MiB'],cpu_seconds_oc=a['cpu_seconds'],cpu_seconds_hermes=b['cpu_seconds']))
 status=dict(at=time.time(),formal_completed=len(cases),formal_planned=48,paired_completed=len(paired),cases=cases,pairs=paired,financial_cap=None,note='Only output-aligned stable-version formal runs. Earlier pilots/calibration excluded. One pair is not a stable overall ranking.')
 save(R/'results/current-comparison.json',status)
 if cases:
  with (R/'results/task-runs.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(cases[0]));w.writeheader();w.writerows(cases)
 if paired:
  with (R/'results/task-pairs.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
 def cell(v):return html.escape(str(round(v,4) if isinstance(v,float) else v))
 rows=''.join('<tr>'+''.join('<td>'+cell(c[k])+'</td>' for k in ['task','variant','repeat','family','passed','elapsed_seconds','model_calls','cost_estimated_CNY','peak_memory_MiB','cpu_seconds'])+'</tr>' for c in cases)
 text='''<!doctype html><meta charset="utf-8"><title>OpenClaw 与 Hermes：实验实时记录</title><style>body{font:16px system-ui;margin:32px;line-height:1.6;color:#182238}table{border-collapse:collapse}td,th{padding:8px 12px;border:1px solid #ccd5e2}th{background:#eef3fa}strong{color:#124c90}</style>'''
 text+='<h1>OpenClaw 与 Hermes：实验实时记录</h1><p><strong>'+str(len(cases))+'/48 次正式业务运行已完成，'+str(len(paired))+' 对可比结果。</strong>强/中/弱评级须等待对应机制实验与证据覆盖，缺测不填中。</p><p>固定 OpenClaw v2026.10.6、Hermes v0.22.5；同为 DeepSeek Flash/high，生成预算64K；同等工作区任务授权。费用单位人民币（API usage估算；完整性经原始回执复核，非流式旧标记校正未改变费用），内存为完整进程组 cgroup 峰值，CPU单位秒。</p><table><tr>'+''.join('<th>'+x+'</th>' for x in ['任务','变体','重复','产品','验收通过','耗时秒','API请求','费用元','峰值MiB','CPU秒'])+'</tr>'+rows+'</table><p>原始证据在 runs/formal；配置校准和旧试跑未混入。一次模型任务可能包含多次API请求。</p>'
 (R/'results/current-comparison.html').write_text(text)
 print(json.dumps(dict(completed=len(cases),paired=len(paired),passed_by_family={f:sum(c['passed'] for c in cases if c['family']==f) for f in ['openclaw','hermes']})))
if __name__=='__main__':main()
