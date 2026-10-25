import importlib.util,json,os,sys,types,hashlib
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
SOURCE=R/'scripts/vendor_mechanisms.py'
s=SOURCE.read_text().replace('from run_pairs import save','from runtime import save').replace("self.socket_dir=R/'evidence'/f'socket-{family}-{kind}'","self.socket_dir=Path('/root/output/oc-hermes-execution-20261024-v6/evidence/sockets')/__import__('hashlib').sha256(str(run).encode()).hexdigest()[:10]")
s=s.replace('self.socket_dir.mkdir(exist_ok=True)','self.socket_dir.mkdir(parents=True,exist_ok=True)')
M=types.ModuleType('native_mechanisms');M.__file__=str(SOURCE);exec(compile(s,str(SOURCE),'exec'),M.__dict__)
def box(state,work,relay_dir=None,family=None,command=None,evaluator=None):return sandbox(state,work,family,command,relay_dir)
M.C=types.SimpleNamespace(configuration=configuration,sandbox=box,product_command=command)
def main():
 os.chdir(OLD);results=[]
 # Six truly independent connections/profiles for MCP; three independent repeats for failure contracts.
 for rep in range(1,7):
  root=R/'native-units'/f'u{rep}';(root/'evidence').mkdir(parents=True,exist_ok=True);M.R=root
  kinds=['mcp']+(['timeout','deny','plugin-host','retry-429-r1','retry-503-r1'] if rep<=3 else [])
  for kind in kinds:
   for family in (['openclaw','hermes'] if rep%2 else ['hermes','openclaw']):
    path=root/'runs-mechanisms'/kind/family/'result.json'
    if path.exists():v=json.loads(path.read_text())
    else:v=M.run_one(family,kind)
    v={**v,'independent_unit':rep};results.append(v);save(R/'results/native-suite.json',results)
  if rep<=3:
   p=root/'runs-mechanisms/plugin-in-process/hermes/result.json'
   v=json.loads(p.read_text()) if p.exists() else M.run_one('hermes','plugin-in-process');results.append({**v,'independent_unit':rep,'negative_control':True});save(R/'results/native-suite.json',results)
 print('NATIVE_SUITE_DONE',len(results),flush=True)
if __name__=='__main__':main()
