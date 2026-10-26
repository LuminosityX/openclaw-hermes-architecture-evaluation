#!/usr/bin/env python3
"""Audit actual scenario adapter preparation against the complete frozen scope."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from campaign import DEFAULT_PLAN, load_plan, scenario_index, audit, records_from,validate_nonapplicability
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
SOURCES['SEC-11']=['evaluation/runner/gateway_auth_cases.py','evaluation/runner/gateway_auth_probe.mjs',
                   'evaluation/runner/mechanism_cases.py','evaluation/runner/hook_cases.py','evaluation/runner/pilot.py','evaluation/tools/run_local.py']
for _family in ['PERF-01','PERF-02','PERF-04','COST-02','COST-04','OBS-07']:
    SOURCES[_family]=['evaluation/runner/service_path_cases.py','evaluation/runner/service_path_validation.py',
        'evaluation/runner/trace_access_cases.py','evaluation/runner/trace_access_probe.mjs',
        'evaluation/runner/public_gateway_client.mjs','evaluation/runner/mechanism_cases.py',
        'evaluation/runner/hook_cases.py','evaluation/runner/pilot.py','evaluation/tools/run_local.py']
for _family in ['REL-09','EXT-01','PERF-08']:
    SOURCES[_family]=[*SOURCES['PERF-01'],'evaluation/runner/lifecycle_cases.py']
SOURCES['SEC-01']=[*SOURCES['PERF-01'],'evaluation/runner/execution_authority_cases.py',
    'evaluation/runner/operation_fixture.py','evaluation/runner/protocol_cases.py','evaluation/runner/mcp_probe.py']
SOURCES['OBS-05']=[*SOURCES['PERF-01'],'evaluation/runner/operational_diagnosis_cases.py']
SOURCES['SEC-03']=[*SOURCES['SEC-01'],'evaluation/runner/isolation_setup_cases.py']
SOURCES['EXT-06']=[*SOURCES['SEC-01'],'evaluation/runner/instruction_input_cases.py']
SOURCES['REL-10']=[*SOURCES['PERF-01'],'evaluation/runner/backup_cases.py']
for _family in ['REL-13','EXT-05']:
    SOURCES[_family]=[*SOURCES['SEC-01'],'evaluation/runner/mcp_http_fixture.py','evaluation/runner/mcp_contract_cases.py']
SOURCES['REL-06']=[*SOURCES['SEC-01'],'evaluation/runner/relocation_cases.py']
SOURCES['REL-04']=[*SOURCES['SEC-01'],'evaluation/runner/recovery_cases.py','evaluation/runner/approval_probe.mjs']
SOURCES['PERF-03']=[*SOURCES['REL-13'],'evaluation/runner/scheduling_cases.py']
SOURCES['REL-02']=[*SOURCES['REL-13'],'evaluation/runner/recovery_cases.py','evaluation/runner/effect_recovery_cases.py']
SOURCES['SEC-05']=[*SOURCES['REL-02'],'evaluation/runner/operational_diagnosis_cases.py','evaluation/runner/policy_resolution_cases.py']
SOURCES['SEC-10']=[*SOURCES['SEC-01'],'evaluation/runner/network_boundary_cases.py']
SOURCES['SEC-09']=[*SOURCES['PERF-09'],'evaluation/runner/injection_cases.py','evaluation/tools/injection_workloads.py',
    'evaluation/tools/run_injection_family.py','evaluation/runner/provider_bridge.py','evaluation/tools/provider_connection.py']
SOURCES['SEC-08']=[*SOURCES['SEC-01'],'evaluation/runner/privacy_cases.py']
SOURCES['OBS-02']=[*SOURCES['REL-02'],'evaluation/runner/collector_cases.py']
SOURCES['PERF-10']=[*SOURCES['PERF-09'],'evaluation/runner/provider_bridge.py','evaluation/runner/conversation_cases.py',
    'evaluation/runner/recovery_cases.py','evaluation/runner/mechanism_cases.py','evaluation/runner/service_path_cases.py',
    'evaluation/runner/hook_cases.py','evaluation/runner/operation_fixture.py',
    'evaluation/tools/conversation_workloads.py','evaluation/tools/run_injection_family.py']
SOURCES['SEC-07']=[*SOURCES['REL-13'],'evaluation/runner/oauth_fixture.py','evaluation/runner/oauth_cases.py']
SOURCES['COST-03']=[*SOURCES['PERF-10'],'evaluation/runner/reuse_cases.py','evaluation/tools/reuse_workloads.py','evaluation/tools/reuse_accounting.py']

SOURCES['OBS-04']=[*SOURCES['SEC-08'],'evaluation/runner/retention_cases.py','evaluation/runner/backup_cases.py']

SOURCES['OBS-06']=[*SOURCES['SEC-08'],'evaluation/runner/trajectory_cases.py']

for _family in ['REL-07','REL-12']:
    SOURCES[_family]=[*SOURCES['SEC-01'],'evaluation/runner/dependency_cases.py','evaluation/runner/package_registry_fixture.py']

SOURCES['SEC-12']=[*SOURCES['REL-07'],'evaluation/runner/extension_security_cases.py','evaluation/runner/effect_recovery_cases.py']

SOURCES['OBS-01']=[*SOURCES['SEC-08'],'evaluation/runner/authorization_observation_cases.py','evaluation/runner/approval_observer.mjs','evaluation/runner/effect_recovery_cases.py','evaluation/runner/recovery_cases.py']

SOURCES['EXT-04']=[*SOURCES['SEC-08'],'evaluation/runner/context_contract_cases.py','evaluation/runner/context_reference.mjs','evaluation/runner/effect_recovery_cases.py']

SOURCES['SEC-04']=[*SOURCES['OBS-01'],'evaluation/runner/session_authority_cases.py','evaluation/runner/mcp_http_fixture.py']

SOURCES['EXT-02']=[*SOURCES['SEC-08'],'evaluation/runner/harness_contract_cases.py','evaluation/runner/harness_reference.mjs','evaluation/runner/external_harness_worker.py','evaluation/runner/effect_recovery_cases.py']

SOURCES['SEC-02']=[*SOURCES['OBS-01'],'evaluation/runner/credential_cases.py','evaluation/runner/credential_worker.py','evaluation/runner/mcp_http_fixture.py']

SOURCES['SEC-06']=[*SOURCES['OBS-01'],'evaluation/runner/revocation_cases.py','evaluation/runner/revocation_observer.mjs','evaluation/runner/owned_open_gate.py','evaluation/runner/backup_cases.py']

SOURCES['REL-01']=[*SOURCES['SEC-08'],'evaluation/runner/admission_cases.py','evaluation/runner/admission_wire.mjs','evaluation/runner/backup_cases.py','evaluation/runner/effect_recovery_cases.py','evaluation/runner/recovery_cases.py']

SOURCES['EXT-07']=list(dict.fromkeys([*SOURCES['EXT-02'],*SOURCES['REL-07'],'evaluation/runner/external_corpus_cases.py']))

SOURCES['REL-05']=list(dict.fromkeys([*SOURCES['EXT-02'],*SOURCES['OBS-01'],*SOURCES['REL-13'],'evaluation/runner/cancellation_cases.py','evaluation/runner/cancellation_control.mjs','evaluation/runner/backup_cases.py']))

SOURCES['EXT-03']=list(dict.fromkeys([*SOURCES['REL-07'],'evaluation/runner/version_skew_cases.py','evaluation/runner/effect_recovery_cases.py','evaluation/tools/prepare_previous_core.py','evaluation/design/previous-core.json']))

SOURCES['OBS-03']=list(dict.fromkeys([*SOURCES['REL-01'],*SOURCES['REL-05'],*SOURCES['SEC-06'],*SOURCES['REL-02'],'evaluation/runner/blind_diagnosis_cases.py','evaluation/runner/blind_native_reader.py']))

SOURCES['COST-05']=list(dict.fromkeys([*SOURCES['OBS-01'],*SOURCES['REL-13'],'evaluation/runner/budget_capability_cases.py','evaluation/tools/prepare_capability_contracts.py','evaluation/design/native-budget-contracts.json']))

SOURCES['REL-08']=['evaluation/runner/portable_support.py','evaluation/runner/portable_core.py','evaluation/tools/run_cross_os.py','evaluation/tools/prepare_portable_runtime.py','evaluation/tools/download_cross_os_source.py','evaluation/tools/target.py','.github/workflows/cross-os-experiments.yml']

SOURCES['REL-03']=list(dict.fromkeys([*SOURCES['OBS-01'],*SOURCES['REL-13'],'evaluation/runner/delegation_cases.py','evaluation/runner/native_freeze.py']))

SOURCES['REL-11']=list(dict.fromkeys([*SOURCES['REL-03'],*SOURCES['REL-10'],*SOURCES['EXT-03'],'evaluation/runner/migration_cases.py','evaluation/runner/migration_trace.py','evaluation/runner/migration_trace_child.py','evaluation/runner/portable_support.py','evaluation/design/migration-source-core.json']))

SOURCES['COST-07']=list(dict.fromkeys([*SOURCES['PERF-09'],'evaluation/runner/billing_cases.py','evaluation/runner/provider_bridge.py','evaluation/runner/privacy_cases.py','evaluation/runner/trace_access_probe.mjs','evaluation/runner/public_gateway_client.mjs','evaluation/tools/billing_accounting.py','evaluation/tools/run_billing_family.py']))


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
        if case=='REL-08' and not (proof.get('actual_source_os')=='Linux' and proof.get('actual_target_os')=='Windows' and proof.get('target_node_platform')=='win32' and proof.get('native_windows_job_object') is True):continue
        hashes=proof.get('controller_sha256',{})
        if not all(hashes.get(p)==hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES[case]): continue
        if proof.get('harness_error') or not proof.get('validation_complete') or not proof.get('fixture_and_invocation_valid'): continue
        observations=proof.get('observations',[])
        expected={sid for sid,(family,_) in scenario_index(plan).items() if family['id']==case}
        actual=[row.get('scenario_id') for row in observations]
        if len(actual)!=len(expected) or set(actual)!=expected: continue
        for observation in observations:
            if observation.get('state')=='unsupported':
                try:validate_nonapplicability(observation,plan)
                except ValueError:continue
                if observation.get('native_invoked') is True and observation.get('fixture_validated') is True:
                    verified[observation['scenario_id']]=observation
                continue
            assertions=observation.get('assertions',[])
            valid_assertions=bool(assertions) and all(a.get('verdict') in {'pass','fail'} and a.get('evidence') for a in assertions)
            consistent=valid_assertions and (observation.get('state')=='pass')==all(a['verdict']=='pass' for a in assertions)
            if observation.get('native_invoked') is True and observation.get('fixture_validated') is True and observation.get('state') in {'pass','fail'} and consistent:
                verified[observation['scenario_id']]=observation
    return verified


def readiness(plan,proofs=(),records=()):
    verified=native_validation(plan,proofs)
    formal=audit(plan,records)
    formal_rows={row['id']:row for row in formal['scenario_status']}
    rows=[]
    for sid,(case,scenario) in scenario_index(plan).items():
        family=case['id']
        state='native-validated-candidate' if sid in verified else 'candidate-awaiting-native-validation' if family in SOURCES else 'not-implemented'
        rows.append(dict(scenario_id=sid,case_id=family,dimension=case['dimension'],name=scenario['name'],
                         preparation_state=state,full_campaign_executed=formal_rows[sid]['state'] in {'pass','fail'},
                         formal_execution_state=formal_rows[sid]['state'],formal_valid_units=formal_rows[sid]['valid_units'],
                         source_files=SOURCES.get(family,['evaluation/tools/task_workloads.py','evaluation/tools/task_acceptance.py'] if family=='PERF-09' else [])))
    counts=Counter(row['preparation_state'] for row in rows)
    missing=[row['scenario_id'] for row in rows if row['preparation_state']!='native-validated-candidate']
    return dict(kind='full-campaign-adapter-readiness',plan_sha256=plan['plan_sha256'],scenario_count=len(rows),
                completed_formal_scenarios=formal['measured_scenarios'],accepted_formal_observations=formal['accepted_observation_count'],
                preparation_counts=dict(counts),ready_for_full_execution=not missing,
                scenarios_requiring_implementation_or_validation=missing,scenario_status=rows,
                rule='Preparation counts apply to new executions at current controller hashes. Recorded formal observations retain their original controller provenance. Product failures remain valid observations. Development calibration never counts as full experiment coverage.')


def load_proofs(directory):
    return [json.loads(path.read_text()) for path in sorted(Path(directory).glob('adapter-validation-*.json'))
            if re.fullmatch(r'adapter-validation-\d+-(?:REL|SEC|PERF|COST|EXT|OBS)-\d{2}\.json',path.name)]


def proof_directory(plan,plan_path=DEFAULT_PLAN):
    return ROOT/plan['preparation_evidence_directory'] if plan.get('preparation_evidence_directory') else Path(plan_path).parent/'preparation'


def require_execution_ready(plan,case_id,proofs):
    report=readiness(plan,proofs)
    if plan['workflow'].get('execution_readiness')=='per-family':
        rows=[row for row in report['scenario_status'] if row['case_id']==case_id]
        require(rows and all(row['preparation_state']=='native-validated-candidate' for row in rows),
                'Selected family has missing or stale native validation; no full experiment started')
    else:
        require(report['ready_for_full_execution'],'Full scope has missing or unvalidated adapters; no full experiment started')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
    parser.add_argument('--proofs',type=Path)
    parser.add_argument('--details',action='store_true')
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args()
    plan=load_plan(args.plan)
    report=readiness(plan,load_proofs(args.proofs or proof_directory(plan,args.plan)),records_from(args.plan.parent/'results'))
    if not args.details: report={k:v for k,v in report.items() if k not in {'scenario_status','scenarios_requiring_implementation_or_validation'}}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.require_complete and not report['ready_for_full_execution']: parser.exit(1,'Full scope still has missing or unvalidated adapters; do not start a partial run as the full campaign\n')


if __name__=='__main__': main()
