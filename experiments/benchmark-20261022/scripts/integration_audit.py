import json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1];all_requests=[json.loads(x) for x in (ROOT/'raw/model-requests.jsonl').read_text().splitlines()];log=(ROOT/'logs/integration-openclaw-gateway.log').read_text();audit=[]
for framework in ['openclaw','hermes']:
 p=ROOT/f'raw/extended-integration/{framework}-delegation.json';d=json.loads(p.read_text());assert len(d['records'])==10
 for record in d['records']:
  final=record['parsed_final'];payload=json.loads(final['delegation_results'][0]);case=final['case'];run_id='integration-child-'+case;requests=[r for r in all_requests if r['run_id']==run_id]
  terminal_complete=any(r.get('observed_tool_results')==1 and r.get('returned_calls')==0 for r in requests);native_complete=payload.get('status')=='accepted' and payload.get('childSessionKey','').startswith('agent:main:subagent:') and f"run {payload.get('runId')} ended with stopReason=stop" in log if framework=='openclaw' else payload.get('results',[{}])[0].get('status')=='completed' and json.loads(payload['results'][0]['summary']).get('observed_tool_results')==1
  passed=record['passed'] and terminal_complete and native_complete
  audit.append({'framework':framework,'case':record['case'],'child_run_id':run_id,'native_complete':native_complete,'terminal_complete':terminal_complete,'passed':passed,'native_delegation':payload,'model_requests':requests});assert passed,(framework,case)
for row in [2,9,13,18,21,22]:
 d=json.loads((ROOT/f'results/extended-row-{row:02}.json').read_text());assert d['status']=='measured'
 for f,v in d['frameworks'].items():assert v['passed']==10 and v['total']==10 and len(v['values'])==10
(ROOT/'raw/extended-integration/delegation-audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps({'verified_rows':[2,9,13,18,21,22],'actual_cases':120,'delegation_final_completion_checks':len(audit)}))
