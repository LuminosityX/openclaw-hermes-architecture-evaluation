"""Populate only completed, independently checked measurements into the frozen scorer.

Unavailable and unfinished criteria stay absent; they are never coerced to parity.
Architecture explanations require separate review of the referenced native records.
"""
import hashlib, json, sys, time
from pathlib import Path
from runtime import R, save

D = Path('/root/output/oc-hermes-formal-design-20261024')
sys.path.insert(0, str(D))
from score_protocol import score


def main():
    protocol = json.loads((D / 'protocol_v1.json').read_text())
    semantic = hashlib.sha256(json.dumps(protocol, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()
    formal = json.loads((R / 'results/current-comparison.json').read_text())
    integrity = json.loads((R / 'results/formal-integrity-audit.json').read_text())
    native = json.loads((R / 'results/native-measured-differences.json').read_text())
    if native.get('measurement_profile') != 'matched-file-and-shell-tools':
        raise RuntimeError('Do not score the earlier unequal tool-scope Gateway profile')
    if formal['formal_completed'] != 48 or integrity['formal_completed'] != 48 or not integrity['audit_passed']:
        raise RuntimeError('Formal delivery/evidence gate not ready')
    observation_path = R / 'results/observations.json'
    if observation_path.exists():
        observations = json.loads(observation_path.read_text())
        if observations['protocol_semantic_sha256'] != semantic:
            raise RuntimeError('Retain earlier observations; protocol lock mismatch')
    else:
        observations = dict(protocol_version=protocol['version'], protocol_semantic_sha256=semantic,
                            peer_set=protocol['peer_set'], preflight_valid=True, metrics={},
                            gates={}, validity={}, eligibility={})
    if native['scale_instances'] != 12 or native['MCP_connections'] != 12:
        raise RuntimeError('Independent native timing units not complete')
    pairs = [dict(unit=f"{x['task']}-{x['variant']}-{x['repeat']}",
                  cluster=f"{x['task']}-{x['variant']}", case=x['task'],
                  oc=x['seconds_oc'], hermes=x['seconds_hermes']) for x in formal['pairs']]
    observations['metrics']['D04a'] = dict(pairs=pairs, evidence=[
        'results/current-comparison.json', 'results/formal-integrity-audit.json',
        'results/formal-task-results.json'])
    for criterion, native_key in [('D04b', 'gateway_first_text'), ('D04c', 'MCP_tool_critical_path')]:
        observations['metrics'][criterion] = dict(
            pairs=native['quantitative'][native_key]['pairs'],
            evidence=['results/native-measured-differences.json',
                      native['source_scale_file'] if criterion == 'D04b' else 'results/native-suite.json'])
    quality = all(x['passed'] for x in formal['cases']) and all(x['both_accepted'] for x in formal['pairs'])
    dimension = next(x for x in protocol['dimensions'] if x['id'] == 'D04')
    observations['eligibility']['D04'] = {
        key: dict(status='pass' if quality else 'fail', evidence=[
            'results/formal-task-results.json', 'results/formal-integrity-audit.json'])
        for key in dimension['eligibility_gates']}
    # D06 uses independently observed native capacity and resource contracts.
    replicas_path = R / 'results/replicas.json'
    capacity_path = R / 'results/capacity-guards.json'
    security_path = R / 'results/security-boundaries.json'
    if all(path.exists() for path in [replicas_path, capacity_path, security_path]):
        replicas = json.loads(replicas_path.read_text())
        capacity = json.loads(capacity_path.read_text())
        security = [x for x in json.loads(security_path.read_text()) if x['mode'] == 'readwrite']
        mechanism = json.loads((R / 'results/native-suite.json').read_text())
        if len(replicas) == len(capacity) == len(security) == 6:
            def paired(records, unit, identity='unit'):
                rows = {x['family']: x for x in records if x[identity] == unit}
                if set(rows) != {'openclaw', 'hermes'}:
                    raise RuntimeError('Missing fresh paired functional unit')
                return rows
            node_pairs = []
            cap_pairs = []
            for unit in range(1, 4):
                fs = paired(replicas, unit)
                for case in ['node_placement', 'node_restart', 'node_capacity']:
                    values = {}
                    for family, row in fs.items():
                        batches = {x['copies']: x for x in row['measurements']}
                        if case == 'node_placement':
                            value = (row['full_nodes'] == 2 and row['node_storage_distinct']
                                     and all(x['correct'] for x in row['warmup'])
                                     and all(x['correct'] == x['total'] for x in batches.values())
                                     and {x['node'] for x in batches[2]['tasks']} == {0, 1})
                        elif case == 'node_restart':
                            value = (row['other_node_healthy_during_outage'] and row['restarted_same_node_ready']
                                     and row['same_node_prior_history_retained'])
                        else:
                            value = (all(x['correct'] == x['total'] for x in batches.values())
                                     and batches[2]['throughput'] > batches[1]['throughput'])
                        values[family] = bool(value)
                    node_pairs.append(dict(unit=f'{case}-u{unit}', case=case,
                                           oc=values['openclaw'], hermes=values['hermes']))
                cs, ss = paired(capacity, unit), paired(security, unit)
                for case in ['backpressure', 'resource_caps', 'sustained_load', 'R01', 'R02']:
                    values = {}
                    for family in ['openclaw', 'hermes']:
                        if case == 'backpressure':
                            value = cs[family]['backpressure_held']
                        elif case == 'sustained_load':
                            value = cs[family]['sustained_passed']
                        elif case == 'resource_caps':
                            limits = ss[family]['observations'].get('effective_container_limits', {})
                            value = (ss[family].get('valid') is True and limits.get('memory.max') == '536870912'
                                     and limits.get('pids.max') == '128' and limits.get('cpu.max') == '100000 100000')
                        else:
                            kind = 'retry-429-r1' if case == 'R01' else 'retry-503-r1'
                            rows = [x for x in mechanism if x['kind'] == kind
                                    and x['family'] == family and x['independent_unit'] == unit]
                            if len(rows) != 1:
                                raise RuntimeError('Independent provider-backoff unit missing')
                            wait = rows[0].get('actual_retry_wait_seconds')
                            value = wait is not None and wait >= 1.9
                        values[family] = bool(value)
                    cap_pairs.append(dict(unit=f'{case}-u{unit}', case=case,
                                          oc=values['openclaw'], hermes=values['hermes']))
            observations['metrics']['D06a'] = dict(
                pairs=native['quantitative']['scale_efficiency']['pairs'], lower_is_better=False,
                evidence=['results/native-measured-differences.json', native['source_scale_file']])
            observations['metrics']['D06b'] = dict(pairs=node_pairs, evidence=['results/replicas.json'],
                scope='Same-host whole Gateway replicas and explicit node affinity; no native scheduler or automatic cross-node session migration is claimed.')
            observations['metrics']['D06c'] = dict(pairs=cap_pairs, evidence=[
                'results/capacity-guards.json', 'results/security-boundaries.json', 'results/native-suite.json'],
                scope='Native run admission/backpressure, bounded 20-task stability run, per-tool-container kernel CPU/RAM/PID caps and provider-declared backoff. Container caps are not a Gateway process RAM cap; 503 recovery itself remains separate from wait compliance.')
            scale = json.loads((R / native['source_scale_file']).read_text())
            persistence = []
            for row in scale:
                file = R / 'runs-scale-matched-tools' / f"u{row['independent_unit']}" / row['family'] / 'native-persistence-inventory.json'
                inventory = json.loads(file.read_text())
                tables = ['transcript_events'] if row['family'] == 'openclaw' else ['messages', 'session_admissions']
                persistence.append(all(any(hit['table'] == table and hit['count'] >= 63
                                           for db in inventory for hit in db.get('token_hits', [])) for table in tables))
            aligned = (all(x.get('configured_concurrency_cap') == 16 for x in scale) and all(persistence)
                       and all(x['native_concurrency_limit_held'] for x in capacity))
            d6 = next(x for x in protocol['dimensions'] if x['id'] == 'D06')
            observations['validity']['D06'] = {key: dict(
                status='pass' if aligned else 'fail', evidence=[native['source_scale_file'],
                    'results/capacity-guards.json', 'results/replicas.json',
                    'evidence/gateway-tool-scope-adjudication.json']) for key in d6['validity_gates']}
            terminal = json.loads((R / 'results/native-scale-terminal-audit.json').read_text())
            complete = terminal['passed'] and terminal['requests'] == 756
            observations['gates']['D06'] = {key: dict(
                oc='pass' if complete and all(x['passed'] for x in replicas if x['family'] == 'openclaw') else 'fail',
                hermes='pass' if complete and all(x['passed'] for x in replicas if x['family'] == 'hermes') else 'fail',
                evidence=['results/native-scale-terminal-audit.json', 'results/replicas.json'])
                for key in d6['critical_gates']}
    observations['last_updated'] = time.time()
    observations.pop('profile_reassessment_pending', None)
    observations['scope'] = ('Only populated completed criteria are eligible. Two-product relative grading; '
                             'no five-family ranking and no coercion of unknown outcomes to 中. '
                             'D04 covers the frozen E01 tasks and controlled native timing workloads.')
    save(observation_path, observations)
    scores = score(protocol, observations)
    scores['experiment_complete'] = False
    scores['architecture_explanations_reviewed'] = False
    save(R / 'results/partial-grades.json', scores)
    files = [observation_path, D / 'protocol_v1.json', D / 'score_protocol.py',
             R / 'results/current-comparison.json', R / 'results/formal-integrity-audit.json',
             R / 'results/native-measured-differences.json', R / native['source_scale_file'],
             R / 'results/native-suite.json']
    def evidence_references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'evidence':
                    for item in child if isinstance(child, list) else [child]:
                        if isinstance(item, str):
                            file = R / item
                            if file.is_file() and file.resolve().is_relative_to(R):
                                yield file
                else:
                    yield from evidence_references(child)
        elif isinstance(value, list):
            for child in value:
                yield from evidence_references(child)
    files.extend(evidence_references(observations))
    save(R / 'results/partial-grades-evidence-hashes.json', {
        str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in files})
    print('EVIDENCE_GRADED_DIMENSIONS', [(d['id'], d['grades']) for d in scores['dimensions']
                                         if d['status'] in ['graded', 'critical_gate_decision']], flush=True)


if __name__ == '__main__':
    main()
