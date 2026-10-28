#!/usr/bin/env python3
"""Execute every prescribed independent unit of one calibrated Codex family.

Mirrors the OpenClaw campaign's family runner contract: verify the pinned
installation on this disposable host, hash the reviewed controller sources,
run each scenario of the family for every prescribed independent unit, bind
each observation to the frozen Codex campaign plan and validate it with the
shared campaign audit rules. The npm package carries no git-commit metadata;
runtime identity binds version, tarball integrity and the release-tag
resolution recorded in the target pin, which stays independently re-checkable.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'evaluation' / 'runner'))

from campaign import load_plan, scenario_index, validate_result
from suite import require

DEFAULT_PLAN = ROOT / 'evaluation/campaigns/full-20261027-codex/plan.json'
CODEX_SOURCES = {
    'REL-01': ['evaluation/runner/rel01_cases.py',
               'evaluation/runner/codex_runtime.py',
               'evaluation/runner/codex_provider_fixture.py'],
    'REL-02': ['evaluation/runner/rel02_cases.py',
               'evaluation/runner/codex_runtime.py',
               'evaluation/runner/codex_provider_fixture.py',
               'evaluation/runner/codex_effect_ledger.py'],
}
CONTROLLER_MODULE = {'REL-01': 'rel01_cases', 'REL-02': 'rel02_cases'}
PIN = ROOT / 'evaluation/design/codex-target-pin.json'


def verify_installation(runtime_dir, pin):
    lock_path = runtime_dir / 'package-lock.json'
    require(lock_path.exists(), 'Runtime lockfile missing; install with npm before running')
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    entry = lock['packages'].get('node_modules/@openai/codex')
    require(entry is not None, 'Lockfile has no @openai/codex entry')
    require(entry.get('version') == pin['version'], 'Installed Codex version differs from the pin')
    require(entry.get('integrity') == pin['npm_integrity'],
            'Installed tarball integrity differs from the pinned npm integrity')
    binary = runtime_dir / 'node_modules' / '.bin' / 'codex'
    require(binary.exists(), 'codex binary missing from the shared runtime')
    version = subprocess.run([str(binary), '--version'], capture_output=True, text=True,
                             timeout=60).stdout.strip()
    require(version == f"codex-cli {pin['version']}", f'Unexpected codex --version: {version}')
    return dict(kind='codex-runtime-identity', version=pin['version'],
                npm_integrity=pin['npm_integrity'], release_tag=pin['release_tag'],
                source_commit=pin['source_commit'],
                commit_binding='release-tag resolution recorded in codex-target-pin.json; '
                               'npm package carries no commit metadata',
                version_output=version, binary=str(binary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--case', required=True, choices=sorted(CODEX_SOURCES))
    parser.add_argument('--runtime', type=Path, required=True,
                        help='Directory containing package-lock.json and node_modules/@openai/codex')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        pin = json.loads(PIN.read_text(encoding='utf-8'))
        require(plan['target']['version'] == pin['version']
                and plan['target']['source_commit'] == pin['source_commit'],
                'Plan target differs from the resolved pin')
        identity = verify_installation(args.runtime, pin)
        controller_hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                             for path in CODEX_SOURCES[args.case]}
        module_name = CONTROLLER_MODULE[args.case]
        controller = __import__(module_name)
        family_scenarios = {sid: case for sid, (case, _) in scenario_index(plan).items()
                            if case['id'] == args.case}
        require(set(family_scenarios) == set(controller.SCENARIOS),
                'Controller scenarios differ from the frozen family scope')
        run_id = os.environ.get('GITHUB_RUN_ID', 'local-development')
        controller_commit = os.environ.get('GITHUB_SHA', 'local')
        results = []
        args.output.mkdir(parents=True, exist_ok=True)
        for sid in sorted(family_scenarios):
            case, _ = scenario_index(plan)[sid]
            for unit in range(1, case['required_independent_units'] + 1):
                row = controller.run_scenario(sid, unit=unit, codex=str(identity['binary']))
                result = dict(row)
                result.update(plan_sha256=plan['plan_sha256'], run_id=run_id,
                              controller_commit=controller_commit,
                              full_campaign_coverage=True,
                              model_execution='deterministic-local-fixture',
                              evidence=[f'unit-{unit}/{sid}.json', 'execution.json'])
                validate_result(result, plan)
                results.append(result)
                unit_dir = args.output / f'unit-{unit}'
                unit_dir.mkdir(exist_ok=True)
                (unit_dir / f'{sid}.json').write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        execution = dict(kind='codex-campaign-family-run', case_id=args.case,
                         run_id=run_id, controller_commit=controller_commit,
                         runtime_identity=identity, controller_sha256=controller_hashes,
                         full_campaign_coverage=True, results_count=len(results),
                         harness_error=False)
        (args.output / 'execution.json').write_text(
            json.dumps(execution, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (args.output / 'results.json').write_text(
            json.dumps(results, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        total = sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())
        require(total <= 8 * 1024 * 1024, 'Evidence exceeds the 8 MiB hosted bound')
        print(json.dumps(dict(case=args.case, observations=len(results),
                              states={s: sum(1 for r in results if r['state'] == s)
                                      for s in sorted({r['state'] for r in results})},
                              evidence_bytes=total), ensure_ascii=False))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'FAIL: {error}\n')


if __name__ == '__main__':
    main()
