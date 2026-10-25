import asyncio,json,os,pathlib,sys
R=pathlib.Path(__file__).resolve().parents[1];S=pathlib.Path('/root/output/openclaw-hermes-benchmark-20261022/sources/hermes');profile=R/'runtime/hermes';profile.mkdir(parents=True,exist_ok=True);work=R/'workspaces/hermes';work.mkdir(parents=True,exist_ok=True)
os.environ['HERMES_HOME']=str(profile);os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime');os.environ['OPENAI_API_KEY']='local-benchmark-proxy';os.environ['OPENAI_BASE_URL']='http://127.0.0.1:40490/hermes/v1'
config={'model':{'default':'deepseek-flash','provider':'custom','base_url':'http://127.0.0.1:40490/hermes/v1','api_mode':'chat_completions','context_length':128000},'terminal':{'backend':'local','cwd':str(work)},'approvals':{'unattended_mode':'approve'},'background_review':{'enabled':False},'memory':{'enabled':False},'platform_toolsets':{'api_server':['terminal']},'agent':{'max_turns':8},'reasoning':{'enabled':False},'max_tokens':512}
(profile/'config.yaml').write_text(json.dumps(config));sys.path.insert(0,str(S));os.chdir(work)
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
async def main():
    adapter=APIServerAdapter(PlatformConfig(enabled=True,extra={'host':'127.0.0.1','port':40492,'key':'local-nonfunctional-benchmark','model_name':'deepseek-flash','model_routes':{'deepseek-flash':{'model':'deepseek-flash','provider':'custom','api_key':'local-benchmark-proxy','base_url':'http://127.0.0.1:40490/hermes/v1'}}}))
    ready=await adapter.connect();(R/'runtime/hermes-ready.json').write_text(json.dumps({'ready':ready,'pid':os.getpid()}));print(json.dumps({'ready':ready}),flush=True)
    if ready:
        try:await asyncio.Event().wait()
        finally:await adapter.disconnect()
asyncio.run(main())
