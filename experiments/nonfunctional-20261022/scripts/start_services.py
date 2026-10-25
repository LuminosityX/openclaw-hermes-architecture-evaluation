import json,os,subprocess,time,pathlib
R=pathlib.Path(__file__).resolve().parents[1];OLD=pathlib.Path('/root/output/openclaw-hermes-benchmark-20261022')
for d in ['raw','results','logs','runtime','workspaces']:(R/d).mkdir(parents=True,exist_ok=True)
env=dict(os.environ);node=OLD/'envs/openclaw-toolchain/node_modules/node/bin/node';env['PATH']=str(node.parent)+os.pathsep+env.get('PATH','')
commands={'proxy':(['/usr/bin/python3',str(R/'scripts/model_proxy.py')],R),'hermes':([str(OLD/'envs/hermes/bin/python'),str(R/'scripts/hermes_gateway.py')],R),'openclaw':([str(node),'--import',str(OLD/'envs/openclaw-toolchain/node_modules/tsx/dist/loader.mjs'),str(R/'scripts/openclaw_gateway.mjs')],OLD/'sources/openclaw')}
pids={}
for name,(cmd,cwd) in commands.items():
    out=(R/f'logs/{name}.log').open('ab');p=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True);pids[name]=p.pid
(R/'runtime/service-pids.json').write_text(json.dumps(pids));print(json.dumps({'launched':pids}),flush=True)
