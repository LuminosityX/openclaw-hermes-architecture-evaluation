"""Validate candidate native adapters. This is excluded from full-campaign results."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys

import pilot
import protocol_cases


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=['REL-14','REL-15'],required=True)
    args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    for name in ['tmp','home','cache','run']: (pilot.BASE/name).mkdir(exist_ok=True)
    report=dict(kind='native-adapter-validation',product='openclaw',studies=[],case_id=args.case,
                full_campaign_coverage=False,observations=[],paid_model_calls=0)
    fixture=None
    try:
        report['storage_guard_check']=pilot.storage_guard_check()
        report['fixture_selfcheck']=protocol_cases.selfcheck()
        fixture=protocol_cases.ProtocolFixture()
        for sid in protocol_cases.SCENARIOS:
            if not sid.startswith(args.case+'-'): continue
            root=pilot.BASE/sid.lower()
            token='PILOT_PROTOCOL_'+sid.replace('-','_')+'_π'
            fixture.activate(sid,token)
            begin=len(fixture.events)
            gateway=None
            observation=dict(scenario_id=sid,unit=1,fixture_validated=True,native_invoked=False)
            try:
                gateway=pilot.Gateway(root,configurer=lambda root:protocol_cases.configure(root,sid))
                gateway.ready()
                request=gateway.request(token)
                events=fixture.events[begin:]
                assertions=protocol_cases.acceptance(sid,request,events)
                invoked=any(e['kind']=='scripted-provider-request' for e in events)
                native=pilot.native_evidence(root,[token])
                observation.update(native_invoked=invoked,state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',
                    request={k:v for k,v in request.items() if k!='response_excerpt'},
                    response_excerpt_sha256=hashlib.sha256(request.get('response_excerpt','').encode()).hexdigest(),
                    assertions=assertions,events=events,
                    native_records=dict(tokens=native['tokens'],native_log_sha256=native['native_log_sha256'],native_log_bytes=native['native_log_bytes']),
                    resources=gateway.sampler.summary(),config_sha256=hashlib.sha256((root/'config.json').read_bytes()).hexdigest(),
                    usage_note='The missing-usage transcript deliberately omits provider usage; absent provider counters must not be normalized to zero.')
                if not invoked: observation.update(state='harness-error',reason='Native provider entry point was not reached')
            except Exception as error:
                observation.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:1500])
            finally:
                if gateway: gateway.stop()
                shutil.rmtree(root,ignore_errors=True)
            report['observations'].append(observation)
            print(json.dumps(dict(kind='adapter-validation-checkpoint',product='openclaw',observation=observation)),flush=True)
        report['validation_complete']=len(report['observations'])==sum(s.startswith(args.case+'-') for s in protocol_cases.SCENARIOS)
        report['fixture_and_invocation_valid']=all(r['state']!='harness-error' for r in report['observations'])
        if not report['validation_complete'] or not report['fixture_and_invocation_valid']:
            report['harness_error']='Candidate adapters include incomplete/native-entry failures; no full coverage awarded'
    except Exception as error:
        report['harness_error']=type(error).__name__+': '+str(error)[:1500]
    finally:
        if fixture: fixture.close()
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if report.get('harness_error'): sys.exit(1)


if __name__=='__main__': main()
