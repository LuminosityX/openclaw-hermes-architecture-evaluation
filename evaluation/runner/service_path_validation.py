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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=[*service_path_cases.FAMILIES,*lifecycle_cases.FAMILIES,*mcp_contract_cases.FAMILIES,'OBS-07','SEC-01','OBS-05','SEC-03','EXT-06','REL-10','REL-06'],required=True)
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
    selected=[sid for sid in module.SCENARIOS if sid.startswith(args.case+'-') and (not args.scenario or sid in args.scenario)]
    if args.scenario and (len(args.scenario)!=len(set(args.scenario)) or set(args.scenario)!=set(selected)):
        parser.error('Selected scenarios must be distinct members of the selected family')
    report=dict(kind='native-campaign-family-unit' if args.campaign_unit else 'native-adapter-validation',
        product='openclaw',studies=[],case_id=args.case,full_campaign_coverage=bool(args.campaign_unit),observations=[],paid_model_calls=0)
    try:
        report['storage_guard_check']=pilot.storage_guard_check()
        report['fixture_selfcheck']=mechanism_cases.selfcheck()
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
