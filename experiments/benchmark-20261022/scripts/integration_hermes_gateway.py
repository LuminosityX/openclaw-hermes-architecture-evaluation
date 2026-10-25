import asyncio,json,os,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];profile=ROOT/'runtime/extended-integration/hermes-gateway';profile.mkdir(parents=True,exist_ok=True);os.environ['HERMES_HOME']=str(profile);os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime');os.environ['OPENAI_API_KEY']='integration-local-fixture';os.environ['OPENAI_BASE_URL']='http://127.0.0.1:38691/v1'
config={'model':{'default':'bench-scripted','provider':'custom','base_url':'http://127.0.0.1:38691/v1','api_mode':'chat_completions','context_length':128000},'terminal':{'backend':'local','cwd':str(ROOT)},'background_review':{'enabled':False},'memory':{'enabled':False},'platform_toolsets':{'api_server':['terminal','delegation']},'delegation':{'max_iterations':5,'max_concurrent_children':2},'agent':{'max_turns':8}}
(profile/'config.yaml').write_text(json.dumps(config));sys.path.insert(0,str(ROOT/'sources/hermes'));os.chdir(ROOT)
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
async def main():
 adapter=APIServerAdapter(PlatformConfig(enabled=True,extra={'host':'127.0.0.1','port':40322,'key':'integration-only-loopback-6b69f75b55e1a11084ae91ae7984f354','model_name':'bench-scripted','model_routes':{'bench-scripted':{'model':'bench-scripted','provider':'custom','api_key':'integration-local-fixture','base_url':'http://127.0.0.1:38691/v1'}}}))
 ready=await adapter.connect();(ROOT/'raw/extended-integration/hermes-gateway-ready.json').write_text(json.dumps({'ready':ready,'pid':os.getpid(),'port':40322}));print(json.dumps({'ready':ready}),flush=True)
 if ready:
  try:await asyncio.Event().wait()
  finally:await adapter.disconnect()
asyncio.run(main())
