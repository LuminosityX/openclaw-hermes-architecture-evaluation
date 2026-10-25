import argparse,json,pathlib,time,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('framework');p.add_argument('--delegation',action='store_true');p.add_argument('--count',type=int,default=10);p.add_argument('--run-tag',default=str(time.time_ns()));args=p.parse_args();framework=args.framework;port=40321 if framework=='openclaw' else 40322;records=[];kind='delegation' if args.delegation else 'gateway';output=ROOT/f'raw/extended-integration/{framework}-{kind}.json'
for i in range(args.count):
 case=f'{framework}-{args.run_tag}-{i}';run_id=f'integration-gateway-formal-{case}';prompt=f'INTEGRATION_DELEGATE_CASE={case} Spawn one child agent to execute its requested tool and report its result.' if args.delegation else f'BENCH_RUN_ID={run_id} BENCH_TOOL_COUNT=1 BENCH_DELAY_MS=0'
 body={'model':'openclaw:main' if framework=='openclaw' else 'bench-scripted','stream':False,'user':f'integration-formal-{kind}-{case}','messages':[{'role':'user','content':prompt}]};request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer integration-only-loopback-6b69f75b55e1a11084ae91ae7984f354'});started=time.perf_counter();record={'case':i,'run_id':run_id,'run_tag':args.run_tag,'request':body,'passed':False}
 try:
  with urllib.request.urlopen(request,timeout=180) as response:record['http_status']=response.status;record['response']=json.loads(response.read())
  content=record['response']['choices'][0]['message']['content'];final=json.loads(content);record['parsed_final']=final
  target=f'integration-child-{case}' if args.delegation else run_id
  for _ in range(120 if args.delegation else 3):
   events=[json.loads(v) for v in (ROOT/'raw/tool-events.jsonl').read_text().splitlines()];actual=[v for v in events if v['run_id']==target]
   if len(actual)>=2:break
   time.sleep(.5)
  record['tool_events']=actual
  if args.delegation:
   record['passed']=final.get('case')==case and final.get('tool_results',0)>=1 and len(actual)==2 and {x['event'] for x in actual}=={'start','end'}
  else:record['passed']=final.get('run_id')==run_id and final.get('observed_tool_results')==1 and final.get('expected_tool_results')==1 and len(actual)==2
 except Exception as e:
  record['error']=str(e)
  if isinstance(e,urllib.error.HTTPError):record['error_body']=e.read().decode()
 record['elapsed_ms']=(time.perf_counter()-started)*1000;records.append(record);output.write_text(json.dumps({'framework':framework,'records':records,'entrypoints':['src/gateway/openai-http.ts:handleOpenAiHttpRequest' if framework=='openclaw' else 'gateway/platforms/api_server.py:APIServerAdapter','src/agents/tools/sessions-spawn-tool.ts:createSessionsSpawnTool' if framework=='openclaw' and args.delegation else 'tools/delegate_tool.py:delegate_task' if args.delegation else 'native agent terminal tool']},indent=2));print(json.dumps({'framework':framework,'kind':kind,'case':i,'passed':record['passed'],'error':record.get('error'),'elapsed_ms':record['elapsed_ms']}),flush=True)
