import json,os,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'sources/hermes'));os.environ['HERMES_HOME']=str(ROOT/'runtime/extended-integration/hermes-ssh');pathlib.Path(os.environ['HERMES_HOME']).mkdir(exist_ok=True,parents=True)
from tools.environments.ssh import SSHEnvironment
fixture=ROOT/'runtime/extended-integration/ssh';ends=json.loads((fixture/'endpoints.json').read_text());envs=[];records=[]
try:
 for e in ends:envs.append(SSHEnvironment(host='127.0.0.1',user='root',port=e['port'],key_path=str(fixture/'client'),cwd=e['directory'],sync_files=False,persistent=False))
 for i in range(10):
  n=i%2;command=f"printf '%s' 'token-{i}' > case-{i}.txt && printf '%s ' \"$(cat identity.txt)\" && cat case-{i}.txt";r=envs[n].execute(command);records.append({'row':2,'case':i,'endpoint':n+1,'command':command,'result':r,'passed':r['returncode']==0 and r['output'].strip()==f'endpoint-{n+1} token-{i}'})
 for i in range(10):
  out=[]
  for n in range(2):
   r=envs[n].execute('cat resource.json');out.append({'code':r['returncode'],**json.loads(r['output'])})
  records.append({'row':18,'case':i,'results':out,'passed':all(v['endpoint']==n+1 and v['code']==0 for n,v in enumerate(out)) and sum(v['value'] for v in out)==51})
finally:
 for e in envs:e.cleanup()
p=ROOT/'raw/extended-integration/hermes-ssh.json';p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps({'framework':'hermes','records':records,'entrypoints':['tools/environments/ssh.py:SSHEnvironment.execute']},indent=2));print(json.dumps({'passed':sum(x['passed'] for x in records),'total':len(records)}))
