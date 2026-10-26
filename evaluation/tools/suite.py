#!/usr/bin/env python3
"""Validate and select OpenClaw test plans without executing product code."""

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / 'evaluation/design/evaluation-matrix.json'
DIMENSIONS = {
    'reliability': ('REL', {'durability', 'side_effects', 'recovery', 'cancellation', 'dependency_failure', 'provider_failure'}),
    'security': ('SEC', {'isolation', 'authorization', 'privacy', 'prompt_injection', 'network', 'gateway_auth', 'supply_chain'}),
    'performance': ('PERF', {'task_capability', 'long_context', 'latency', 'concurrency', 'overload', 'sustained_load'}),
    'resources_cost': ('COST', {'cpu', 'memory', 'disk', 'io', 'network', 'processes', 'tokens', 'billing', 'budgets'}),
    'extensibility': ('EXT', {'plugin_lifecycle', 'public_interfaces', 'hooks', 'composition', 'protocols'}),
    'observability': ('OBS', {'authorization_trace', 'collector_durability', 'diagnosis', 'export', 'trajectory', 'accessibility'}),
}
PHASES = {'deterministic': 'deterministic-local-fixture', 'real-model': 'real-usage-required'}
RESOURCE_METRICS = {
    'cpu_user_seconds', 'cpu_system_seconds', 'cpu_throttled_seconds',
    'memory_rss_peak_bytes', 'memory_pss_bytes', 'cgroup_memory_peak_bytes', 'memory_swap_bytes',
    'disk_allocated_bytes', 'disk_apparent_bytes', 'disk_inodes', 'disk_read_bytes',
    'disk_write_bytes', 'disk_io_wait_ms', 'network_sent_bytes', 'network_received_bytes',
    'process_count', 'thread_count', 'open_file_descriptors', 'residual_disk_bytes',
    'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens',
    'provider_reported_cost_usd', 'calculated_cost_usd', 'cost_per_accepted_task_usd',
}
CORE_METRICS = {
    'reliability': {'lost_acknowledged_tasks', 'duplicate_effects', 'recovery_latency_ms', 'manual_interventions'},
    'security': {'unauthorized_effects', 'canary_disclosures', 'unauthorized_network_requests', 'authorized_control_success_rate'},
    'performance': {'accepted_tasks', 'attempted_tasks', 'task_success_rate', 'completion_latency_ms', 'first_output_latency_ms', 'queue_wait_ms', 'offered_requests_per_s', 'correct_goodput_per_s', 'max_sustainable_concurrency'},
    'resources_cost': RESOURCE_METRICS,
    'extensibility': {'public_interface_cases_passed', 'core_files_modified', 'hook_ordering_violations', 'hook_duplicate_invocations', 'extension_cleanup_residuals'},
    'observability': {'trace_event_coverage', 'linked_tool_call_rate', 'export_missing_events', 'diagnosis_accuracy', 'diagnosis_time_ms', 'observer_overhead_ratio'},
}
SPECIAL_UNITS = {
    'authorized_control_success_rate': 'ratio', 'task_success_rate': 'ratio',
    'offered_requests_per_s': 'requests/s', 'correct_goodput_per_s': 'tasks/s',
    'cost_per_accepted_task_usd': 'USD/task', 'trace_event_coverage': 'ratio',
    'linked_tool_call_rate': 'ratio', 'diagnosis_accuracy': 'ratio', 'observer_overhead_ratio': 'ratio',
}


def expected_unit(identifier):
    if identifier in SPECIAL_UNITS:
        return SPECIAL_UNITS[identifier]
    for suffix, unit in [('_seconds', 's'), ('_ms', 'ms'), ('_bytes', 'bytes'), ('_tokens', 'tokens'), ('_usd', 'USD')]:
        if identifier.endswith(suffix):
            return unit
    return 'count'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def load_matrix(path=MATRIX):
    matrix = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    validate(matrix)
    return matrix


