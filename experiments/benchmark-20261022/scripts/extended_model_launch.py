import os,subprocess
from pathlib import Path
from configure_deepseek import configured_key
ROOT=Path(__file__).resolve().parents[1]
key=configured_key()
if not key:raise SystemExit('DeepSeek credential not configured')
env=dict(os.environ);env['DEEPSEEK_API_KEY']=key
state=ROOT/'runtime/extended-model-openclaw-state';state.mkdir(parents=True,exist_ok=True)
env['OPENCLAW_STATE_DIR']=str(state)
env['OPENCLAW_WORKSPACE_DIR']=str(ROOT/'fixtures/agent-workspace')
node=ROOT/'envs/openclaw-toolchain/node_modules/node/bin/node';tsx=ROOT/'envs/openclaw-toolchain/node_modules/tsx/dist/loader.mjs'
env['PATH']=str(node.parent)+os.pathsep+env.get('PATH','')
import sys
framework=sys.argv[1]
command=[str(ROOT/'envs/hermes/bin/python'),str(ROOT/'scripts/extended_model_hermes.py')] if framework=='hermes' else [str(node),'--import',str(tsx),str(ROOT/'scripts/extended_model_openclaw.mjs')]
completed=subprocess.run(command,cwd=ROOT if framework=='hermes' else ROOT/'sources/openclaw',env=env)
raise SystemExit(completed.returncode)
