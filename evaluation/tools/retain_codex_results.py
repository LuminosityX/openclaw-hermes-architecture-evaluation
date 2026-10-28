#!/usr/bin/env python3
"""Retain compact formal Codex campaign evidence from a hosted artifact ZIP.

Reads the bounded artifact entirely in memory, verifies the execution binding
(run identity, runtime pin, controller hashes), re-validates every observation
against the frozen Codex campaign plan, rejects duplicated independent units,
checks the local campaign evidence budget and only then writes one compressed
record file. Raw runtimes, trajectories and dependency trees are never written
to the repository.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from campaign import load_plan, scenario_index, validate_result, records_from
from suite import require

DEFAULT_PLAN = ROOT / 'evaluation/campaigns/full-20261027-codex/plan.json'
CAMPAIGN_DIR = DEFAULT_PLAN.parent
EVIDENCE_BUDGET_BYTES = 4 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True,
                        help='Downloaded codex-campaign-<CASE> artifact ZIP')
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        results_dir = args.plan.parent / 'results'
        require(args.artifact.exists(), 'Artifact ZIP not found')
        raw = args.artifact.read_bytes()
        require(len(raw) <= 64 * 1024 * 1024, 'Artifact exceeds its declared bound')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            require('execution.json' in names, 'Artifact is missing execution.json')
            execution = json.loads(archive.read('execution.json').decode('utf-8'))
            require(execution.get('kind') == 'codex-campaign-family-run',
                    'Unexpected execution record kind')
            require(execution.get('full_campaign_coverage') is True,
                    'Development calibration cannot be retained as formal evidence')
            require(execution.get('harness_error') is False, 'Harness failure cannot be retained')
            identity = execution['runtime_identity']
            require(identity['version'] == plan['target']['version']
                    and identity['source_commit'] == plan['target']['source_commit']
                    and identity['npm_integrity'] == plan['target']['npm_integrity'],
                    'Artifact runtime identity differs from the frozen plan pin')
            family = execution['case_id']
            unit_files = sorted(n for n in names if n.startswith('unit-') and n.endswith('.json'))
            require(unit_files, 'Artifact has no unit observation files')
            records = []
            for name in unit_files:
                record = json.loads(archive.read(name).decode('utf-8'))
                validate_result(record, plan)
                records.append(record)
            expected = {sid for sid, (case, _) in scenario_index(plan).items()
                        if case['id'] == family}
            observed = {r['scenario_id'] for r in records}
            require(observed <= expected, 'Artifact contains scenarios outside the family')
        existing = records_from(results_dir)
        seen = {(r.get('scenario_id'), r.get('unit')) for r in existing}
        duplicates = [k for k in ((r['scenario_id'], r['unit']) for r in records) if k in seen]
        require(not duplicates, f'Duplicate independent units already retained: {duplicates}')
        run_id = execution['run_id']
        require(isinstance(run_id, str) and run_id.isdigit(),
                'Only hosted run identities (GitHub run IDs) can be retained as formal evidence')
        output = results_dir / f'{run_id}-codex-campaign-{family}.json.gz'
        require(not output.exists(), 'Record file for this run already exists')
        results_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, ensure_ascii=False, separators=(',', ':')).encode()
        output.write_bytes(gzip.compress(payload, 9))
        footprint = sum(p.stat().st_size for p in results_dir.glob('*'))
        require(footprint <= EVIDENCE_BUDGET_BYTES, 'Local campaign evidence budget exceeded')
        display = str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)
        print(json.dumps(dict(retained=display, family=family,
                              run_id=run_id, observations=len(records),
                              states=sorted({r['state'] for r in records}),
                              compressed_bytes=output.stat().st_size,
                              campaign_footprint_bytes=footprint), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f'FAIL: {error}\n')


if __name__ == '__main__':
    main()
