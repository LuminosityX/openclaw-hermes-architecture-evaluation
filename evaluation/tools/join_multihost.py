#!/usr/bin/env python3
"""Join actual independent native hosts; never infer placement from service count."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from adapter_readiness import SOURCES,load_proofs,require_execution_ready
from campaign import load_plan
from run_campaign_family import bind_unit
from suite import ROOT,require


def joined(root,unit,plan):
    a=root/('multihost-native-gateway-'+str(unit));b=root/('multihost-native-worker-'+str(unit))
    gateway=json.loads((a/'host-provenance.json').read_text());worker=json.loads((b/'host-provenance.json').read_text())
    native=json.loads((a/'gateway-report.json').read_text());events=json.loads((b/'host-events.json').read_text());local=json.loads((a/'host-events.json').read_text())
    for host,directory in [(gateway,a),(worker,b)]:
        require(not host.get('harness_error'),host.get('harness_error','Actual host fixture failed'))
        require(host['controller_commit']==os.environ['GITHUB_SHA'] and str(host['run_id'])==os.environ['GITHUB_RUN_ID'],'Host source/run provenance mismatch')
        installation=json.loads((directory/'installation.json').read_text());require(installation['target']==plan['target'],'Independent host installed a different core target')
    require(gateway['host_boot_id']!=worker['host_boot_id'],'Actual independent kernel/VM identities required')
    require(not worker.get('native_execution_pids_after_shutdown'),'Owned native worker processes survived execution-host destruction')
    require(worker.get('native_execution_state_removed_after_shutdown') is True,'Owned native worker storage was not removed after host loss')
    require(worker.get('execution_host_destroyed') is True,'Actual owned native worker host was not destroyed')
    require(not any(e['kind']=='observer-harness-error' for e in events+local),'Independent kernel observer failed')
    require(any(e['kind']=='real-native-TLS-partition-restored' and e.get('actual_dropped_packets',0)>0 for e in events),'Actual network partition lacks observed native packet drops')
    require(any(e['kind']=='actual-owned-helper-entry' and e['token'].startswith('PILOT_MULTI_S3_') for e in events),'Worker loss did not interrupt live native work')
    for prefix,observed in [('PILOT_MULTI_S1_',local),('PILOT_MULTI_S2_',events),('PILOT_MULTI_S4_',events)]:
        require(any(e['kind']=='actual-owned-helper-entry' and e['token'].startswith(prefix) for e in observed),'Native execution placement lacks independent host kernel attribution: '+prefix)
    require(len(native.get('observations',[]))==4 and not native.get('harness_error'),'Native multi-host scenario execution incomplete')
    native.update(kind='native-adapter-validation' if unit==0 else 'native-campaign-family-unit',full_campaign_coverage=unit!=0,runtime_identity=json.loads((a/'installation.json').read_text())['installed_build'],
        actual_independent_hosts=True,actual_kernel_boot_ids=[gateway['host_boot_id'],worker['host_boot_id']],native_full_worker_session_dispatch=True,
        controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['PERF-07']},validation_complete=True,fixture_and_invocation_valid=True,
        independent_worker_host_events=events,independent_gateway_host_events=local,worker_host_provenance=worker,gateway_host_provenance=gateway)
    for row in native['observations']:
        row['unit']=unit or 1
        if row['scenario_id']=='PERF-07-S03':
            row['assertions'].append(dict(name='independent-Gateway-observer-sees-no-implicit-local-business-replay',verdict='fail' if any(e['kind']=='actual-owned-helper-entry' and e['token'].startswith('PILOT_MULTI_S3_') for e in local) else 'pass',evidence=['independent_gateway_host_events']))
            row['state']='pass' if all(a['verdict']=='pass' for a in row['assertions']) else 'fail'
    return native


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--mode',choices=['calibration','formal'],required=True);args=parser.parse_args()
    plan=load_plan();args.output.mkdir(parents=True,exist_ok=True);proofs=args.output/'provenance';proofs.mkdir(exist_ok=True)
    if args.mode=='calibration':
        native=joined(args.input,0,plan);path=proofs/('adapter-validation-'+os.environ['GITHUB_RUN_ID']+'-PERF-07.json');path.write_text(json.dumps(native,ensure_ascii=False)+'\n')
        require_execution_ready(plan,'PERF-07',load_proofs(proofs));return
    candidates=list(args.input.rglob('adapter-validation-*-PERF-07.json'));require(len(candidates)==1,'Actual whole-family calibration proof missing')
    shutil.copy(candidates[0],proofs/candidates[0].name);require_execution_ready(plan,'PERF-07',load_proofs(proofs))
    rows=[]
    for unit in range(1,7):
        native=joined(args.input,unit,plan);directory=args.output/('unit-'+str(unit));directory.mkdir();path=directory/'summary.json';raw=(json.dumps(native,ensure_ascii=False)+'\n').encode();path.write_bytes(raw)
        rows.extend(bind_unit(plan,'PERF-07',unit,native,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_SHA'],str(path.relative_to(args.output)),hashlib.sha256(raw).hexdigest()))
        for role in ['gateway','worker']:
            source=args.input/('multihost-native-'+role+'-'+str(unit));shutil.copytree(source,directory/role)
    (args.output/'results.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
    (args.output/'execution.json').write_text(json.dumps(dict(github_run_id=os.environ['GITHUB_RUN_ID'],controller_commit=os.environ['GITHUB_SHA'],case_id='PERF-07',plan_sha256=plan['plan_sha256'],full_campaign_coverage=True,harness_failures=[],completed_records=len(rows)))+'\n')

if __name__=='__main__':main()
