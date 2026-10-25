"""Read existing evidence only; never rerun a subject or revise original outcomes.

The active formal worker loaded the pre-amendment grader. This separate audit
checks its exact upstream count and immutable test assets before interpretation.
"""
import hashlib, json, re, time
from pathlib import Path
from runtime import R, save


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(require_complete=False):
    records = []
    for file in sorted((R / 'runs/formal').glob('*/*/result.json')):
        run = file.parent
        result = json.loads(file.read_text())
        inputs = json.loads((run / 'input-manifest.json').read_text())
        checks = {'model_policy_clean': not result.get('violations')}
        untouched = {}
        if result['task'] in ('W1', 'W2'):
            test = json.loads((run / 'upstream-tests.json').read_text())
            counts = re.findall(r'(\d+) passed', test['stdout'])
            checks['exactly_109_upstream_tests_passed'] = (
                test['exit_code'] == 0 and bool(counts) and int(counts[-1]) == 109
            )
            for name, digest in inputs.items():
                if name == 'run_tests.py' or name.startswith(('project/tests/', 'project/testing/')):
                    target = run / 'workspace' / name
                    untouched[name] = target.is_file() and sha(target) == digest
            checks['immutable_public_test_assets_match_input_hashes'] = bool(untouched) and all(untouched.values())
        fixture = R / 'fixtures' / f"{result['task']}-v{result['variant']}"
        expected = {str(p.relative_to(fixture)): sha(p) for p in fixture.rglob('*') if p.is_file()}
        checks['input_manifest_matches_frozen_case'] = inputs == expected
        records.append(dict(
            run=str(run.relative_to(R)), checks=checks, passed=all(checks.values()),
            upstream_public_asset_count=len(untouched), immutable_assets=untouched,
            source_result_sha256=sha(file), source_input_manifest_sha256=sha(run / 'input-manifest.json'),
        ))
    report = dict(
        at=time.time(), formal_completed=len(records), formal_planned=48,
        audit_passed=all(x['passed'] for x in records), records=records,
        scope='Posthoc evidence integrity audit, including the exact 109-test amendment. Original formal outcomes and cost records are preserved; no new model or product execution.',
    )
    save(R / 'results/formal-integrity-audit.json', report)
    print('FORMAL_INTEGRITY_AUDIT', len(records), report['audit_passed'], flush=True)
    if not report['audit_passed']:
        raise RuntimeError('Retain original results; inspect failed evidence checks before scoring')
    if require_complete and len(records) != 48:
        raise RuntimeError('Main formal batch is incomplete')
    return report


if __name__ == '__main__':
    main(require_complete=True)
