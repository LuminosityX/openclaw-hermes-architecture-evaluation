"""Verify kernel enforcement in containers created by each native backend."""
import json
import subprocess
from pathlib import Path
from run_initial import ROOT, NODE, TSX, PYTHON, ENV, run

docker = [str(ROOT/'envs/docker/docker/docker'),'--host','unix://'+str(ROOT/'runtime/docker/docker.sock')]
records=[]
creators=[]
for framework in ['hermes','openclaw']:
    container_id=None
    try:
        if framework=='hermes':
            output=ROOT/'raw/hermes-quota-container.json'
            run([PYTHON,ROOT/'scripts/hermes_docker_create.py','--run-id','hermes-quota-initial','--output',output],'quota-create-hermes')
            creator=json.loads(output.read_text())
            container_id=creator['container_id']
            if not creator['limits_match']:raise RuntimeError('Hermes container limits mismatch')
        else:
            creator=run([NODE,'--import',TSX,ROOT/'scripts/openclaw_sandbox_probe.mjs','quota'],'quota-create-openclaw',ROOT/'sources/openclaw')
            (ROOT/'raw/openclaw-quota-container.json').write_text(json.dumps(creator,indent=2))
            container_id=creator['samples'][0]['container_id']
            if not creator['aggregate']['valid']:raise RuntimeError('OpenClaw container setup failed')
        creators.append({'framework':framework,'container_id':container_id,'native_creator':creator})
        for trial in range(3):
            completed=subprocess.run(docker+['exec','-i',container_id,'python3','-'],input=(ROOT/'scripts/quota_workload.py').read_text(),text=True,capture_output=True,timeout=60,env=ENV)
            (ROOT/f'logs/quota-{framework}-{trial}.stderr.log').write_text(completed.stderr)
            if completed.returncode:raise RuntimeError(f'{framework} quota workload failed {completed.returncode}: {completed.stderr}')
            result=json.loads(completed.stdout)
            if result.get('status')!='complete':raise RuntimeError(f'Unsupported quota environment: {result}')
            for record in result['results']:
                records.append({'framework':framework,'row':26,'trial':trial,**record})
            (ROOT/'results/quota-samples.partial.json').write_text(json.dumps({'samples':records,'creators':creators},indent=2))
            print(json.dumps({'framework':framework,'trial':trial,'all_correct':result['all_correct']}),flush=True)
    finally:
        if container_id:
            cleaned=subprocess.run(docker+['rm','-f',container_id],text=True,capture_output=True,env=ENV)
            if cleaned.returncode:raise RuntimeError(f'Owned container cleanup failed {container_id}: {cleaned.stderr}')
if len(records)!=18:raise RuntimeError(f'Missing quota observations: {len(records)}')
payload={'schema_version':1,'scope':'Actual kernel pressure in native-created sandbox containers; each of3 resource cases repeated3 times per framework; not a general security score.','samples':records,'creators':creators}
(ROOT/'results/quota-samples.json').write_text(json.dumps(payload,indent=2))
print(json.dumps({'status':'complete','observations':len(records),'all_correct':all(r['correct'] for r in records)}),flush=True)
