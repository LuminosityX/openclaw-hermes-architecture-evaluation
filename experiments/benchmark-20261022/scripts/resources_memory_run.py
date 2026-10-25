import subprocess,json,time,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];node=R/'envs/openclaw-toolchain/node_modules/node/bin/node';tsx=R/'envs/openclaw-toolchain/node_modules/tsx/dist/loader.mjs';py=R/'envs/hermes/bin/python'
for count in ([100]if '--cpu' in sys.argv else[10,50,100]):
 for sample in (range(2000,2010)if '--cpu' in sys.argv else range(5)):
  for fw in ['openclaw','hermes']:
   target=R/f'raw/extended-resources/memory-{fw}-{count}-{sample}.json'
   if target.exists():
    data=json.loads(target.read_text())
    if data.get('functional'):continue
   cmd=[str(node),'--expose-gc','--import',str(tsx),str(R/'scripts/resources_memory_openclaw.mjs'),str(count),str(sample)]if fw=='openclaw'else[str(py),str(R/'scripts/resources_memory_hermes.py'),str(count),str(sample)]
   with (R/f'raw/extended-resources/memory-{fw}-{count}-{sample}.log').open('w')as f:r=subprocess.run(cmd,cwd=R/'sources/openclaw',stdout=f,stderr=subprocess.STDOUT,timeout=180)
   print(json.dumps({'framework':fw,'count':count,'sample':sample,'exit':r.returncode}),flush=True)
   if r.returncode:raise SystemExit(r.returncode)
