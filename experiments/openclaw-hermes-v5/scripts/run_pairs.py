import argparse, csv, hashlib, importlib.util, json, os, shutil, signal, subprocess, sys, threading, time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
OLD=Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval/work')
sys.path.insert(0,str(OLD))
import pilot_coordinator as C
from audit_relay import Relay,utc

def save(path,data):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)

def evaluate(run,task):
    cmd=C.sandbox(run/'state',run/'workspace',evaluator=R/'private'/task)
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    try:result=json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:result={'passed':False,'evaluator_error':True}
    result.update(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)
    save(run/'acceptance.json',result);return result

def make_state(run,family):
    (run/'state').mkdir();C.configuration(family,run/'state')

def verify_inputs():
    m=json.loads((R/'evidence/input-manifest.json').read_text())
    assert all(hashlib.sha256((R/p).read_bytes()).hexdigest()==h for p,h in m.items()),'Frozen fixture changed'

def run_case(task,family,budget):
    run=R/'runs'/task/family
    if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
    if run.exists():raise RuntimeError('Partial attempt preserved; inspect before restarting: '+str(run))
    run.mkdir(parents=True);run.chmod(0o700)
    shutil.copytree(R/'fixtures'/task,run/'workspace')
    make_state(run,family)
    # Exact same public inputs per pair; only isolated product state differs.
    save(run/'public-manifest.json',{str(p.relative_to(run/'workspace')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/'workspace').rglob('*') if p.is_file()})
    relay=Relay(run,family,budget,inference_authorized=True)
    command=C.product_command(family)
    if family=='openclaw':command[command.index('--timeout')+1]='600'
    command=C.sandbox(run/'state',run/'workspace',relay.socket_dir,family,command)
    save(run/'launch.json',{'command':command,'started':utc(),'model':'deepseek-flash','reasoning':'high','human_intervention':False})
    env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ','HOME','TERM']}
    rec={'task':task,'family':family,'started':utc(),'model':'deepseek-flash','reasoning':'high','attempt':1,'failure':None}
    print('START',task,family,flush=True);start=time.monotonic()
    proc=None
    try:
        with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:
            proc=subprocess.Popen(['/usr/bin/time','-v','-o',str(run/'resources.txt'),*command],stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True,env=env)
            save(R/'evidence/active.json',{'task':task,'family':family,'pid':proc.pid,'started':utc()})
            last=0
            while proc.poll() is None:
                elapsed=time.monotonic()-start
                if elapsed-last>=20:
                    print('ACTIVE',task,family,round(elapsed),'sec',relay.calls,'calls',flush=True);last=elapsed
                    save(R/'evidence/live-budget.json',{k:v for k,v in budget.items() if k!='lock'})
                if elapsed>600 or relay.violations or any(x.get('transport_failure') for x in relay.responses):
                    rec['failure']='timeout' if elapsed>600 else 'relay_policy_or_transport'
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    break
                time.sleep(1)
            rec['elapsed_seconds']=round(time.monotonic()-start,3);rec['exit_code']=proc.returncode
        deadline=time.monotonic()+8
        while len(relay.responses)<relay.calls and time.monotonic()<deadline:time.sleep(.2)
    finally:
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        relay.close()
        save(R/'evidence/active.json',{'active':False,'updated':utc()})
    rec.update(ended=utc(),calls=relay.calls,responses=relay.responses,violations=relay.violations,cost_estimate_CNY=sum(x.get('estimated_cost_CNY') or 0 for x in relay.responses),human_interventions=0)
    # Freeze produced artifacts before any hidden acceptance execution.
    save(run/'artifact-manifest.json',{str(p.relative_to(run/'workspace')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/'workspace').rglob('*') if p.is_file() and not p.is_symlink()})
    acc=evaluate(run,task);rec['passed']=acc.get('passed',False) and not rec['failure'] and rec['exit_code']==0
    rec['checks_passed']=sum(x.get('passed',False) for x in acc.get('checks',[]));rec['checks_total']=len(acc.get('checks',[]))
    save(run/'result.json',rec);save(R/'evidence/live-budget.json',{k:v for k,v in budget.items() if k!='lock'})
    print('DONE',task,family,'PASS' if rec['passed'] else 'FAIL',rec['elapsed_seconds'],'sec',rec['calls'],'calls','CNY',rec['cost_estimate_CNY'],flush=True)
    return rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preflight',action='store_true');ap.add_argument('--limit',type=int,default=12);args=ap.parse_args()
    verify_inputs()
    # The existing relay deliberately uses a short relative Unix socket path.
    os.chdir(OLD)
    if args.preflight:
        p=R/'evidence/preflight';p.mkdir(exist_ok=True)
        # Validate the hidden coding checker against an independent reference implementation.
        for family in ['openclaw','hermes']:
            q=p/family;q.mkdir(exist_ok=True);(q/'workspace').mkdir(exist_ok=True)
            (q/'workspace/PROMPT.md').write_text('No model invocation.')
            if not (q/'state').exists():make_state(q,family)
            cmd=['node','/runtime/openclaw/node_modules/openclaw/openclaw.mjs','--version'] if family=='openclaw' else ['bash','-c','cd /runtime/hermes-source; task_activation="$(/runtime/hermes-tools/python-3.14.9+20261021-linux-x64/bin/python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes --version']
            r=subprocess.run(C.sandbox(q/'state',q/'workspace',family=family,command=cmd),capture_output=True,text=True,timeout=60)
            save(q/'version.json',dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr));print(family,r.returncode,r.stdout[-300:])
            assert r.returncode==0
        return
    historical=json.loads(Path('/root/Downloads/1023magnitude/agent_eval_handoff/state/status.json').read_text())['cost_meter']
    prior=historical['conservative_estimate_plus_unknown_reserve_CNY']
    b={'lock':threading.Lock(),'spent':prior,'reserved':0.,'limit':min(50.,prior+15.)}
    # Resume only finished records, retaining unresolved reservations in live budget.
    if (R/'evidence/live-budget.json').exists():b.update(json.loads((R/'evidence/live-budget.json').read_text()))
    save(R/'evidence/authorization.json',dict(at=utc(),instruction='用户明确要求只测试OpenClaw和Hermes，弄清孰强孰弱',supersedes='previous methodology-review hold for these two products only',total_cap_CNY=50,new_incremental_exposure_cap_CNY=15,previous_conservative_exposure_CNY=prior,no_other_products=True,no_paid_cloud=True,no_mobile_login=True))
    results=[];order=[]
    for v in range(1,4):
        for typ in ['code','data']:
            order += [(f'{typ}-v{v}',f) for f in (['openclaw','hermes'] if (v+(typ=='data'))%2 else ['hermes','openclaw'])]
    save(R/'evidence/order.json',order)
    for task,family in order[:args.limit]:
        r=run_case(task,family,b);results.append(r)
        save(R/'results/pairs.json',results)
        if r.get('failure')=='relay_policy_or_transport':raise RuntimeError('Relay uncertainty: retain attempt and resolve before next paid run')
    print('BATCH_COMPLETE',len(results),'results',flush=True)

if __name__=='__main__':main()
