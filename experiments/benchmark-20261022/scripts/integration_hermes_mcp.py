import asyncio,json,os,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'sources/hermes'));os.environ['HERMES_HOME']=str(ROOT/'runtime/extended-integration/hermes-mcp');pathlib.Path(os.environ['HERMES_HOME']).mkdir(parents=True,exist_ok=True)
from tools.mcp_tool import MCPServerTask
records=[]
async def main():
 for i in range(5):
  server=MCPServerTask('integration-bench');await server.start({'command':'/usr/bin/python3','args':[str(ROOT/'scripts/mcp_fixture.py')],'trust':'full'})
  try:
   catalog=await server.session.list_tools()
   for j in range(2):
    index=i*2+j;run_id=['ascii','中文表情😀','quote"line\nsecond','x'*10000,'reconnected'][i];result=await server.session.call_tool('bench_delay',arguments={'run_id':run_id,'id':index,'delay_ms':0});parsed=json.loads(result.content[0].text);schema=[t.model_dump(by_alias=True) for t in catalog.tools];records.append({'case':index,'session':i,'catalog':schema,'result':result.model_dump(by_alias=True),'passed':any(t.name=='bench_delay' and 'run_id' in t.input_schema.get('required',[]) for t in catalog.tools) and parsed['run_id']==run_id and parsed['id']==index and not result.is_error})
  finally:await server.shutdown()
asyncio.run(main());(ROOT/'raw/extended-integration/hermes-mcp.json').write_text(json.dumps({'framework':'hermes','records':records,'entrypoints':['tools/mcp_tool.py:MCPServerTask','tools/mcp_tool_server_run.py:MCPServerRunMixin.start']},indent=2));print(json.dumps({'passed':sum(x['passed'] for x in records),'total':len(records)}))