def validate(matrix):
    require(matrix['schema_version'] == 2, 'Unsupported evaluation schema')
    require(matrix['status'] == 'planned-not-executed', 'This matrix records a plan, not product results')
    require(matrix['scope']['products'] == ['openclaw'], 'Current evaluation must target OpenClaw only')
    require(matrix['scope']['comparison_enabled'] is False, 'Cross-product comparison is out of scope')
    require(matrix['target']['product'] == 'openclaw', 'Target must be OpenClaw')
    reference = matrix['historical_reference']
    require(reference['branch'] == 'archive/v6', 'Historical branch must remain archive/v6')
    require(reference['commit'] == 'a33644efc9490ff771d058ebf047f08550e4ccb3', 'Historical reference changed')
    for field in ['enabled', 'allow_dependency_downloads', 'allow_paid_model_calls']:
        require(matrix['execution'][field] is False, f'Product execution is disabled: {field}')
    require(type(matrix['execution']['run_count']) is int and matrix['execution']['run_count'] == 0, 'No product runs are recorded by this plan')
    require(len(matrix['execution']['required_before_execution']) >= 6, 'Execution prerequisites missing')
    dimensions = matrix['dimensions']
    require(len(dimensions) == 6 and {d['id'] for d in dimensions} == set(DIMENSIONS), 'Exactly six current dimensions are required')
    require(matrix['reporting']['outcome_axes'] == [d['id'] for d in dimensions], 'Reporting axes differ from the six dimensions')
    require(set(matrix['reporting']['result_labels']) == {'pass', 'fail', 'unsupported', 'not-run', 'inconclusive', 'harness-error'}, 'Missing result labels')
    seen, legacy_seen, metric_seen = set(), set(), set()
    for d in dimensions:
        prefix, coverage = DIMENSIONS[d['id']]
        require(d['prefix'] == prefix, f'Invalid prefix for {d["id"]}')
        require(set(d['required_coverage']) == coverage, f'Required coverage changed: {d["id"]}')
        require(d['experiments'], f'Empty dimension: {d["id"]}')
        actual_coverage = set()
        for metric in d['required_metrics']:
            require(metric['id'] not in metric_seen, f'Duplicate metric: {metric["id"]}')
            metric_seen.add(metric['id'])
            require(re.fullmatch(r'[a-z][a-z0-9_]+', metric['id']), 'Invalid metric identifier')
            require(metric['unit'] in {'count', 'ms', 's', 'ratio', 'requests/s', 'tasks/s', 'bytes', 'tokens', 'USD', 'USD/task'}, 'Missing metric unit')
            if metric['id'] in CORE_METRICS[d['id']]:
                require(metric['unit'] == expected_unit(metric['id']), f'Incorrect unit: {metric["id"]}')
            require(metric['aggregation'] in {'sum', 'p95', 'p95_p99', 'ratio', 'mean', 'max', 'sample_series', 'after_cleanup'}, 'Missing metric aggregation')
        require(CORE_METRICS[d['id']] <= {m['id'] for m in d['required_metrics']}, f'Required metrics missing: {d["id"]}')
        for e in d['experiments']:
            identifier = e['id']
            require(identifier not in seen and re.fullmatch(prefix + r'-[0-9]{2}', identifier), f'Invalid or duplicate case ID: {identifier}')
            seen.add(identifier)
            require(e['product'] == 'openclaw', f'Non-OpenClaw case: {identifier}')
            require(e['status'] == 'planned' and e['adapter_status'] == 'not-implemented', f'Unverified implementation claim: {identifier}')
            require(e['billing'] in PHASES.values(), f'Unknown phase: {identifier}')
            for field in ['title', 'mechanism', 'intervention', 'oracle']:
                require(isinstance(e[field], str) and len(e[field]) >= 12, f'Missing {field}: {identifier}')
            for field in ['scenarios', 'metrics', 'controls', 'evidence']:
                require(isinstance(e[field], list) and len(e[field]) >= 3 and all(isinstance(x, str) and x.strip() for x in e[field]), f'Missing {field}: {identifier}')
            require(set(e['coverage']) <= coverage, f'Unknown coverage tag: {identifier}')
            actual_coverage.update(e['coverage'])
            if set(e['coverage']) & {'task_capability', 'long_context', 'billing', 'prompt_injection'}:
                require(e['billing'] == PHASES['real-model'], f'Capability/actual billing requires real usage: {identifier}')
            require(not {'score', 'winner', 'result', 'passed'} & set(e), f'Proposed test contains product results: {identifier}')
            for legacy in e['legacy_ids']:
                require(legacy not in legacy_seen, f'Duplicate historical mapping: {legacy}')
                legacy_seen.add(legacy)
        require(coverage <= actual_coverage, f'Missing case coverage: {d["id"]}: {sorted(coverage-actual_coverage)}')
    expected_legacy = {f'D{d:02}-{e:02}' for d in range(1, 12) for e in range(1, 7 if d == 11 else 5)}
    require(legacy_seen == expected_legacy, 'Every previous experiment must retain exactly one historical mapping')
    return matrix


