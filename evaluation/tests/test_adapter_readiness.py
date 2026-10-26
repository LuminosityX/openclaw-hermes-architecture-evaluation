"""Implementation readiness cannot be inferred from scenario labels or old pilots."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from adapter_readiness import readiness, native_validation, SOURCES
from campaign import load_plan
from suite import ROOT


class ReadinessTests(unittest.TestCase):
    def test_entire_frozen_scope_remains_visible(self):
        report=readiness(load_plan())
        self.assertEqual(report['scenario_count'],257)
        self.assertEqual(sum(report['preparation_counts'].values()),257)
        self.assertFalse(report['ready_for_full_execution'])

    def test_pilot_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'candidate-adapter'): native_validation(load_plan(),[dict(kind='exploratory-pilot')])

    def test_failed_product_observation_can_validate_only_exact_controller(self):
        plan=load_plan()
        proof=dict(kind='native-adapter-validation',full_campaign_coverage=False,case_id='REL-14',
            runtime_identity=dict(version=plan['target']['version'],commit=plan['target']['source_commit']),
            controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['REL-14']},
            validation_complete=True,fixture_and_invocation_valid=True,
            observations=[dict(scenario_id='REL-14-S01',state='fail',native_invoked=True,fixture_validated=True)])
        self.assertIn('REL-14-S01',native_validation(plan,[proof]))
        proof['controller_sha256'][SOURCES['REL-14'][0]]='old-source'
        self.assertNotIn('REL-14-S01',native_validation(plan,[proof]))
