"""Sequential native-backend latency pilot with validated resource/image/reuse setup."""
import json
import sys
from run_initial import ROOT,NODE,TSX,PYTHON,ENV,run

aggregate_only='--aggregate-only' in sys.argv
ENV['BENCH_SAMPLES']='30'
ENV['BENCH_WARMUPS']='5'
rows=[]
native=[]
for mode in ['cold','warm']:
    if aggregate_only:
        data=json.loads((ROOT/f'raw/openclaw-sandbox-{mode}.json').read_text())
    else:
        data=run([NODE,'--import',TSX,ROOT/'scripts/openclaw_sandbox_probe.mjs',mode],f'sandbox-openclaw-{mode}',ROOT/'sources/openclaw')
        (ROOT/f'raw/openclaw-sandbox-{mode}.json').write_text(json.dumps(data,indent=2))
    if not data['aggregate']['valid']:raise RuntimeError(f'OpenClaw {mode} failed setup/correctness validation')
    measured=[r for r in data['samples'] if not r['warmup']]
    if len(measured)!=30:raise RuntimeError('Missing OpenClaw samples')
    for record in measured:
        rows.append({'framework':'openclaw','row':6,'metric':'cold_create_and_command' if mode=='cold' else 'warm_reattach_and_command','sample':record['sample'],'duration_ms':record['ready_ms'],'correct':record['correct']})
    native.append({'framework':'openclaw','mode':mode,'verification':data['verification']})
if not aggregate_only:
    run([PYTHON,ROOT/'scripts/hermes_docker_probe.py','--samples','30','--warmups','5'],'sandbox-hermes')
data=json.loads((ROOT/'raw/hermes-docker.json').read_text())
if data['errors'] or data.get('cleanup_errors') or len(data['samples'])!=60 or not all(r['correct'] for r in data['samples']):raise RuntimeError('Hermes missing/incorrect sandbox samples or cleanup failure')
checks=[x['HostConfig'].get('NanoCpus')==1000000000 and x['HostConfig'].get('Memory')==536870912 and x['HostConfig'].get('PidsLimit')==128 and x['HostConfig'].get('NetworkMode')=='none' for x in data['inspections']]
if not checks or not all(checks):raise RuntimeError('Hermes resource configuration verification failed')
rows.extend(data['samples']);native.append({'framework':'hermes','limit_verification':checks,'inspections':data['inspections']})
payload={'schema_version':1,'scope':'Source-mode native backend readiness pilot, image preloaded. All backends include their own initialization. Not full Agent/Gateway or released artifact benchmark.','samples_per_case':30,'warmups_per_case':5,'order':['openclaw-cold','openclaw-warm','hermes-cold-and-warm'],'native_verification':native,'samples':rows}
(ROOT/'results/sandbox-samples.json').write_text(json.dumps(payload,indent=2))
print(json.dumps({'status':'complete','samples':len(rows),'all_correct':all(r['correct'] for r in rows)}),flush=True)
