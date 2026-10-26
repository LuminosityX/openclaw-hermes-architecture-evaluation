"""Synthetic preregistrations test guardrails; no product evidence is generated."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from architecture import ARTIFACTS, BUDGETS, load_studies, registration_template, select_studies, validate_registration, validate_studies
from suite import ROOT, load_matrix


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.matrix = load_matrix()
        self.plan = load_studies()
        self.study = self.plan['studies'][0]

    def test_first_wave_order_and_no_execution(self):
        selected = select_studies(self.plan, wave=1)
        self.assertEqual([s['id'] for s in selected['studies']], ['ARC-01', 'ARC-03', 'ARC-02'])
        self.assertFalse(selected['execution_enabled'])
        self.assertEqual(selected['product_run_count'], 0)

    def test_unknown_or_conflicting_selectors(self):
        for kwargs in [dict(identifiers=['NOPE']), dict(wave=1, identifiers=['ARC-05']), dict(wave=9)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                select_studies(self.plan, **kwargs)

    def test_each_study_addresses_six_axes_and_both_sides(self):
        del self.study['axes']['security']
        with self.assertRaisesRegex(ValueError, 'six axes'):
            validate_studies(self.plan, self.matrix)

    def test_cost_hypothesis_cannot_be_omitted(self):
        for axis in self.study['axes'].values():
            if axis['role'] == 'cost-hypothesis':
                axis['role'] = 'guardrail'
        with self.assertRaisesRegex(ValueError, 'both benefit and cost'):
            validate_studies(self.plan, self.matrix)

    def test_documented_intent_needs_source(self):
        self.study['source']['url'] = None
        with self.assertRaisesRegex(ValueError, 'needs a source'):
            validate_studies(self.plan, self.matrix)

    def test_unsupported_metric_and_case_mapping_fail(self):
        self.study['axes']['performance']['metrics'].append('invented_metric')
        with self.assertRaisesRegex(ValueError, 'Unknown metric'):
            validate_studies(self.plan, self.matrix)
        self.study['axes']['performance']['metrics'].pop()
        self.study['case_ids'].append('HERMES-01')
        with self.assertRaisesRegex(ValueError, 'case mapping'):
            validate_studies(self.plan, self.matrix)

    def test_plan_cannot_claim_measured_results(self):
        self.study['tradeoff_proven'] = True
        with self.assertRaisesRegex(ValueError, 'product claims'):
            validate_studies(self.plan, self.matrix)

    def test_empty_template_is_not_ready(self):
        with self.assertRaisesRegex(ValueError, 'Pin the installed'):
            validate_registration(registration_template(self.study), self.plan, self.matrix)

    def complete_record(self, directory, study=None):
        study = study or self.study
        record = registration_template(study)
        record.update(execution_mode='deterministic', target=dict(version='synthetic-fixture', source_commit='a'*40),
                      independent_units_per_arm=4, paired_blocks=4,
                      sample_size_rationale='Synthetic validator fixture, not a justified product sample size.',
                      estimand='Synthetic paired difference', uncertainty_method='Synthetic declared method',
                      allocation_and_reset='Synthetic randomized blocks and fresh state',
                      workload_revision='synthetic-fixture-v1', reversal_workload_revision='synthetic-reversal-v1',
                      stop_rules='Synthetic validation-only stopping rule')
        key = record['contrast']['config_key']
        record['contrast'].update(baseline_config={key:1}, intervention_config={key:4}, unresolved_confounders=[])
        for thresholds in record['thresholds'].values():
            for threshold in thresholds:
                threshold['minimum_meaningful_difference'] = 0.1
        record['budgets'] = {**{name:1 for name in BUDGETS}, 'model_cost_usd':0}
        for name in ARTIFACTS:
            if name == 'runtime_identity':
                data = dict(product='openclaw', **record['target'])
            elif name == 'source_binding':
                data = dict(product='openclaw', source_commit='a'*40, study_id=study['id'],
                            mechanism_supported=True, source_locations=['synthetic/source.ts:1'], config_key=key)
            elif name.startswith('effective_config_'):
                data = record['contrast'][name.removeprefix('effective_config_') + '_config']
            else:
                data = dict(kind='synthetic-validator-fixture', name=name)
            path = Path(directory) / (name+'.json')
            path.write_text(json.dumps(data))
            record['artifacts'][name] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        return record

    def test_complete_metadata_is_not_execution_or_verified_product_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory)
            result = validate_registration(record, self.plan, self.matrix)
            self.assertTrue(result['metadata_valid'])
            self.assertFalse(result['execution_enabled'])
            self.assertFalse(result['product_results_verified'])

    def test_confounded_native_contrast_and_wrong_field_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory)
            record['contrast']['unresolved_confounders'] = ['different model']
            with self.assertRaisesRegex(ValueError, 'confounders block'):
                validate_registration(record, self.plan, self.matrix)
            record['contrast']['unresolved_confounders'] = []
            record['contrast']['baseline_config'] = {'unrelated.setting':1}
            record['contrast']['intervention_config'] = {'unrelated.setting':4}
            with self.assertRaisesRegex(ValueError, 'declared flattened'):
                validate_registration(record, self.plan, self.matrix)

    def test_two_native_config_changes_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory)
            record['contrast']['baseline_config']['another'] = 1
            record['contrast']['intervention_config']['another'] = 2
            with self.assertRaisesRegex(ValueError, 'declared flattened'):
                validate_registration(record, self.plan, self.matrix)

    def test_missing_or_nonfinite_margins_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in [None, True, -1, float('inf')]:
                record = self.complete_record(directory)
                record['thresholds']['reliability'][0]['minimum_meaningful_difference'] = value
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'meaningful-difference'):
                    validate_registration(record, self.plan, self.matrix)

    def test_missing_evidence_or_tampered_bytes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory)
            path = Path(record['artifacts']['fixture_selftest']['path'])
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                validate_registration(record, self.plan, self.matrix)

    def test_runtime_artifact_pin_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory)
            record['target']['source_commit'] = 'b'*40
            with self.assertRaisesRegex(ValueError, 'Runtime identity'):
                validate_registration(record, self.plan, self.matrix)

    def test_effective_config_artifacts_must_match_declared_change(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory)
            record['contrast']['intervention_config']['agents.defaults.maxConcurrent'] = 8
            with self.assertRaisesRegex(ValueError, 'Effective config artifact'):
                validate_registration(record, self.plan, self.matrix)

    def test_preregistration_cannot_claim_proven_tradeoff(self):
        record = registration_template(self.study)
        record['tradeoff_proven'] = True
        with self.assertRaisesRegex(ValueError, 'product conclusions'):
            validate_registration(record, self.plan, self.matrix)

    def test_real_usage_study_cannot_be_registered_as_deterministic(self):
        study = next(s for s in self.plan['studies'] if s['id'] == 'ARC-05')
        with tempfile.TemporaryDirectory() as directory:
            record = self.complete_record(directory, study)
            record['contrast']['config_key'] = 'synthetic.reuse'
            record['contrast']['baseline_config'] = {'synthetic.reuse':False}
            record['contrast']['intervention_config'] = {'synthetic.reuse':True}
            with self.assertRaisesRegex(ValueError, 'includes real-usage'):
                validate_registration(record, self.plan, self.matrix)

    def test_cli_study_selection(self):
        result = subprocess.run([sys.executable, str(ROOT/'evaluation/tools/architecture.py'), 'plan', '--study', 'ARC-03'], capture_output=True, text=True, check=True)
        self.assertEqual([s['id'] for s in json.loads(result.stdout)['studies']], ['ARC-03'])


if __name__ == '__main__':
    unittest.main()
