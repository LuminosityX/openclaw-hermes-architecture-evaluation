"""Native public-HTTP/WebSocket auth probes with ephemeral synthetic identities."""
import argparse
import hashlib
import http.client
import json
import resource
import shutil
import subprocess
import sys

import mechanism_cases
import pilot

SCENARIOS={f'SEC-11-S{i:02}':name for i,name in enumerate([
    'invalid-credential','expired-reconnect-proof','origin','revoked-token','reader-administrative-action'],1)}


def configure(root):
    config=mechanism_cases.configure(root,'PERF-05-S01')
    config['gateway']['controlUi'].update(allowedOrigins=['http://127.0.0.1:18789'])
    pilot.save(root/'config.json',config)
    return config


def http_probe(token,credential):
    connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=15)
    headers={'Content-Type':'application/json'}
    if credential:headers['Authorization']='Bearer '+credential
    try:
        connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',stream=False,messages=[dict(role='user',content=token)])),headers)
        response=connection.getresponse();data=response.read(1024**2)
        return dict(status=response.status,response_sha256=hashlib.sha256(data).hexdigest(),response_bytes=len(data))
    finally:connection.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=['SEC-11'],required=True)
    parser.add_argument('--campaign-unit',type=int,choices=range(1,4))
    args=parser.parse_args();unit=args.campaign_unit or 1
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    for name in ['tmp','home','cache','run']:(pilot.BASE/name).mkdir(exist_ok=True)
    report=dict(kind='native-campaign-family-unit' if args.campaign_unit else 'native-adapter-validation',product='openclaw',studies=[],
        case_id=args.case,full_campaign_coverage=bool(args.campaign_unit),observations=[],paid_model_calls=0)
    try:
        report['storage_guard_check']=pilot.storage_guard_check()
        proof=subprocess.run([pilot.NODE,'/driver/gateway_auth_probe.mjs','--selfcheck'],capture_output=True,text=True,timeout=10,check=True)
        report['signature_fixture_selfcheck']=json.loads(proof.stdout)
        report['receipt_fixture_selfcheck']=mechanism_cases.selfcheck()
        for sid in SCENARIOS:
            root=pilot.BASE/sid.lower();fixture=None;gateway=None
            token='PILOT_AUTH_'+sid.replace('-','_')+'_U'+str(unit)
            observation=dict(scenario_id=sid,unit=unit,fixture_validated=False,native_invoked=False)
            try:
                fixture=mechanism_cases.MechanismFixture();fixture.register(token)
                gateway=pilot.Gateway(root,configurer=configure);gateway.ready()
                positive=gateway.request(token)
                if not positive['accepted'] or fixture.receipts.get(token)!=1:raise RuntimeError('Native receipt positive control failed')
                observation.update(fixture_validated=True,native_invoked=True)
                assertions=[];http=[]
                if sid=='SEC-11-S01':
                    begin=len(fixture.events)
                    for credential in [None,'SYNTHETIC_INVALID_GATEWAY_SECRET']:
                        denied=token+'_DENIED_'+str(len(http));fixture.register(denied)
                        http.append(http_probe(denied,credential))
                    assertions.extend([dict(name='http-missing-and-invalid-credentials-rejected',verdict='pass' if all(r['status']==401 for r in http) else 'fail',evidence=['native-http-responses']),
                        dict(name='unauthorized-http-no-provider-or-effect',verdict='pass' if not fixture.events[begin:] else 'fail',evidence=['independent-events'])])
                spec=root/'wire-spec.json';pilot.save(spec,dict(scenario=sid,shared_token=pilot.TOKEN,config_path=str(root/'config.json')))
                execution=subprocess.run([pilot.NODE,'/driver/gateway_auth_probe.mjs',str(spec)],capture_output=True,text=True,timeout=100)
                if not execution.stdout.strip():raise RuntimeError('Wire probe exited '+str(execution.returncode)+': '+execution.stderr[-1800:])
                wire=json.loads(execution.stdout)
                observation['wire']=wire
                if wire.get('scenario_id')!=sid:raise RuntimeError('Wire probe scenario mismatch')
                if wire.get('harness_error'):raise RuntimeError(wire['harness_error'])
                if execution.returncode or not wire['fixture_validated'] or not wire['native_invoked']:raise RuntimeError('Wire probe did not validate its native positive controls')
                assertions.extend(wire['assertions'])
                observation.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
                    wire=wire,http=http,events=fixture.events,resources=gateway.sampler.summary(),
                    config_sha256=hashlib.sha256((root/'config.json').read_bytes()).hexdigest(),
                    credential_policy='Fresh synthetic shared secret and Ed25519 devices inside the isolated namespace. No provider API key or external identity service.')
            except Exception as error:
                observation.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3000])
            finally:
                if gateway:gateway.stop()
                if fixture:fixture.close()
                shutil.rmtree(root,ignore_errors=True)
            report['observations'].append(observation)
            print(json.dumps(dict(kind='adapter-validation-checkpoint',product='openclaw',observation=observation)),flush=True)
        report['validation_complete']=len(report['observations'])==len(SCENARIOS)
        report['fixture_and_invocation_valid']=all(r['state']!='harness-error' and r['fixture_validated'] and r['native_invoked'] for r in report['observations'])
        if not report['validation_complete'] or not report['fixture_and_invocation_valid']:report['harness_error']='Gateway auth fixture/invocation validation incomplete'
    except Exception as error:report['harness_error']=type(error).__name__+': '+str(error)[:3000]
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if report.get('harness_error'):sys.exit(1)


if __name__=='__main__':main()
