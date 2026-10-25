import csv,datetime as dt,json,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def median(xs):return statistics.median(xs) if xs else None
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
records=[]
for p in sorted(R.glob('runs/*/*/result.json')):
 d=json.loads(p.read_text());u=[x.get('usage',{}) for x in d['responses']]
 row={k:d[k] for k in ['task','family','passed','elapsed_seconds','calls','cost_estimate_CNY','checks_passed','checks_total']}
 row.update(input_tokens=sum(x.get('prompt_tokens',0) for x in u),cached_input_tokens=sum(x.get('prompt_cache_hit_tokens',0) for x in u),output_tokens=sum(x.get('completion_tokens',0) for x in u),request_duration_sum_seconds=sum(x['duration_seconds'] for x in d['responses']),terminal_usage_complete=all(x.get('usage_completeness')=='terminal_observed' for x in d['responses']),human_interventions=d['human_interventions'])
 timeline=[json.loads(l) for l in (p.parent/'api-audit.jsonl').read_text().splitlines()]
 sent=[x for x in timeline if x.get('event')=='request']
 row['first_model_request_after_start_seconds']=(dt.datetime.fromisoformat(sent[0]['at_utc'])-dt.datetime.fromisoformat(d['started'])).total_seconds() if sent else None
 row['all_requests_fixed_flash']=all(x.get('model')=='deepseek-flash' for x in sent)
 obs=p.parent/'sampled-resources.json'
 if obs.exists():
  v=json.loads(obs.read_text());row.update(peak_pss_MiB=v['peak_sum_pss_kib']/1024,resource_sample_complete=v['full_from_start'])
 records.append(row)
assert len(records)==12,'Finish the fixed twelve-run batch before aggregation'
assert all(r['all_requests_fixed_flash'] for r in records)
aggregates=[]
for family in ['openclaw','hermes']:
 for typ in ['code','data','all']:
  rs=[r for r in records if r['family']==family and (typ=='all' or r['task'].startswith(typ))]
  aggregates.append(dict(family=family,task_type=typ,n=len(rs),passed=sum(r['passed'] for r in rs),wall_seconds_sum=sum(r['elapsed_seconds'] for r in rs),wall_seconds_median=median([r['elapsed_seconds'] for r in rs]),wall_seconds_range=[min(r['elapsed_seconds'] for r in rs),max(r['elapsed_seconds'] for r in rs)],model_calls_sum=sum(r['calls'] for r in rs),model_CNY_estimate_sum=sum(r['cost_estimate_CNY'] for r in rs),input_tokens_sum=sum(r['input_tokens'] for r in rs),output_tokens_sum=sum(r['output_tokens'] for r in rs)))
pairs=[]
for typ in ['code','data']:
 for v in range(1,4):
  name=f'{typ}-v{v}';a=next(r for r in records if r['task']==name and r['family']=='openclaw');b=next(r for r in records if r['task']==name and r['family']=='hermes')
  pairs.append(dict(task=name,openclaw_pass=a['passed'],hermes_pass=b['passed'],OC_over_H_wall_ratio=a['elapsed_seconds']/b['elapsed_seconds'],OC_over_H_model_cost_ratio=a['cost_estimate_CNY']/b['cost_estimate_CNY'],memory_paired_complete=a.get('resource_sample_complete',False) and b.get('resource_sample_complete',False),OC_over_H_peak_pss_ratio=a.get('peak_pss_MiB',0)/b['peak_pss_MiB'] if b.get('peak_pss_MiB') and a.get('resource_sample_complete') and b.get('resource_sample_complete') else None))
save(R/'results/task-analysis.json',dict(records=records,aggregates=aggregates,pairs=pairs,scope='Two constructed task types, three input variants each; no human repairs. Same DeepSeek Flash high-reasoning main model. Not a general coding intelligence ranking.',pricing='2026-10-24 Saturday CNY off-peak: uncached input1, cached input0.02, output4 per million tokens; API usage estimate, not exclusive invoice.',resource_scope='Complete paired /proc tree peak PSS samples only; outer time launcher CPU/RSS excluded.'))
with (R/'results/task-results.csv').open('w',newline='') as f:
 fields=sorted(set().union(*(r.keys() for r in records)));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
mechanisms=[]
for p in sorted(R.glob('runs-mechanisms/*/*/result.json')):
 d=json.loads(p.read_text());kind=p.parent.parent.name;row=dict(kind=kind,family=d['family'],passed=d.get('passed'),exit_code=d.get('exit_code'))
 if kind=='mcp':
  row['by_tool_count']=[dict(tool_count=n,median_ms=median([x['duration_ms'] for x in d['batches'] if x['count']==n and not x['warmup'] and x['valid']]),median_overlap=median([x['max_overlap'] for x in d['batches'] if x['count']==n and not x['warmup'] and x['valid']]),n=sum(x['count']==n and not x['warmup'] and x['valid'] for x in d['batches'])) for n in [1,4,8]]
 elif kind=='http-scale':
  row['by_concurrency']=[dict(concurrency=n,median_seconds=median([x['seconds'] for x in d['batches'] if x['concurrency']==n]),median_throughput=median([x['throughput'] for x in d['batches'] if x['concurrency']==n]),correct_requests=sum(x['completed'] for x in d['batches'] if x['concurrency']==n),total_requests=sum(x['concurrency'] for x in d['batches'] if x['concurrency']==n)) for n in [1,2,4,8]]
 elif kind.startswith('plugin'):
  row.update({k:d.get(k) for k in ['valid_comparison','plugin_loaded_and_called','crash_entered','main_loop_survived']})
 elif kind.startswith('retry'):
  row.update({k:d.get(k) for k in ['injected_status','actual_retry_wait_seconds','retry_after_seconds']});row['retry_after_honored']=d['passed'];row['native_completion_after_retry']=d.get('exit_code')==0 and d.get('actual_retry_wait_seconds') is not None
 elif kind=='timeout':row['observations']=d.get('observations')
 elif kind.startswith('deny'):row.update({k:d.get(k) for k in ['side_effect_created','tool_results_present']})
 mechanisms.append(row)
save(R/'results/mechanism-analysis.json',mechanisms)
print(json.dumps({'aggregates':aggregates,'memory_paired':[p for p in pairs if p['memory_paired_complete']],'mechanism_records':len(mechanisms)},ensure_ascii=False,indent=2))
