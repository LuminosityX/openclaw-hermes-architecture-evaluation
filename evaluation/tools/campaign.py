#!/usr/bin/env python3
"""Freeze full experiment coverage and keep architecture analysis behind completion."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path

from suite import MATRIX, ROOT, load_matrix, require, unique_object

DEFAULT_PLAN=ROOT/'evaluation/campaigns/full-20261026-batched/plan.json'
RESULT_STATES={'pass','fail','unsupported','blocked','harness-error'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def freeze(matrix):
    cases=[]
    for dimension in matrix['dimensions']:
        for case in dimension['experiments']:
            cases.append(dict(id=case['id'],dimension=dimension['id'],title=case['title'],phase=case['billing'],
                required_independent_units=6 if dimension['id'] in {'performance','resources_cost'} else 3,
                oracle=case['oracle'],intervention=case['intervention'],controls=case['controls'],
                required_evidence=case['evidence'],metrics=case['metrics'],
                scenarios=[dict(id=f'{case["id"]}-S{i:02}',name=name) for i,name in enumerate(case['scenarios'],1)]))
    body=dict(schema_version=1,campaign_id='full-20261026',product='openclaw',
        created_at_utc=datetime.now(timezone.utc).isoformat(),matrix_sha256=digest(matrix),target=matrix['target'],
        model=dict(provider='deepseek',model='deepseek-flash',base_url='https://api.deepseek.com',
                   api_key_source='GitHub Actions repository secret DEEPSEEK_API_KEY',
                   spend_limit=None,spend_limit_authorization='User explicitly requested no campaign spending ceiling.',
                   provider_alias_limitation='Record models-list metadata and response model/version for every run; do not claim immutable weights if the provider only exposes a moving alias.'),
        workflow=dict(order=['prepare-all-adapters','execute-full-frozen-scope','audit-completion','unified-architecture-analysis'],
                      interim_architecture_conclusions=False,
                      previous_pilots_count_as_full_coverage=False,
                      source_reading_during_execution='Allowed for test implementation and harness repair; architecture interpretation is deferred.'),
        resource_policy=dict(local_runtime_installation=False,execution_host='disposable-hosted-runners',
                             shared_installation_per_shard=True,copy_dependencies_per_case=False,
                             retain_runtime_state=False,maximum_local_campaign_evidence_bytes=4*1024**2,
                             note='Per-scenario runtime/time/process/token limits are experimental conditions; monetary ceiling is explicitly disabled.'),
        cases=cases)
    return dict(**body,plan_sha256=digest(body))


def load_plan(path=DEFAULT_PLAN):
    plan=json.loads(Path(path).read_text(),object_pairs_hook=unique_object)
    body={k:v for k,v in plan.items() if k!='plan_sha256'}
    require(plan['plan_sha256']==digest(body),'Frozen campaign plan changed; create a new campaign instead of silently changing scope')
    require(plan['product']=='openclaw' and len(plan['cases'])==60,'Full campaign must preserve all sixty experiment families')
    ids=[s['id'] for c in plan['cases'] for s in c['scenarios']]
    require(len(ids)==len(set(ids))==257,'Full campaign must preserve all 257 scenarios')
    require(plan['workflow']['interim_architecture_conclusions'] is False,'Experiment-first campaign required')
    return plan


def scenario_index(plan):
    return {s['id']:(case,s) for case in plan['cases'] for s in case['scenarios']}


def validate_nonapplicability(result,plan):
    require(result.get('native_invoked') is True and result.get('fixture_validated') is True,
            'Unsupported requires actual native invocation and a validated capability probe')
    require(result.get('native_capability_absent') is True and result.get('capability_evidence') and result.get('probe_attempted') is True,
            'Unsupported needs a native capability probe and versioned support-contract evidence; missing adapters are not unsupported features')
    contract=result.get('native_contract',{})
    require(contract.get('target_commit')==plan['target']['source_commit'] and contract.get('reference') and contract.get('sha256'),
            'Unsupported requires the pinned native contract, reference and SHA256')
    require(result.get('exclusion_reason')=='capability-not-provided',
            'Environment failures and missing implementations cannot establish nonapplicability')


def validate_result(result,plan,allow_development=False):
    require(result['schema_version']==1 and result['plan_sha256']==plan['plan_sha256'],'Result must bind the frozen full campaign')
    require(result['product']=='openclaw','Result must target OpenClaw')
    require(result['target_version']==plan['target']['version'] and result['target_commit']==plan['target']['source_commit'],'Result runtime pin mismatch')
    require(result['scenario_id'] in scenario_index(plan),'Unknown scenario')
    require(result['state'] in RESULT_STATES,'Unknown result state')
    require(result['evidence'] and result['run_id'],'Actual run and evidence references required')
    require(allow_development or result.get('full_campaign_coverage') is not False,
            'Development calibration cannot count as full campaign execution')
    require(not {'architecture_conclusion','causal_interpretation','overall_grade'}&set(result),'Architecture interpretation is deferred until the experiment campaign is sealed')
    state=result['state']
    if state in {'pass','fail'}:
        require(result['fixture_validated'] is True and result['native_invoked'] is True,'Native execution and validated acceptance fixtures required')
        case,_=scenario_index(plan)[result['scenario_id']]
        require(type(result['unit']) is int and 1<=result['unit']<=case['required_independent_units'],'Independent unit is outside the preregistered count')
        assertions=result['assertions']
        require(assertions and all(a['verdict'] in {'pass','fail'} and a.get('evidence') for a in assertions),'Acceptance assertions need their own evidence')
        require((state=='pass')==all(a['verdict']=='pass' for a in assertions),'Result disagrees with acceptance assertions')
    elif state=='unsupported':
        validate_nonapplicability(result,plan)
    else:
        require(result.get('reason'),'Blocked/harness failures need an explicit reason')
    return result


def audit(plan,records):
    by_scenario={sid:[] for sid in scenario_index(plan)}
    for result in records:
        validate_result(result,plan)
        by_scenario[result['scenario_id']].append(result)
    scenarios=[]
    for sid,(case,scenario) in scenario_index(plan).items():
        attempts=by_scenario[sid]
        valid={}
        for r in attempts:
            if r['state'] in {'pass','fail'}:
                require(r['unit'] not in valid,'More than one accepted observation for the same independent unit; explicitly supersede an invalid attempt instead of inflating samples')
                valid[r['unit']]=r
        if len(valid)==case['required_independent_units']:
            state='fail' if any(r['state']=='fail' for r in valid.values()) else 'pass'
        elif not valid and any(r['state']=='unsupported' for r in attempts):
            state='unsupported'
        elif any(r['state']=='blocked' for r in attempts):
            state='blocked'
        elif any(r['state']=='harness-error' for r in attempts):
            state='harness-error'
        else:
            state='partial' if valid else 'not-run'
        scenarios.append(dict(id=sid,case_id=case['id'],dimension=case['dimension'],name=scenario['name'],state=state,
                              valid_units=len(valid),required_units=case['required_independent_units']))
    counts=Counter(s['state'] for s in scenarios)
    blockers=[s['id'] for s in scenarios if s['state'] not in {'pass','fail','unsupported'}]
    return dict(kind='full-campaign-completion-audit',campaign_id=plan['campaign_id'],plan_sha256=plan['plan_sha256'],
                experiment_families=60,scenarios=257,scenario_counts=dict(counts),
                accepted_observation_count=sum(s['valid_units'] for s in scenarios),
                measured_scenarios=counts['pass']+counts['fail'],verified_nonapplicable_scenarios=counts['unsupported'],
                missing_or_invalid_scenarios=blockers,experiments_complete=not blockers,
                analysis_allowed=not blockers,scenario_status=scenarios,
                rule='Failures are completed experiments. Missing implementations, unavailable environments, harness failures and missing credentials remain incomplete. Verified nonapplicability is disclosed separately from measured coverage.')


def records_from(directory):
    records=[]
    if directory.exists():
        for path in sorted([*directory.glob('*.json'),*directory.glob('*.json.gz')]):
            if path.suffix=='.gz':
                require(path.stat().st_size<=8*1024**2,'Compressed result file exceeds its byte bound')
                with gzip.open(path,'rb') as source:raw=source.read(8*1024**2+1)
                require(len(raw)<=8*1024**2,'Expanded result file exceeds its byte bound')
                data=json.loads(raw,object_pairs_hook=unique_object)
            else:data=json.loads(path.read_text(),object_pairs_hook=unique_object)
            records.extend(data if isinstance(data,list) else [data])
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('freeze')
    for name in ['status','seal']:
        command=sub.add_parser(name)
        command.add_argument('--results',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='freeze':
            require(not args.plan.exists(),'Do not overwrite a frozen campaign plan')
            plan=freeze(load_matrix())
            args.plan.parent.mkdir(parents=True,exist_ok=True)
            args.plan.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(dict(plan=str(args.plan),sha256=plan['plan_sha256'],families=len(plan['cases']),scenarios=len(scenario_index(plan)))))
        else:
            plan=load_plan(args.plan)
            result=audit(plan,records_from(args.results or args.plan.parent/'results'))
            if args.command=='seal':
                require(result['experiments_complete'],'Full experiment campaign is incomplete; unified architecture analysis remains locked')
                (args.plan.parent/'experiments-sealed.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            summary={k:v for k,v in result.items() if k not in {'scenario_status','missing_or_invalid_scenarios'}}
            summary['remaining_count']=len(result['missing_or_invalid_scenarios'])
            print(json.dumps(summary,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError,OSError) as error:
        parser.exit(1,f'FAIL: {error}\n')


if __name__=='__main__':
    main()
