"""Implementation readiness cannot be inferred from scenario labels or old pilots."""
import copy
import hashlib
from pathlib import Path
import sys
import json
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from adapter_readiness import readiness, native_validation, SOURCES, load_proofs, require_execution_ready
from campaign import load_plan
from suite import ROOT


class ReadinessTests(unittest.TestCase):
    def proof(self,plan):
        return dict(kind='native-adapter-validation',full_campaign_coverage=False,case_id='REL-14',
            runtime_identity=dict(version=plan['target']['version'],commit=plan['target']['source_commit']),
            controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['REL-14']},
            validation_complete=True,fixture_and_invocation_valid=True,
            observations=[dict(scenario_id=f'REL-14-S{i:02}',state='fail',native_invoked=True,fixture_validated=True,
                               assertions=[dict(name='product-regression',verdict='fail',evidence=['independent-receipt'])]) for i in range(1,5)])

    def test_batched_plan_requires_every_scenario_of_the_selected_family(self):
        plan=load_plan()
        proof=self.proof(plan)
        self.assertFalse(require_execution_ready(plan,'REL-14',[proof])['ready_for_full_execution'])
        with self.assertRaisesRegex(ValueError,'Selected family'):
            require_execution_ready(plan,'REL-15',[proof])
        original=load_plan(ROOT/'evaluation/campaigns/full-20261026/plan.json')
        with self.assertRaisesRegex(ValueError,'Full scope'):
            require_execution_ready(original,'REL-14',[proof])
    def test_entire_frozen_scope_remains_visible(self):
        report=readiness(load_plan())
        self.assertEqual(report['scenario_count'],257)
        self.assertEqual(sum(report['preparation_counts'].values()),257)
        self.assertFalse(report['ready_for_full_execution'])

    def test_pilot_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'candidate-adapter'): native_validation(load_plan(),[dict(kind='exploratory-pilot')])

    def test_adjacent_installation_metadata_is_not_an_adapter_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'adapter-validation-123-REL-14.json').write_text(json.dumps(dict(kind='native-adapter-validation')))
            (root/'adapter-validation-123-REL-14-installation.json').write_text(json.dumps(dict(kind='published-installation-check')))
            self.assertEqual(len(load_proofs(root)),1)

    def test_failed_product_observation_can_validate_only_exact_controller(self):
        plan=load_plan()
        proof=dict(kind='native-adapter-validation',full_campaign_coverage=False,case_id='REL-14',
            runtime_identity=dict(version=plan['target']['version'],commit=plan['target']['source_commit']),
            controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['REL-14']},
            validation_complete=True,fixture_and_invocation_valid=True,
            observations=[dict(scenario_id=f'REL-14-S{i:02}',state='fail',native_invoked=True,fixture_validated=True,
                               assertions=[dict(name='product-regression',verdict='fail',evidence=['independent-receipt'])]) for i in range(1,5)])
        self.assertIn('REL-14-S01',native_validation(plan,[proof]))
        incomplete=copy.deepcopy(proof)
        incomplete['observations']=incomplete['observations'][:1]
        self.assertEqual(native_validation(plan,[incomplete]),{})
        inconsistent=copy.deepcopy(proof)
        inconsistent['observations'][0]['state']='pass'
        self.assertNotIn('REL-14-S01',native_validation(plan,[inconsistent]))
        proof['controller_sha256'][SOURCES['REL-14'][0]]='old-source'
        self.assertNotIn('REL-14-S01',native_validation(plan,[proof]))
