import json,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[1];frameworks={}
for fw,entry in [('openclaw','agentExecCommand'),('hermes','AIAgent + run_conversation + close')]:
 p=R/f'raw/extended-resources/turn-{fw}.json';raw=json.loads(p.read_text());d=[x for x in raw['samples']if not x['warmup']]
 assert len(d)==10,(fw,len(d))
 for x in d:
  if fw=='openclaw':assert x.get('correct') is True and x['result']['toolCalls']==0
  else:assert x['correct'] is True and x['tool_count']==0
 v=[x['cpu_ms']for x in d];frameworks[fw]={'values':v,'passed':len(d),'total':len(d),'entrypoints':[entry], 'evidence':[f'raw/extended-resources/turn-{fw}.json'],'median_ms':statistics.median(v)}
events=[json.loads(x)for x in (R/'raw/extended-resources/provider-requests.jsonl').read_text().splitlines()];latest=[x for x in events if x['case']=='unicode'and x['body'].get('max_completion_tokens')==128 and len(x['body'].get('tools')or[])==0][-13:]
assert len(latest)==13 and all(x['case']=='unicode'and x['passed']and len(x['body'].get('tools')or[])==0 for x in latest),'OpenClaw final wire requests must be successful and advertise no tools'
hermes_wire=[x for x in events if x['case']=='unicode'and x['body'].get('max_tokens')==128 and x['body'].get('reasoning_effort')=='none' and len(x['body'].get('tools')or[])==0][-13:]
assert len(hermes_wire)==13 and all(x['passed']for x in hermes_wire)
proof=R/'raw/extended-resources/minimal-turn-wire-proof.json';proof.write_text(json.dumps({'openclaw':latest,'hermes':hermes_wire},ensure_ascii=False,indent=2));frameworks['openclaw']['evidence'].append(str(proof.relative_to(R)));frameworks['hermes']['evidence'].append(str(proof.relative_to(R)))
row={'row':20,'title':'资源轻量化','metric':'预热后完整最小对话CPU时间','unit':'ms','direction':'lower','scope':'Complete native minimal text-turn CPU time, three same-process warmups followed by ten measured fresh sessions per framework; same deterministic local OpenAI-compatible endpoint, 128k context, output cap128, reasoning disabled, temperature omitted and no advertised tools. OpenClaw production agentExecCommand versus Hermes AIAgent construction, run_conversation and close. CPU = /proc/self/stat user + system + waited child CPU; 100Hz OS clock gives 10ms resolution.','limitations':['This is the fixed source-API harness (Node 24 with tsx/jiti versus Hermes Python), not packaged-release or whole-Gateway performance. Imports and first-turn compilation are excluded, but native on-demand source/runtime work inside later turns remains included.','Measures CPU for a trivial successful framework turn with no tools; excludes actual LLM inference, real API latency/charges, production messaging gateways and enabled plugin stacks.','Active detached descendants not yet reaped are not included by cutime/cstime; tool-free runs do not spawn task workloads. Node worker-thread CPU is part of process CPU.','Runtime semantics and lifecycle implementation differ; this is the measured harness resource cost, not a general speed ranking. Idle-controller constructor and unstable resident-memory diagnostics are separate secondary artifacts.'],'status':'measured','frameworks':frameworks}
(R/'results/extended-row-20.json').write_text(json.dumps(row,ensure_ascii=False,indent=2));print(json.dumps({fw:v['median_ms']for fw,v in frameworks.items()}))
