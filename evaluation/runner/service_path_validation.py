"""Native calibration/formal driver for public service-path and trace adapters."""
import argparse
import json
import resource
import sys

import mechanism_cases
import pilot
import service_path_cases
import trace_access_cases
import lifecycle_cases
import execution_authority_cases
import operational_diagnosis_cases
import isolation_setup_cases
import instruction_input_cases
import backup_cases
import mcp_contract_cases
import relocation_cases
import recovery_cases
import scheduling_cases
import effect_recovery_cases
import policy_resolution_cases
import network_boundary_cases
import privacy_cases
import collector_cases
import oauth_cases
import retention_cases
import trajectory_cases
import dependency_cases
import extension_security_cases
import authorization_observation_cases
import context_contract_cases
import session_authority_cases
import harness_contract_cases
import credential_cases


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=[*service_path_cases.FAMILIES,*lifecycle_cases.FAMILIES,*mcp_contract_cases.FAMILIES,'OBS-07','SEC-01','OBS-05','SEC-03','EXT-06','REL-10','REL-06','REL-04','PERF-03','REL-02','SEC-05','SEC-10','SEC-08','OBS-02','SEC-07','OBS-04','OBS-06','REL-07','REL-12','SEC-12','OBS-01','EXT-04','SEC-04','EXT-02','SEC-02'],required=True)
    parser.add_argument('--campaign-unit',type=int,choices=range(1,7))
    parser.add_argument('--scenario',action='append',help='Explicit selected pending scenario; formal units only')
    args=parser.parse_args()
    if args.scenario and not args.campaign_unit:parser.error('Calibration must cover the entire selected family')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    for name in ['tmp','home','cache','run']:(pilot.BASE/name).mkdir(exist_ok=True)
    module=trace_access_cases if args.case=='OBS-07' else lifecycle_cases if args.case in lifecycle_cases.FAMILIES else service_path_cases
    if args.case=='SEC-01':module=execution_authority_cases
    if args.case=='OBS-05':module=operational_diagnosis_cases
    if args.case=='SEC-03':module=isolation_setup_cases
    if args.case=='EXT-06':module=instruction_input_cases
    if args.case=='REL-10':module=backup_cases
    if args.case in mcp_contract_cases.FAMILIES:module=mcp_contract_cases
    if args.case=='REL-06':module=relocation_cases
    if args.case=='REL-04':module=recovery_cases
    if args.case=='PERF-03':module=scheduling_cases
    if args.case=='REL-02':module=effect_recovery_cases
    if args.case=='SEC-05':module=policy_resolution_cases
    if args.case=='SEC-10':module=network_boundary_cases
    if args.case=='SEC-08':module=privacy_cases
    if args.case=='OBS-02':module=collector_cases
    if args.case=='SEC-07':module=oauth_cases
    if args.case=='OBS-04':module=retention_cases
    if args.case=='OBS-06':module=trajectory_cases
    if args.case in dependency_cases.FAMILIES:module=dependency_cases
    if args.case=='SEC-12':module=extension_security_cases
    if args.case=='OBS-01':module=authorization_observation_cases
    if args.case=='EXT-04':module=context_contract_cases
    if args.case=='SEC-04':module=session_authority_cases
    if args.case=='EXT-02':module=harness_contract_cases
    if args.case=='SEC-02':module=credential_cases
    selected=[sid for sid in module.SCENARIOS if sid.startswith(args.case+'-') and (not args.scenario or sid in args.scenario)]
    if args.scenario and (len(args.scenario)!=len(set(args.scenario)) or set(args.scenario)!=set(selected)):
        parser.error('Selected scenarios must be distinct members of the selected family')
    report=dict(kind='native-campaign-family-unit' if args.campaign_unit else 'native-adapter-validation',
        product='openclaw',studies=[],case_id=args.case,full_campaign_coverage=bool(args.campaign_unit),observations=[],paid_model_calls=0)
    try:
        report['storage_guard_check']=pilot.storage_guard_check()
        report['fixture_selfcheck']=mechanism_cases.selfcheck()
        if args.case=='REL-06':report['uid_environment_preflight']=relocation_cases.environment_selfcheck()
        if args.case=='SEC-10':report['network_environment_preflight']=network_boundary_cases.environment_selfcheck()
        if args.case=='SEC-07':report['oauth_environment_preflight']=oauth_cases.environment_selfcheck()
        if args.case=='OBS-02':report['addon_environment_preflight']=collector_cases.environment_selfcheck()
        if args.case in {*dependency_cases.FAMILIES,'SEC-12'}:report['dependency_environment_preflight']=dependency_cases.environment_selfcheck()
        for sid in selected:
            row=module.run_scenario(pilot.BASE/sid.lower(),sid,args.campaign_unit or 1)
            report['observations'].append(row)
            print(json.dumps(dict(kind='adapter-validation-checkpoint',product='openclaw',observation=row)),flush=True)
        expected=len(selected)
        report['validation_complete']=len(report['observations'])==expected
        report['fixture_and_invocation_valid']=all(r['state']!='harness-error' and r['native_invoked'] and r['fixture_validated'] for r in report['observations'])
        if not report['validation_complete'] or not report['fixture_and_invocation_valid']:
            report['harness_error']='Native family has an invalid fixture or invocation; calibration/formal unit incomplete'
    except Exception as error:report['harness_error']=type(error).__name__+': '+str(error)[:2000]
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if report.get('harness_error'):sys.exit(1)


if __name__=='__main__':main()
