"""Regression checks for scope, plan selection and evidence classification."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from suite import DIMENSIONS, PHASES, ROOT, load_matrix, render_catalogue, select_plan, validate


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.matrix = load_matrix()

    def test_all_six_dimensions_and_openclaw_only(self):
        plan = select_plan(self.matrix, phase='all')
        self.assertEqual({c['dimension'] for c in plan['cases']}, set(DIMENSIONS))
        self.assertEqual({c['product'] for c in plan['cases']}, {'openclaw'})
        self.assertFalse(plan['execution_enabled'])
        self.assertEqual(plan['product_run_count'], 0)

    def test_default_plan_excludes_real_usage(self):
        self.assertEqual({c['billing'] for c in select_plan(self.matrix)['cases']}, {PHASES['deterministic']})

    def test_dimension_and_case_filter_intersect(self):
        plan = select_plan(self.matrix, dimensions=['security'], cases=['SEC-08'])
        self.assertEqual([c['id'] for c in plan['cases']], ['SEC-08'])
        with self.assertRaisesRegex(ValueError, 'No cases'):
            select_plan(self.matrix, dimensions=['security'], cases=['REL-01'])

    def test_real_task_capability_requires_explicit_phase(self):
        with self.assertRaisesRegex(ValueError, 'real-usage'):
            select_plan(self.matrix, cases=['PERF-09'])
        self.assertEqual(len(select_plan(self.matrix, cases=['PERF-09'], phase='real-model')['cases']), 1)

    def test_unknown_selectors_fail(self):
        for kwargs in [dict(dimensions=['compatibility']), dict(cases=['D01-01']), dict(phase='paid')]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                select_plan(self.matrix, **kwargs)

    def test_cross_product_scope_and_cases_rejected(self):
        self.matrix['scope']['products'].append('hermes')
        with self.assertRaisesRegex(ValueError, 'OpenClaw only'):
            validate(self.matrix)
        self.matrix = load_matrix()
        self.matrix['dimensions'][0]['experiments'][0]['product'] = 'hermes'
        with self.assertRaisesRegex(ValueError, 'Non-OpenClaw'):
            validate(self.matrix)

    def test_seventh_or_missing_dimension_rejected(self):
        self.matrix['dimensions'].append(copy.deepcopy(self.matrix['dimensions'][0]))
        with self.assertRaisesRegex(ValueError, 'Exactly six'):
            validate(self.matrix)
        self.matrix['dimensions'] = self.matrix['dimensions'][:5]
        with self.assertRaisesRegex(ValueError, 'Exactly six'):
            validate(self.matrix)

    def test_privacy_and_hooks_cannot_silently_disappear(self):
        for dimension, tag in [('security', 'privacy'), ('extensibility', 'hooks')]:
            matrix = load_matrix()
            d = next(d for d in matrix['dimensions'] if d['id'] == dimension)
            for case in d['experiments']:
                case['coverage'] = [t for t in case['coverage'] if t != tag]
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, 'Missing case coverage'):
                validate(matrix)

    def test_resource_counter_coverage_and_units(self):
        d = next(d for d in self.matrix['dimensions'] if d['id'] == 'resources_cost')
        d['required_metrics'] = [m for m in d['required_metrics'] if m['id'] != 'disk_inodes']
        with self.assertRaisesRegex(ValueError, 'Required metrics missing'):
            validate(self.matrix)

    def test_latency_and_cpu_units_cannot_change_to_bytes(self):
        for dimension, metric in [('performance', 'completion_latency_ms'), ('resources_cost', 'cpu_user_seconds')]:
            matrix = load_matrix()
            d = next(d for d in matrix['dimensions'] if d['id'] == dimension)
            next(m for m in d['required_metrics'] if m['id'] == metric)['unit'] = 'bytes'
            with self.subTest(metric=metric), self.assertRaisesRegex(ValueError, 'Incorrect unit'):
                validate(matrix)

    def test_model_dependent_injection_requires_real_usage(self):
        d = next(d for d in self.matrix['dimensions'] if d['id'] == 'security')
        next(e for e in d['experiments'] if 'prompt_injection' in e['coverage'])['billing'] = PHASES['deterministic']
        with self.assertRaisesRegex(ValueError, 'real usage'):
            validate(self.matrix)

    def test_no_product_results_or_execution_claims(self):
        for field in ['enabled', 'allow_paid_model_calls', 'allow_dependency_downloads']:
            matrix = load_matrix()
            matrix['execution'][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'disabled'):
                validate(matrix)
        self.matrix['dimensions'][0]['experiments'][0]['passed'] = True
        with self.assertRaisesRegex(ValueError, 'product results'):
            validate(self.matrix)

    def test_duplicate_case_and_lost_historical_mapping_rejected(self):
        case = self.matrix['dimensions'][0]['experiments'][0]
        self.matrix['dimensions'][0]['experiments'].append(copy.deepcopy(case))
        with self.assertRaisesRegex(ValueError, 'duplicate case'):
            validate(self.matrix)
        self.matrix['dimensions'][0]['experiments'].pop()
        case['legacy_ids'] = []
        with self.assertRaisesRegex(ValueError, 'historical mapping'):
            validate(self.matrix)

    def test_real_usage_not_classified_as_deterministic(self):
        d = next(d for d in self.matrix['dimensions'] if d['id'] == 'performance')
        next(e for e in d['experiments'] if 'task_capability' in e['coverage'])['billing'] = PHASES['deterministic']
        with self.assertRaisesRegex(ValueError, 'real usage'):
            validate(self.matrix)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'matrix.json'
            path.write_text('{"schema_version": 2, "schema_version": 2}')
            with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                load_matrix(path)

    def test_catalogue_matches_source(self):
        self.assertEqual(render_catalogue(self.matrix), (ROOT / 'evaluation/experiment-catalogue.md').read_text())

    def test_cli_json_plan_and_rejected_selector(self):
        cli = [sys.executable, str(ROOT / 'evaluation/tools/suite.py'), 'plan']
        result = subprocess.run(cli + ['--dimension', 'observability'], capture_output=True, text=True, check=True)
        self.assertEqual({c['dimension'] for c in json.loads(result.stdout)['cases']}, {'observability'})
        result = subprocess.run(cli + ['--case', 'NOPE'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unknown case', result.stderr)


if __name__ == '__main__':
    unittest.main()
