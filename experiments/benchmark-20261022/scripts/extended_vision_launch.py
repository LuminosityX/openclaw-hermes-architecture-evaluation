import os,subprocess,sys
from pathlib import Path
from configure_deepseek import configured_key
ROOT=Path(__file__).resolve().parents[1];key=configured_key()
if not key:raise SystemExit('Missing credential')
env=dict(os.environ);env['DEEPSEEK_API_KEY']=key
state=ROOT/'runtime/extended-vision-openclaw';state.mkdir(parents=True,exist_ok=True);env['OPENCLAW_STATE_DIR']=str(state)
node=ROOT/'envs/openclaw-toolchain/node_modules/node/bin/node';env['PATH']=str(node.parent)+os.pathsep+env.get('PATH','')
if sys.argv[1]=='openclaw':cmd=[str(node),'--import',str(ROOT/'envs/openclaw-toolchain/node_modules/tsx/dist/loader.mjs'),str(ROOT/'scripts/extended_vision_openclaw.mjs')];cwd=ROOT/'sources/openclaw'
else:cmd=[str(ROOT/'envs/hermes/bin/python'),str(ROOT/'scripts/extended_vision_hermes.py')];cwd=ROOT
raise SystemExit(subprocess.run(cmd,cwd=cwd,env=env).returncode)
