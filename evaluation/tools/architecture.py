#!/usr/bin/env python3
"""Select architecture studies and check preregistration metadata; never execute."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from suite import DIMENSIONS, ROOT, load_matrix, require, unique_object

STUDIES = ROOT / 'evaluation/design/architecture-studies.json'
ARTIFACTS = ('runtime_identity', 'source_binding', 'effective_config_baseline',
             'effective_config_intervention', 'fixture_selftest', 'collector_selftest',
             'owned_resources_manifest', 'analysis_plan')
BUDGETS = ('wall_time_seconds', 'cpu_seconds', 'memory_bytes', 'disk_bytes', 'inodes', 'processes', 'connections')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object)


def validate_studies(plan, matrix):
    require(plan['schema_version'] == 1 and plan['product'] == 'openclaw', 'OpenClaw architecture schema required')
    require(plan['status'] == 'planned-not-executed' and plan['execution_enabled'] is False, 'Architecture plan must not claim execution')
    metrics = {d['id']: {m['id']: m for m in d['required_metrics']} for d in matrix['dimensions']}
    cases = {e['id']: e for d in matrix['dimensions'] for e in d['experiments']}
    seen = set()
    for study in plan['studies']:
        sid = study['id']
        require(re.fullmatch(r'ARC-[0-9]{2}', sid) and sid not in seen, f'Invalid or duplicate study: {sid}')
        seen.add(sid)
        require(study['product'] == 'openclaw' and study['status'] == 'planned', f'Invalid scope/status: {sid}')
        require(type(study['wave']) is int and study['wave'] in {1, 2}, f'Invalid wave: {sid}')
        require(study['case_ids'] and len(study['case_ids']) == len(set(study['case_ids'])) and set(study['case_ids']) <= set(cases), f'Unknown or duplicate case mapping: {sid}')
        if study['wave'] == 1:
            require(all(cases[c]['billing'] == 'deterministic-local-fixture' for c in study['case_ids']), f'First wave cannot silently require real usage: {sid}')
        require(study['design_goal']['evidence_status'] in {'documented-goal', 'hypothesis'}, f'Unknown intent evidence: {sid}')
        source = study['source']
        require(source['pin_verification'] == 'pending', f'Plan cannot certify a runtime source binding: {sid}')
        if study['design_goal']['evidence_status'] == 'documented-goal':
            require(source['url'] and source['documented_fact'], f'Documented goal needs a source: {sid}')
        if source['url']:
            require(source['url'].startswith('https://docs.openclaw.ai/'), f'Expected primary documentation: {sid}')
        contrast = study['comparison']
        require(contrast['kind'] in {'native-config', 'boundary-comparison', 'counterfactual'}, f'Unknown contrast: {sid}')
        require([a['id'] for a in contrast['arms']] == ['baseline', 'intervention'], f'Contrast needs two explicit arms: {sid}')
        require(contrast['changed_variable'] and len(contrast['held_constant']) >= 4, f'Controls missing: {sid}')
        require(contrast['confounders'] and study['limitations'], f'Confounders/limitations missing: {sid}')
        require(set(study['axes']) == set(DIMENSIONS), f'Every study must address six axes: {sid}')
        roles = set()
        for axis, observation in study['axes'].items():
            role = observation['role']
            roles.add(role)
            require(role in {'benefit-hypothesis', 'cost-hypothesis', 'guardrail', 'not-applicable'}, f'Unknown axis role: {sid}')
            require(observation['question'], f'Missing axis question or non-applicability reason: {sid}')
            require(set(observation['metrics']) <= set(metrics[axis]), f'Unknown metric: {sid}/{axis}')
            require(len(observation['metrics']) == len(set(observation['metrics'])), f'Duplicate metric: {sid}/{axis}')
            require(bool(observation['metrics']) == (role != 'not-applicable'), f'Non-applicability must be explicit: {sid}/{axis}')
        require({'benefit-hypothesis', 'cost-hypothesis'} <= roles, f'Must state both benefit and cost hypotheses: {sid}')
        require(set(study['hypotheses']) == {'benefit', 'cost', 'falsified_when'} and all(study['hypotheses'].values()), f'Falsifiable hypotheses required: {sid}')
        protocol = study['protocol']
        for field in ['independent_units_per_arm', 'sample_size_rationale', 'paired_blocks', 'thresholds', 'stop_rules']:
            require(protocol[field] is None, f'Unregistered values must remain unset in the shared plan: {sid}/{field}')
        require(len(protocol['reversal_workloads']) >= 2, f'Reversal conditions missing: {sid}')
        require(not {'result', 'score', 'passed', 'tradeoff_proven'} & set(study), f'Plan contains product claims: {sid}')
    require(plan['first_wave'] and len(plan['first_wave']) == len(set(plan['first_wave'])), 'Invalid first wave')
    require(set(plan['first_wave']) == {s['id'] for s in plan['studies'] if s['wave'] == 1}, 'First-wave order/membership mismatch')
    return plan


def load_studies():
    return validate_studies(read_json(STUDIES), load_matrix())


def select_studies(plan, wave=None, identifiers=()):
    require(wave is None or wave in {1, 2}, 'Unknown wave')
    require(set(identifiers) <= {s['id'] for s in plan['studies']}, 'Unknown architecture study')
    selected = [s for s in plan['studies'] if (wave is None or s['wave'] == wave) and (not identifiers or s['id'] in identifiers)]
    require(selected, 'No architecture studies match')
    if wave == 1:
        selected.sort(key=lambda s: plan['first_wave'].index(s['id']))
    return dict(kind='architecture-plan-only', product='openclaw', execution_enabled=False,
                product_run_count=0, studies=selected)


def registration_template(study):
    return dict(schema_version=1, product='openclaw', study_id=study['id'],
                record_kind='preregistration', execution_mode=study['protocol']['execution_mode'],
                target=dict(version=None, source_commit=None),
                independent_units_per_arm=None, paired_blocks=None, sample_size_rationale=None,
                estimand=None, uncertainty_method=None, allocation_and_reset=None,
                workload_revision=None, reversal_workload_revision=None, stop_rules=None,
                contrast=dict(kind=study['comparison']['kind'], changed_variable=study['comparison']['changed_variable'],
                              config_key=study['comparison'].get('config_key'),
                              baseline_config=None, intervention_config=None, unresolved_confounders=None),
                thresholds={axis: [dict(metric=m, minimum_meaningful_difference=None)
                                   for m in observation['metrics']] for axis, observation in study['axes'].items()},
                budgets={**{b: None for b in BUDGETS}, 'model_cost_usd': None},
                artifacts={a:dict(path=None, sha256=None) for a in ARTIFACTS})


def validate_registration(record, plan, matrix):
    require(record['schema_version'] == 1 and record['product'] == 'openclaw' and record['record_kind'] == 'preregistration', 'Expected OpenClaw preregistration')
    require(not {'result', 'score', 'passed', 'tradeoff_proven', 'design_intent_proven'} & set(record), 'Preregistration cannot contain product conclusions')
    study = next((s for s in plan['studies'] if s['id'] == record['study_id']), None)
    require(study is not None, 'Unknown study in preregistration')
    target = record['target']
    require(isinstance(target['version'], str) and target['version'].strip(), 'Pin the installed OpenClaw version')
    require(isinstance(target['source_commit'], str) and re.fullmatch(r'[0-9a-f]{40}', target['source_commit']), 'Pin the full OpenClaw source commit')
    for field in ['independent_units_per_arm', 'paired_blocks']:
        require(type(record[field]) is int and record[field] > 0, f'Preregister {field}')
    require(record['independent_units_per_arm'] == record['paired_blocks'], 'This two-arm protocol requires one independent unit per arm per paired block')
    for field in ['sample_size_rationale', 'estimand', 'uncertainty_method', 'allocation_and_reset', 'workload_revision', 'reversal_workload_revision', 'stop_rules']:
        require(isinstance(record[field], str) and record[field].strip(), f'Preregister {field}')
    contrast = record['contrast']
    require(contrast['kind'] == study['comparison']['kind'] and contrast['changed_variable'] == study['comparison']['changed_variable'], 'Preregistration changes the declared contrast')
    require(isinstance(contrast['baseline_config'], dict) and isinstance(contrast['intervention_config'], dict) and contrast['baseline_config'] != contrast['intervention_config'], 'Capture distinct effective configurations for both arms')
    require(isinstance(contrast['unresolved_confounders'], list), 'Declare unresolved confounders explicitly')
    if contrast['kind'] == 'native-config':
        require(not contrast['unresolved_confounders'], 'Unresolved confounders block a causal native-config contrast')
        left, right = contrast['baseline_config'], contrast['intervention_config']
        key = contrast['config_key']
        require(isinstance(key, str) and key.strip(), 'Bind the native contrast to a verified config key')
        expected_key = study['comparison'].get('config_key')
        require(expected_key is None or key == expected_key, 'Unexpected native config key')
        require(not any(isinstance(value, dict) for value in [*left.values(), *right.values()]), 'Capture flattened stable effective configuration fields')
        require(set(left) == set(right) and {k for k in left if left[k] != right[k]} == {key}, 'Native contrast must change exactly the declared flattened config field')
    require(set(record['thresholds']) == set(DIMENSIONS), 'Preregister thresholds or non-applicability for all six axes')
    for axis, observation in study['axes'].items():
        thresholds = record['thresholds'][axis]
        require(isinstance(thresholds, list) and len(thresholds) == len(observation['metrics']) and {t['metric'] for t in thresholds} == set(observation['metrics']), f'Thresholds must cover the planned metrics: {axis}')
        for threshold in thresholds:
            value = threshold['minimum_meaningful_difference']
            require(type(value) in {int, float} and math.isfinite(value) and value >= 0, f'Declare a finite nonnegative meaningful-difference margin: {axis}')
    for name in BUDGETS:
        require(type(record['budgets'][name]) is int and record['budgets'][name] > 0, f'Declare positive resource budget: {name}')
    mode = record['execution_mode']
    require(mode in {'deterministic', 'real-model'}, 'Select an explicit execution mode')
    case_map = {e['id']: e for d in matrix['dimensions'] for e in d['experiments']}
    requires_real = any(case_map[c]['billing'] == 'real-usage-required' for c in study['case_ids'])
    require(not requires_real or mode == 'real-model', 'This complete study includes real-usage cases; preregister real usage or define a separate deterministic study')
    cost = record['budgets']['model_cost_usd']
    require(type(cost) in {int, float} and math.isfinite(cost) and cost >= 0, 'Declare a finite nonnegative model budget')
    require(cost == 0 if mode == 'deterministic' else cost > 0, 'Deterministic budgets are zero; real-model budgets must be positive')
    require(set(record['artifacts']) == set(ARTIFACTS), 'Missing preregistration evidence artifacts')
    for name, artifact in record['artifacts'].items():
        require(isinstance(artifact['path'], str), f'Missing artifact path: {name}')
        path = Path(artifact['path'])
        require(path.is_absolute() and path.is_file(), f'Artifact must be an existing absolute file: {name}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == artifact['sha256'], f'Artifact checksum mismatch: {name}')
    identity = read_json(record['artifacts']['runtime_identity']['path'])
    require(identity['product'] == 'openclaw' and identity['source_commit'] == target['source_commit'] and identity['version'] == target['version'], 'Runtime identity artifact disagrees with target pin')
    for arm in ['baseline', 'intervention']:
        effective = read_json(record['artifacts']['effective_config_' + arm]['path'])
        require(effective == contrast[arm + '_config'], f'Effective config artifact disagrees with declared {arm} contrast')
    binding = read_json(record['artifacts']['source_binding']['path'])
    require(binding['product'] == 'openclaw' and binding['source_commit'] == target['source_commit'] and binding['study_id'] == study['id'], 'Source binding artifact disagrees with study or target pin')
    require(binding['mechanism_supported'] is True and isinstance(binding['source_locations'], list) and binding['source_locations'] and all(isinstance(location, str) and location.strip() for location in binding['source_locations']), 'Source binding must identify supported mechanism locations at the pinned revision')
    if contrast['kind'] == 'native-config':
        require(binding['config_key'] == contrast['config_key'], 'Source binding does not support the selected config key')
    return dict(kind='preregistration-metadata-check', product='openclaw', study_id=study['id'],
                metadata_valid=True, execution_enabled=False, product_results_verified=False,
                limitation='Checks completeness and artifact bytes only; source interpretation, fixture validity, statistical adequacy and execution authorization require independent review.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    select = sub.add_parser('plan', help='Print a cross-dimensional architecture plan')
    select.add_argument('--wave', type=int, choices=[1, 2])
    select.add_argument('--study', action='append', default=[])
    template = sub.add_parser('template', help='Print an incomplete preregistration template')
    template.add_argument('--study', required=True)
    check = sub.add_parser('check-registration', help='Check metadata and hashes; no product execution')
    check.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        studies = load_studies()
        if args.command == 'plan':
            result = select_studies(studies, args.wave, args.study)
        elif args.command == 'template':
            result = registration_template(select_studies(studies, identifiers=[args.study])['studies'][0])
        else:
            result = validate_registration(read_json(args.path), studies, load_matrix())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'FAIL: {error}\n')


if __name__ == '__main__':
    main()
