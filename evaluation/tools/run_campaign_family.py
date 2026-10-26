#!/usr/bin/env python3
"""Execute every prescribed independent unit of one calibrated native family."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from adapter_readiness import SOURCES, load_proofs, proof_directory, require_execution_ready
from campaign import DEFAULT_PLAN, load_plan, scenario_index, validate_result, records_from
from provider_plugin import verify as verify_plugin
from suite import ROOT, require
from target import verify_installation

NATIVE_FAMILIES = [family for family in SOURCES if family not in {'PERF-09','SEC-09','PERF-10','COST-03','REL-08','PERF-07','COST-07'}]


def bind_unit(plan, family, unit, native, run_id, controller_commit, native_reference, native_sha256, selected_scenarios=None):
    """Bind new formal executions; development reports can never be promoted."""
    require(native.get('kind')=='native-campaign-family-unit' and native.get('full_campaign_coverage') is True,
            'Only new explicitly formal native executions can supply campaign observations')
    require(not native.get('harness_error'),'Native unit has a harness failure')
    identity=native['runtime_identity']
    require(identity['version']==plan['target']['version'] and identity['commit']==plan['target']['source_commit'],'Native runtime pin mismatch')
    require(native.get('case_id')==family,'Native family mismatch')
    if family=='REL-08':
        require(native.get('actual_source_os')=='Linux' and native.get('actual_target_os')=='Windows' and native.get('target_node_platform')=='win32' and native.get('native_windows_job_object') is True,
                'Cross-OS results require actual native Linux and Windows execution; generic Linux or syntax evidence cannot substitute')
    if family=='PERF-07':require(native.get('actual_independent_hosts') is True and native.get('native_full_worker_session_dispatch') is True and len(set(native.get('actual_kernel_boot_ids',[])))==2,'Actual full native session hosting on independent VM kernels is required')
    expected={sid for sid,(case,_) in scenario_index(plan).items() if case['id']==family}
    if selected_scenarios:
        require(len(selected_scenarios)==len(set(selected_scenarios)) and set(selected_scenarios)<=expected,
                'Pending scenario selection is outside the selected family or duplicated')
        expected=set(selected_scenarios)
    rows=native.get('observations',[])
    require(len(rows)==len(expected) and {r['scenario_id'] for r in rows}==expected,'Native unit has missing or duplicated scenarios')
    for path in SOURCES[family]:
        require(native['controller_sha256'].get(path)==hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
                'Native controller source differs from the reviewed adapter: '+path)
    results=[]
    for row in rows:
        require(row['unit']==unit,'Native unit index mismatch')
        result=dict(schema_version=1,plan_sha256=plan['plan_sha256'],product='openclaw',
            target_version=identity['version'],target_commit=identity['commit'],scenario_id=row['scenario_id'],unit=unit,
            state=row['state'],fixture_validated=row['fixture_validated'],native_invoked=row['native_invoked'],
            run_id=run_id,controller_commit=controller_commit,
            evidence=[native_reference+'#'+row['scenario_id']],native_summary_sha256=native_sha256,
            assertions=row.get('assertions',[]),full_campaign_coverage=True,model_execution='deterministic-local-fixture')
        if result['state'] in {'harness-error','blocked'}:
            result['reason']=row.get('reason','Native unit did not produce a valid observation')
        elif result['state']=='unsupported':
            for field in ['native_capability_absent','capability_evidence','probe_attempted','native_contract','exclusion_reason']:
                result[field]=row.get(field)
        validate_result(result,plan)
        results.append(result)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-modules',type=Path,required=True)
    parser.add_argument('--package-lock',type=Path,required=True)
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=NATIVE_FAMILIES,required=True)
    parser.add_argument('--proofs',type=Path,help='Current native calibration proofs, including proofs produced earlier in this hosted job')
    parser.add_argument('--scenarios',nargs='+',help='Execute only explicit pending scenarios, without rerunning accepted observations')
    args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()==0,'Formal execution is restricted to the disposable hosted controller')
    plan=load_plan()
    require_execution_ready(plan,args.case,load_proofs(args.proofs or proof_directory(plan)))
    installation=verify_installation(plan['target'],args.runtime_modules,args.package_lock)
    plugin=verify_plugin(args.runtime_modules,args.package_lock)
    case=next(c for c in plan['cases'] if c['id']==args.case)
    selected=args.scenarios or [s['id'] for s in case['scenarios']]
    require(len(selected)==len(set(selected)) and set(selected)<={s['id'] for s in case['scenarios']},'Invalid pending scenario selection')
    accepted=records_from(DEFAULT_PLAN.parent/'results')
    require(not any(r['scenario_id'] in selected and r['state'] in {'pass','fail','unsupported'} for r in accepted),
            'Selected scenarios already have accepted formal observations; do not repeat valid work')
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    failures=[]
    (args.output/'installation.json').write_text(json.dumps(installation,indent=2)+'\n')
    (args.output/'provider-plugin.json').write_text(json.dumps(plugin,indent=2)+'\n')
    for unit in range(1,case['required_independent_units']+1):
        directory=args.output/('unit-'+str(unit))
        try:
            execution=subprocess.run([sys.executable,str(ROOT/'evaluation/tools/run_local.py'),
                '--runtime-modules',str(args.runtime_modules),'--node',str(args.node),'--output',str(directory),
                '--native-case',args.case,'--campaign-unit',str(unit),'--hosted-profile','--ssh-backend',
                '--memory-mib','3072','--timeout','1200' if args.case=='REL-11' else '600','--tmpfs-mib','384' if args.case in {'REL-10','REL-11'} else '128' if args.case in {'OBS-02','OBS-04','REL-07','REL-12','SEC-12','OBS-01','EXT-04','SEC-04','EXT-02','SEC-02','SEC-06','REL-01','EXT-07','REL-05','EXT-03','OBS-03','COST-05','REL-03','REL-11'} else '64',
                *[value for sid in (args.scenarios or []) for value in ['--native-scenario',sid]]],timeout=1240 if args.case=='REL-11' else 640,check=False)
            require(execution.returncode==0,'Native unit controller did not finish successfully')
            path=directory/'summary.json'
            data=path.read_bytes()
            results.extend(bind_unit(plan,args.case,unit,json.loads(data),os.environ['GITHUB_RUN_ID'],
                os.environ['GITHUB_SHA'],directory.name+'/summary.json',hashlib.sha256(data).hexdigest(),args.scenarios))
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            failures.append(dict(unit=unit,error=type(error).__name__+': '+str(error)[:1800]))
        # Retain completed units even if a later independent unit encounters a
        # harness error. Product failures are completed data and do not stop.
        (args.output/'results.json').write_text(json.dumps(results,ensure_ascii=False,separators=(',',':'))+'\n')
        (args.output/'execution.json').write_text(json.dumps(dict(case_id=args.case,plan_sha256=plan['plan_sha256'],
            github_run_id=os.environ['GITHUB_RUN_ID'],controller_commit=os.environ['GITHUB_SHA'],
            completed_records=len(results),required_units=case['required_independent_units'],harness_failures=failures,
            selected_scenarios=selected,
            full_campaign_coverage=True,paid_model_calls=0),indent=2)+'\n')
    require(not failures,'One or more units have harness failures; completed independent units remain retained')
    print(json.dumps(dict(case_id=args.case,formal_observations=len(results),product_failures=sum(r['state']=='fail' for r in results))))


if __name__=='__main__':
    main()
