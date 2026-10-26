"""Calibrate independent native mechanism adapters; no full coverage awarded."""
import argparse
import json
import resource
import sys

import mechanism_cases
import pilot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=list(mechanism_cases.FAMILIES), required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16*1024**2, 16*1024**2))
    for name in ['tmp', 'home', 'cache', 'run']:
        (pilot.BASE/name).mkdir(exist_ok=True)
    report = dict(kind='native-adapter-validation', product='openclaw', studies=[], case_id=args.case,
                  full_campaign_coverage=False, observations=[], paid_model_calls=0)
    try:
        report['storage_guard_check'] = pilot.storage_guard_check()
        report['fixture_selfcheck'] = mechanism_cases.selfcheck()
        for scenario in mechanism_cases.SCENARIOS:
            if not scenario.startswith(args.case+'-'):
                continue
            observation = mechanism_cases.run_scenario(pilot.BASE/scenario.lower(), scenario)
            report['observations'].append(observation)
            print(json.dumps(dict(kind='adapter-validation-checkpoint', product='openclaw', observation=observation)), flush=True)
        report['validation_complete'] = len(report['observations']) == len(mechanism_cases.FAMILIES[args.case])
        report['fixture_and_invocation_valid'] = all(r['state'] != 'harness-error' and r['fixture_validated'] and r['native_invoked'] for r in report['observations'])
        if not report['validation_complete'] or not report['fixture_and_invocation_valid']:
            report['harness_error'] = 'Missing native invocation or invalid fixture; no full coverage awarded'
    except Exception as error:
        report['harness_error'] = type(error).__name__+': '+str(error)[:3000]
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if report.get('harness_error'):
        sys.exit(1)


if __name__ == '__main__':
    main()
