"""Sequential matched MCP scheduling measurement in real framework conversations."""
import collections
import json
import os
import time
from run_initial import ROOT,NODE,TSX,PYTHON,ENV,run

COUNT=4
BATCHES=35
WARMUPS=5
DELAY=200
rows=[]
runs=[]
for framework in ['openclaw','hermes']:
    run_id=f'{framework}-mcp-formal-{time.time_ns()}'
    output=ROOT/f'raw/{framework}-mcp-batches-formal.json'
    if framework=='openclaw':
        prompt=ROOT/'fixtures/mcp-formal-prompt.txt'
        prompt.write_text(f'BENCH_RUN_ID={run_id} BENCH_TOOL_KIND=mcp BENCH_TOOL_COUNT={COUNT} BENCH_BATCHES={BATCHES} BENCH_DELAY_MS={DELAY}')
        ENV.update({'BENCH_TIMEOUT':'180','BENCH_SAMPLES':'1','BENCH_WARMUPS':'0','BENCH_RUN_ID':run_id,'BENCH_PROMPT_FILE':str(prompt),'BENCH_OUTPUT':str(output)})
        run([NODE,'--import',TSX,ROOT/'scripts/openclaw_agent_probe.mjs','formal',COUNT,DELAY,'mcp'],'mcp-formal-openclaw',ROOT/'sources/openclaw')
        native=json.loads(output.read_text());case=native['samples'][0];envelope=case['result']['envelope'];final=json.loads(envelope['final'])
        if not envelope['ok'] or case['result']['toolCalls']!=COUNT*BATCHES or envelope.get('toolSummary',{}).get('failures')!=0:
            raise RuntimeError('OpenClaw conversation/tool results invalid')
    else:
        run([PYTHON,ROOT/'scripts/hermes_mcp_batches.py','--batches',BATCHES,'--count',COUNT,'--warmups',WARMUPS,'--delay-ms',DELAY,'--run-id',run_id,'--output',output],'mcp-formal-hermes')
        native=json.loads(output.read_text())
        if not native.get('correct'):raise RuntimeError('Hermes conversation/tool results invalid')
        final=json.loads(native['final_response'])
    if final.get('run_id')!=run_id or final.get('observed_tool_results')!=COUNT*BATCHES or final.get('expected_tool_results')!=COUNT*BATCHES:
        raise RuntimeError('Final response does not account for all actual tool results')
    events=[json.loads(line) for line in (ROOT/'raw/tool-events.jsonl').read_text().splitlines() if line.strip()]
    events=[e for e in events if e['run_id']==run_id]
    by_id=collections.defaultdict(list)
    for event in events:by_id[event['id']].append(event)
    if set(by_id)!=set(range(COUNT*BATCHES)):raise RuntimeError('Missing or extra tool IDs')
    for index,values in by_id.items():
        if len(values)!=2 or {x['event'] for x in values}!={'start','end'}:raise RuntimeError('Repeated or missing actual tool execution')
        times={x['event']:x['timestamp_ns'] for x in values}
        if times['end']<=times['start']:raise RuntimeError('Invalid actual timestamps')
    requests=[json.loads(line) for line in (ROOT/'raw/model-requests.jsonl').read_text().splitlines() if line.strip()]
    requests=[r for r in requests if r['run_id']==run_id]
    if len(requests)!=BATCHES+1 or [r['returned_calls'] for r in requests]!=[COUNT]*BATCHES+[0]:raise RuntimeError('Unexpected model retries or tool plan')
    for batch in range(BATCHES):
        subset=[e for i in range(batch*COUNT,(batch+1)*COUNT) for e in by_id[i]]
        starts=[e['timestamp_ns'] for e in subset if e['event']=='start'];ends=[e['timestamp_ns'] for e in subset if e['event']=='end']
        active=maximum=0
        for stamp,delta in sorted((e['timestamp_ns'],1 if e['event']=='start' else -1) for e in subset):
            active+=delta;maximum=max(maximum,active)
        if active!=0:raise RuntimeError('Unfinished tool workload')
        if batch>=WARMUPS:rows.append({'framework':framework,'row':8,'metric':'one_mcp_server_four_call_batch','sample':batch-WARMUPS,'duration_ms':(max(ends)-min(starts))/1e6,'max_overlap':maximum,'tool_count':COUNT,'delay_ms':DELAY,'correct':True,'run_id':run_id})
    runs.append({'framework':framework,'run_id':run_id,'actual_tools':COUNT*BATCHES,'model_requests':len(requests),'native_result':str(output.relative_to(ROOT))})
    (ROOT/'results/mcp-samples.partial.json').write_text(json.dumps({'samples':rows,'runs':runs},indent=2))
payload={'schema_version':1,'scope':'Within one real framework conversation and one stdio MCP connection per framework:35 successive batches, first5warmups, next30observed. The local model only fixes the plan; actual framework executes tools. Timing from actual first tool start through last tool end, excluding framework/model startup and MCP discovery. Not a real-model quality/cost test or an overall parallelism score.','samples_per_case':30,'batches':BATCHES,'warmups':WARMUPS,'delay_ms':DELAY,'runs':runs,'samples':rows}
(ROOT/'results/mcp-samples.json').write_text(json.dumps(payload,indent=2))
print(json.dumps({'status':'complete','samples':len(rows),'actual_tool_calls':COUNT*BATCHES*2}),flush=True)
