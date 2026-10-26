"""Native failure/restart and one actual operator approval, separately attributed."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import mechanism_cases as mechanism
from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

SCENARIOS={f'REL-04-S{i:02}':name for i,name in enumerate(['plugin-exit','worker-exit','gateway-restart','operator-confirmation'],1)}


def pending_admission(result,native_log,provider_seen,effect_count):
    """Retry only an independently undispatched startup-admission rejection."""
    return (result.get('status')==500 and not provider_seen and not effect_count
        and 'AgentDatabaseAdmissionError' in native_log
        and 'has not completed startup inspection and preparation' in native_log)


def configure(root,mode):
    config=service.configure(root)
    if mode=='plugin-exit':
        plugin=root/'composition-a/index.js'
        trigger=json.dumps(str(root/'owned-crash-occurred'))
        source=plugin.read_text().replace("  if(args.action==='throw')",f"  if(args.action==='exit'&&!fs.existsSync({trigger})){{fs.writeFileSync({trigger},'once');process.exit(42);}}\n  if(args.action==='throw')")
        plugin.write_text(source)
    if mode=='worker-exit':
        config['mcp']=dict(servers=dict(probe=dict(transport='stdio',command='/usr/bin/python3',args=['/driver/mcp_probe.py'],requestTimeoutMs=5000)))
        config['tools']['allow'].append('probe__eval_probe')
    if mode=='operator-confirmation':
        config['tools']['allow'].append('exec')
        config['tools']['exec']=dict(host='gateway',security='full',ask='always')
        config['gateway']['controlUi'].update(enabled=True,allowedOrigins=['http://127.0.0.1:18789'])
    pilot.save(root/'config.json',config)
    return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;approver=None;assertions=[];metadata={};requests=[]
    token='PILOT_RECOVERY_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,fixture_validated=False,native_invoked=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-process-and-approval-records','independent-events','independent-effect-ledger']))
    def request(item,session=None):
        result=gateway.request(item,session_key=session)
        requests.append({k:v for k,v in result.items() if k!='response_excerpt' or not result['accepted']})
        return result
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);positive=request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native positive control failed')
        row.update(fixture_validated=True,native_invoked=True)
        if mode=='operator-confirmation':
            effect=root/'operator-approved-effect.txt';script=root/'owned-approval-work.py'
            script.write_text('from pathlib import Path\nfrom urllib.request import Request,urlopen\nimport json\n'
                'Path('+repr(str(effect))+').write_text("SYNTHETIC_APPROVED_EFFECT")\n'
                'body=json.dumps(dict(token='+repr(token)+')).encode()\n'
                'with urlopen(Request("http://127.0.0.1:18080/effect",data=body,headers={"Content-Type":"application/json"}),timeout=5) as response: print(response.read().decode())\n')
            fixture.plan(token,'exec',dict(command='python3 '+str(script),yieldMs=10000),'RECEIPT:'+token)
            spec=root/'approval-spec.json';pilot.save(spec,dict(shared_token=pilot.TOKEN,command_marker=str(script),effect_path=str(effect)))
            approver=subprocess.Popen([pilot.NODE,'/driver/approval_probe.mjs',str(spec)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            first=approver.stdout.readline()
            try:ready=json.loads(first).get('ready') is True
            except ValueError:ready=False
            if not ready:raise RuntimeError('Native approval observer did not become ready: '+first[:1000])
            result=request(token)
            stdout,stderr=approver.communicate(timeout=30)
            approval=json.loads(stdout.strip().splitlines()[-1])
            if approver.returncode or approval.get('harness_error'):raise RuntimeError('Native approval boundary not exercised: '+json.dumps(approval)[:1800])
            reached=mechanism.wait_events(fixture,'effect-commit',[token],seconds=8)
            check('manual-approval-required-before-effect',approval['approval']['effect_before_decision'] is False)
            check('native-operator-verdict-recorded',approval['approval']['resolution'].get('ok') is True)
            check('approved-command-effect-actually-commits-once',reached and effect.is_file() and fixture.receipts.get(token)==1)
            metadata.update(native_approval=approval,logical_operator_interventions=1,
                operator_scope='Automated owner acts as the authorized reviewer for one owned synthetic command; no human active-time claim.')
        elif mode=='worker-exit':
            mcp_control=token+'_MCP_CONTROL';fixture.plan(mcp_control,'probe__eval_probe',dict(token=mcp_control,action='effect'),'RECEIPT:'+mcp_control)
            test=request(mcp_control)
            if not test['accepted'] or fixture.receipts.get(mcp_control)!=1:raise RuntimeError('Native MCP worker control failed')
            fixture.plan(token,'probe__eval_probe',dict(token=token,action='crash'),'RECEIPT:'+token)
            result=request(token)
            faults=[e for e in fixture.events if e['kind']=='fault-start' and e.get('token')==token and e.get('action')=='crash']
            if len(faults)!=1:raise RuntimeError('Actual worker exit intervention was not reached')
            time.sleep(.2);pid=faults[0]['pid'];state='missing'
            try:state=Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()[0]
            except OSError:pass
            check('actual-worker-exit-observed',state in {'missing','Z'})
            check('gateway-survives-worker-exit',gateway.process.poll() is None)
            check('failed-worker-task-not-falsely-completed',not result['accepted'] and not fixture.receipts.get(token))
            after=token+'_MCP_RECOVERED';fixture.plan(after,'probe__eval_probe',dict(token=after,action='effect'),'RECEIPT:'+after)
            recovered=request(after)
            check('later-native-worker-use-recovers',recovered['accepted'] and fixture.receipts.get(after)==1)
            metadata.update(failed_worker_pid=pid,worker_post_exit_state=state,logical_operator_interventions=0)
        else:
            if mode=='plugin-exit':
                fixture.plan(token,'eval_probe',dict(token=token,action='exit'),'RECEIPT:'+token)
                result=request(token);time.sleep(.2)
                if not (root/'owned-crash-occurred').exists():raise RuntimeError('Actual plugin exit intervention was not reached')
            else:
                fixture.register(token,gate=True);fixture.release.clear()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pending=pool.submit(request,token)
                    if not mechanism.wait_events(fixture,'effect-start',[token]):raise RuntimeError('Gateway restart did not reach actual in-flight work')
                    os.killpg(gateway.process.pid,signal.SIGKILL);gateway.process.wait(timeout=5)
                    fixture.release.set();result=pending.result(timeout=40)
                mechanism.wait_events(fixture,'effect-commit',[token])
            check('native-owner-exit-observed',gateway.process.poll() is not None)
            check('interrupted-http-task-not-falsely-completed',not result['accepted'])
            time.sleep(1);metadata['bare_owner_exit_code']=gateway.process.poll()
            metadata['automatic_supervisor_configured']=False
            metadata['pre-restart-native_tail']=''.join(gateway.log_tail)[-4000:]
            gateway.stop();start=time.monotonic_ns();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
            after=token+'_RECOVERED';fixture.register(after)
            deadline=time.monotonic()+30;attempts=[]
            while True:
                recovered=request(after,session=token.lower())
                attempts.append(dict(status=recovered.get('status'),accepted=recovered['accepted'],monotonic_ns=time.monotonic_ns()))
                provider_seen=any(e.get('token')==after and 'provider' in e['kind'] for e in fixture.events)
                if not pending_admission(recovered,''.join(gateway.log_tail),provider_seen,fixture.receipts.get(after,0)) or time.monotonic()>=deadline:break
                time.sleep(.5)
            check('native-service-usable-after-explicit-restart',recovered['accepted'] and fixture.receipts.get(after)==1)
            metadata.update(recovery_wall_ms=(time.monotonic_ns()-start)/1e6,logical_operator_interventions=1,
                recovery_admission_attempts=attempts,recovery_admission_deadline_seconds=30,
                recovery_retry_scope='Evaluator retries only HTTP 500 while native logs explicitly report pending database admission and independent provider/effect ledgers show no dispatch. Early rejection remains observed; no ambiguous or executed call is replayed.',
                interrupted_effect_count=fixture.receipts.get(token,0),
                recovery_scope='Bare native Gateway run, no systemd/container supervisor. Explicit process restart is an operator action; subsequent session handling remains native.')
        healthy=token+'_HEALTHY';fixture.register(healthy);health=request(healthy)
        check('independent-neighbor-service-restored',health['accepted'] and fixture.receipts.get(healthy)==1)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,requests=requests,independent_events=fixture.events,independent_receipts=fixture.receipts,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3000],metadata=metadata)
    finally:
        fixture.release.set()
        if approver and approver.poll() is None:approver.kill();approver.communicate(timeout=5)
        if gateway:
            gateway.stop()
            row['native_gateway_tail']=''.join(gateway.log_tail)[-6000:]
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
