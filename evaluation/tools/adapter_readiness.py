#!/usr/bin/env python3
"""Audit actual scenario adapter preparation against the complete frozen scope."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from campaign import DEFAULT_PLAN, load_plan, scenario_index
from suite import ROOT, require

SOURCES={
    'REL-14':['evaluation/runner/protocol_cases.py','evaluation/runner/pilot.py','evaluation/runner/adapter_validation.py','evaluation/runner/mcp_probe.py','evaluation/tools/run_local.py'],
    'REL-15':['evaluation/runner/protocol_cases.py','evaluation/runner/pilot.py','evaluation/runner/adapter_validation.py','evaluation/runner/mcp_probe.py','evaluation/tools/run_local.py'],
    'EXT-08':['evaluation/runner/hook_cases.py','evaluation/runner/pilot.py','evaluation/runner/adapter_validation.py','evaluation/tools/run_local.py'],
    'PERF-09':['evaluation/runner/task_cases.py','evaluation/runner/task_unit.py','evaluation/runner/function_probe.py',
               'evaluation/runner/pilot.py','evaluation/tools/run_local.py','evaluation/tools/run_task_unit.py',
               'evaluation/tools/task_workloads.py','evaluation/tools/task_acceptance.py','evaluation/tools/model_relay.py','evaluation/tools/task_transcripts.py'],
}
for _family in ['PERF-05','PERF-06','COST-01','COST-06','EXT-09']:
    SOURCES[_family]=['evaluation/runner/mechanism_cases.py','evaluation/runner/mechanism_validation.py',
                      'evaluation/runner/pilot.py','evaluation/runner/hook_cases.py','evaluation/tools/run_local.py']


def native_validation(plan,proofs):
    """A native product failure can validate an adapter; fixture failure cannot."""
    verified={}
    for proof in proofs:
        require(proof.get('kind')=='native-adapter-validation','Expected candidate-adapter validation evidence')
        require(proof.get('full_campaign_coverage') is False,'Preparation proof cannot be promoted into campaign observations')
        identity=proof.get('runtime_identity',{})
        if identity.get('version')!=plan['target']['version'] or identity.get('commit')!=plan['target']['source_commit']: continue
        case=proof.get('case_id')
        if case not in SOURCES: continue
        hashes=proof.get('controller_sha256',{})
        if not all(hashes.get(p)==hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES[case]): continue
        if proof.get('harness_error') or not proof.get('validation_complete') or not proof.get('fixture_and_invocation_valid'): continue
        for observation in proof.get('observations',[]):
            if observation.get('native_invoked') is True and observation.get('fixture_validated') is True and observation.get('state') in {'pass','fail'}:
                verified[observation['scenario_id']]=observation
    return verified


def readiness(plan,proofs=()):
    verified=native_validation(plan,proofs)
    rows=[]
    for sid,(case,scenario) in scenario_index(plan).items():
        family=case['id']
        state='native-validated-candidate' if sid in verified else 'candidate-awaiting-native-validation' if family in SOURCES else 'not-implemented'
        rows.append(dict(scenario_id=sid,case_id=family,dimension=case['dimension'],name=scenario['name'],
                         preparation_state=state,full_campaign_executed=False,
                         source_files=SOURCES.get(family,['evaluation/tools/task_workloads.py','evaluation/tools/task_acceptance.py'] if family=='PERF-09' else [])))
    counts=Counter(row['preparation_state'] for row in rows)
    missing=[row['scenario_id'] for row in rows if row['preparation_state']!='native-validated-candidate']
    return dict(kind='full-campaign-adapter-readiness',plan_sha256=plan['plan_sha256'],scenario_count=len(rows),
                preparation_counts=dict(counts),ready_for_full_execution=not missing,
                scenarios_requiring_implementation_or_validation=missing,scenario_status=rows,
                rule='A candidate must pass native fixture/invocation validation against its current controller hashes. Product failures remain valid observations. Development calibration never counts as full experiment coverage.')


def load_proofs(directory):
    return [json.loads(path.read_text()) for path in sorted(Path(directory).glob('adapter-validation-*.json'))
            if re.fullmatch(r'adapter-validation-\d+-(?:REL|SEC|PERF|COST|EXT|OBS)-\d{2}\.json',path.name)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
    parser.add_argument('--proofs',type=Path)
    parser.add_argument('--details',action='store_true')
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args()
    plan=load_plan(args.plan)
    report=readiness(plan,load_proofs(args.proofs or args.plan.parent/'preparation'))
    if not args.details: report={k:v for k,v in report.items() if k not in {'scenario_status','scenarios_requiring_implementation_or_validation'}}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.require_complete and not report['ready_for_full_execution']: parser.exit(1,'Full scope still has missing or unvalidated adapters; do not start a partial run as the full campaign\n')


if __name__=='__main__': main()
