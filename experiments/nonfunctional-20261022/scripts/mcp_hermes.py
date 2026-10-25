import asyncio,json,os,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];profile=R/'runtime/mcp-hermes';profile.mkdir(parents=True,exist_ok=True);os.environ['HERMES_HOME']=str(profile);sys.path.insert(0,'/root/output/openclaw-hermes-benchmark-20261022/sources/hermes')
for key in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','DEEPSEEK_API_KEY','AWS_SECRET_ACCESS_KEY','GITHUB_TOKEN','HF_TOKEN','DATABASE_URL']:os.environ[key]='bench-only-canary-'+key
from tools.mcp_tool import MCPServerTask
records=[]
async def main():
    for i in range(6):
        server=MCPServerTask('nonfunctional-bench');start=time.monotonic();await server.start({'command':'/usr/bin/python3','args':[str(R/'scripts/mcp_fixture.py')],'trust':'full'});catalog=await server.session.list_tools();result=await server.session.call_tool('inspect_canaries',arguments={});ready=time.monotonic();content=json.loads(result.content[0].text);await server.shutdown();end=time.monotonic();rec={'framework':'hermes','sample':i-1,'warmup':i==0,'ready_ms':(ready-start)*1000,'shutdown_ms':(end-ready)*1000,'valid':any(t.name=='inspect_canaries'for t in catalog.tools)and not result.is_error,**content};records.append(rec);(R/'raw/mcp-hermes.json').write_text(json.dumps(records,indent=2));print(json.dumps(rec),flush=True)
asyncio.run(main())
