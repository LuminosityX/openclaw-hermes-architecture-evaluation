#!/usr/bin/env python3
"""Build the frozen Codex evaluation matrix from the OpenClaw design inventory.

Reads the authoritative OpenClaw matrix (structure, coverage tags, metrics,
phases, controls, evidence and scenario counts), applies the reviewed per-family
translation in design/codex-matrix-translation.json and the resolved target pin,
then validates the result with the Codex product profile. This tool only emits
a plan document; it never executes product code or contacts any provider.
"""

import argparse
import json
from pathlib import Path

from suite import require, validate
from campaign import freeze

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MATRIX = ROOT / 'evaluation/design/evaluation-matrix.json'
TRANSLATION = ROOT / 'evaluation/design/codex-matrix-translation.json'
PIN = ROOT / 'evaluation/design/codex-target-pin.json'
OUTPUT = ROOT / 'evaluation/design/codex-matrix.json'
DEFAULT_CAMPAIGN = ROOT / 'evaluation/campaigns/full-20261027-codex'


def build(translation, pin):
    source = json.loads(SOURCE_MATRIX.read_text(encoding='utf-8'))
    dimensions = []
    for dimension in source['dimensions']:
        experiments = []
        for case in dimension['experiments']:
            override = translation.get(case['id'])
            require(override is not None, f'Missing Codex translation entry: {case["id"]}')
            merged = dict(case)
            for field in ('title', 'mechanism', 'intervention', 'oracle', 'scenarios'):
                if field in override:
                    merged[field] = override[field]
                    if field == 'scenarios':
                        require(len(override['scenarios']) == len(case['scenarios']),
                                f'Scenario count changed: {case["id"]}')
            merged['product'] = 'codex'
            merged.pop('legacy_ids', None)
            merged['openclaw_case_ids'] = [case['id']]
            experiments.append(merged)
        dimensions.append(dict(dimension, experiments=experiments))
    target = {key: pin[key] for key in (
        'product', 'version', 'source_commit', 'selection_policy', 'release_tag',
        'release_url', 'release_published_at', 'checked_at_utc', 'npm_integrity', 'npm_tarball')}
    target['node_engine'] = pin['node_engine']
    target['pin_policy'] = pin['pin_policy']
    return dict(
        schema_version=2,
        name='Codex task framework evaluation',
        status='planned-not-executed',
        scope=dict(products=['codex'], comparison_enabled=False,
                   excluded_products=['openclaw', 'hermes'],
                   dimension_policy=source['scope']['dimension_policy']),
        target=target,
        historical_reference=dict(
            openclaw_campaign='evaluation/campaigns/full-20261026-batched',
            openclaw_matrix='evaluation/design/evaluation-matrix.json',
            change_policy='The six-dimension structure, family inventory and scenario counts originate from the completed OpenClaw campaign in this repository. Codex families record openclaw_case_ids for provenance; no cross-product grade is defined by this matrix.'),
        execution=source['execution'],
        reporting=source['reporting'],
        dimensions=dimensions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir', type=Path, default=DEFAULT_CAMPAIGN,
                        help='Also freeze the Codex campaign plan into this new directory')
    parser.add_argument('--no-plan', action='store_true', help='Only write the matrix, do not freeze a plan')
    args = parser.parse_args()
    try:
        translation = json.loads(TRANSLATION.read_text(encoding='utf-8'))
        pin = json.loads(PIN.read_text(encoding='utf-8'))
        matrix = build(translation, pin)
        OUTPUT.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        validate(matrix)
        summary = dict(matrix=str(OUTPUT), product='codex', version=matrix['target']['version'],
                       families=sum(len(d['experiments']) for d in matrix['dimensions']),
                       scenarios=sum(len(e['scenarios']) for d in matrix['dimensions'] for e in d['experiments']))
        if not args.no_plan:
            plan_path = args.campaign_dir / 'plan.json'
            require(not plan_path.exists(), 'Do not overwrite a frozen campaign plan')
            plan = freeze(matrix, campaign_id='full-20261027-codex')
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            from campaign import load_plan
            load_plan(plan_path)
            summary['plan'] = str(plan_path)
            summary['plan_sha256'] = plan['plan_sha256']
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'FAIL: {error}\n')


if __name__ == '__main__':
    main()