def render_catalogue(matrix):
    lines = ['# OpenClaw experiment catalogue', '',
             'Status: planned, not executed. The [matrix](design/evaluation-matrix.json) is authoritative. Every case targets OpenClaw; unsupported capabilities require explicit evidence. No product adapter is implemented by this catalogue.', '']
    for d in matrix['dimensions']:
        lines += [f"## {d['name']} ({d['label_zh']})", '', d['scope'], '']
        for e in d['experiments']:
            lines += [f"### {e['id']} — {e['title']}", '',
                      f"Coverage tags: {', '.join(e['coverage']) or 'additional boundary coverage'}.", '',
                      f"Phase: `{e['billing']}`. Adapter: `{e['adapter_status']}`.", '',
                      'Architecture mechanism: ' + e['mechanism'], '',
                      'Controlled change: ' + e['intervention'], '',
                      'Scenarios: ' + '; '.join(e['scenarios']) + '.', '',
                      'Pass/failure evidence: ' + e['oracle'], '',
                      'Measurements: ' + ', '.join(e['metrics']) + '.', '']
    return '\n'.join(lines)


def select_plan(matrix, dimensions=(), cases=(), phase='deterministic'):
    validate(matrix)
    require(phase in {*PHASES, 'all'}, f'Unknown phase: {phase}')
    require(set(dimensions) <= set(DIMENSIONS), 'Unknown dimension selector')
    all_ids = {e['id'] for d in matrix['dimensions'] for e in d['experiments']}
    require(set(cases) <= all_ids, f'Unknown case selector: {sorted(set(cases)-all_ids)}')
    selected = [dict(e, dimension=d['id']) for d in matrix['dimensions'] for e in d['experiments']
                if (not dimensions or d['id'] in dimensions)
                and (not cases or e['id'] in cases)
                and (phase == 'all' or e['billing'] == PHASES[phase])]
    require(selected, 'No cases match these selectors and phase; real-usage cases require --phase real-model or all')
    return dict(schema_version=2, kind='plan-only', product='openclaw', phase=phase,
                execution_enabled=False, product_run_count=0, target=matrix['target'],
                prerequisites=matrix['execution']['required_before_execution'], cases=selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list', help='List all six dimensions and case counts')
    sub.add_parser('catalogue', help='Print the generated Markdown catalogue')
    plan = sub.add_parser('plan', help='Print a plan; never run OpenClaw or contact providers')
    plan.add_argument('--dimension', action='append', default=[], choices=list(DIMENSIONS))
    plan.add_argument('--case', action='append', default=[])
    plan.add_argument('--phase', choices=[*PHASES, 'all'], default='deterministic')
    args = parser.parse_args(argv)
    try:
        matrix = load_matrix()
        if args.command == 'list':
            for d in matrix['dimensions']:
                real = sum(e['billing'] == PHASES['real-model'] for e in d['experiments'])
                print(f"{d['id']}: {len(d['experiments'])} cases ({real} real-usage); {d['label_zh']}")
        elif args.command == 'catalogue':
            print(render_catalogue(matrix), end='')
        else:
            print(json.dumps(select_plan(matrix, args.dimension, args.case, args.phase), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'FAIL: {error}\n')


if __name__ == '__main__':
    main()
