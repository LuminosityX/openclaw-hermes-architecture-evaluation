#!/usr/bin/env python3
"""Execute an independently accepted native PERF-09 task on a disposable host.

Full execution requires current native validation under the active plan. --validate-adapter permits
development calibration, explicitly excluded from the frozen campaign results.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from adapter_readiness import require_execution_ready, load_proofs, proof_directory
from campaign import DEFAULT_PLAN, load_plan, validate_result
from model_relay import Relay
from provider_plugin import verify as verify_plugin
from suite import ROOT, require
from target import verify_installation
from task_acceptance import function_results
from task_workloads import judge, workload
from task_transcripts import provider_for


def native_completion_assertion(native,task):
    completed=native.get('native_http_status')==200 and not native.get('task_transport_error') and type(native.get('completion_ms')) in {int,float} and 0<=native['completion_ms']<=task['resource_limits']['timeout_seconds']*1000
    return dict(name='native-task-finished-within-deadline',verdict='pass' if completed else 'fail',evidence=['native/summary.json:native_http_status,completion_ms,task_transport_error'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-modules',type=Path,required=True)
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--package-lock',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenario',choices=[f'PERF-09-S{i:02}' for i in range(1,6)],required=True)
    parser.add_argument('--unit',type=int,choices=range(1,7),required=True)
    parser.add_argument('--thinking',choices=['enabled','disabled'],default='enabled')
    parser.add_argument('--validate-adapter',action='store_true')
    parser.add_argument('--scripted-provider',action='store_true',help='Golden local transcript: zero real model calls, development calibration only')
    args=parser.parse_args()
    if args.scripted_provider and not args.validate_adapter: parser.error('Golden fixture transcripts are never full campaign task-quality evidence')
    plan=load_plan()
    if not args.validate_adapter:
        require_execution_ready(plan,'PERF-09',load_proofs(proof_directory(plan)))
    require(os.geteuid()==0,'Hosted task controller requires root for owned cgroups/namespaces')
    installation=verify_installation(plan['target'],args.runtime_modules,args.package_lock)
    plugin=verify_plugin(args.runtime_modules,args.package_lock)
    if args.scripted_provider:
        os.environ.pop('DEEPSEEK_API_KEY',None)
        key='synthetic-golden-fixture'
    else: key=os.environ.pop('DEEPSEEK_API_KEY','')
    require(bool(key),'DEEPSEEK_API_KEY is not configured')
    task=workload(args.scenario,args.unit)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'installation.json').write_text(json.dumps(installation,indent=2)+'\n')
    (args.output/'provider-plugin.json').write_text(json.dumps(plugin,indent=2)+'\n')
    with tempfile.TemporaryDirectory(prefix='openclaw-task-controller-') as directory:
        root=Path(directory)
        public=dict(task['public'])
        if 'service_fixture' in task: public['service_fixture']=task['service_fixture']
        input_path=root/'input.json'
        input_path.write_text(json.dumps(dict(task=public,thinking=args.thinking,full_campaign_coverage=not args.validate_adapter),ensure_ascii=False))
        relay=Relay(root/'provider.sock',key,thinking=args.thinking,
                    max_output_tokens=task['maximum_output_tokens_per_request'],maximum_requests=task['maximum_model_requests'],
                    open_request=provider_for(task) if args.scripted_provider else None,scripted_fixture=args.scripted_provider)
        key=''
        thread=threading.Thread(target=relay.serve_forever,daemon=True);thread.start()
        try:
            execution=subprocess.run([sys.executable,str(ROOT/'evaluation/tools/run_local.py'),
                '--runtime-modules',str(args.runtime_modules),'--node',str(args.node),
                '--output',str(args.output/'native'),'--hosted-profile','--memory-mib','3072',
                '--timeout','300','--ssh-backend','--task-input',str(input_path),'--relay-socket',str(relay.path)],
                env=dict(os.environ),timeout=330,check=False)
        finally:
            relay.shutdown();thread.join(timeout=3)
            relay.write_ledger(args.output/'provider-usage.json');relay.server_close()
    native=json.loads((args.output/'native/summary.json').read_text())
    ledger=json.loads((args.output/'provider-usage.json').read_text())
    artifacts=native.get('artifacts',{})
    outputs=function_results(task,artifacts.get(task['artifact'])) if task['oracle']['kind']=='python-function' else None
    verdict=judge(task,artifacts,function_results=outputs,service_events=native.get('independent_events'))
    integrity=native.get('input_integrity',{})
    expected_immutable={name for name in task['files'] if name!=task['artifact']}
    intact=set(integrity)==expected_immutable and all(value is True for value in integrity.values())
    verdict['assertions'].append(dict(name='immutable-inputs-unchanged',verdict='pass' if intact else 'fail',evidence=['native/summary.json:input_integrity']))
    verdict['accepted']=verdict['accepted'] and intact
    completion=native_completion_assertion(native,task)
    verdict['assertions'].append(completion)
    verdict['accepted']=verdict['accepted'] and completion['verdict']=='pass'
    require(native.get('full_campaign_coverage') is (not args.validate_adapter),'Native execution purpose disagrees with the host controller')
    fixture_validated=native.get('fixture_selfcheck',{}).get('valid') is True
    harness_failure=execution.returncode!=0 or bool(native.get('harness_error')) or not ledger['forwarded_request_count'] or not fixture_validated
    result=dict(schema_version=1,plan_sha256=plan['plan_sha256'],product='openclaw',target_version=plan['target']['version'],
                target_commit=plan['target']['source_commit'],scenario_id=args.scenario,unit=args.unit,
                state='harness-error' if harness_failure else 'pass' if verdict['accepted'] else 'fail',
                fixture_validated=fixture_validated,native_invoked=ledger['forwarded_request_count']>0,
                run_id=os.environ.get('GITHUB_RUN_ID','hosted-development'),
                evidence=['native/summary.json','provider-usage.json','installation.json','provider-plugin.json'],
                assertions=verdict['assertions'],public_fixture_sha256=task['public_fixture_sha256'],thinking=args.thinking,
                full_campaign_coverage=not args.validate_adapter,
                model_execution='golden-scripted-fixture' if args.scripted_provider else 'real-deepseek-api',
                acceptance_values=outputs,full_campaign_development_calibration=args.validate_adapter)
    if harness_failure: result['reason']='Native task fixture or invocation failed; inspect bounded native/provider evidence'
    validate_result(result,plan,allow_development=args.validate_adapter)
    (args.output/'task-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(scenario=args.scenario,unit=args.unit,state=result['state'],full_campaign_coverage=result['full_campaign_coverage'])))
    if harness_failure: parser.exit(1,'Native task acceptance is not valid campaign evidence\n')
    if args.scripted_provider and not verdict['accepted']: parser.exit(1,'Golden transcript did not produce its independently accepted artifact; investigate the candidate adapter\n')


if __name__=='__main__': main()
