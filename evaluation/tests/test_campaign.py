"""Completion is about independently executed coverage, including product failures."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from campaign import audit, load_plan, scenario_index, validate_result


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.plan=load_plan()

    def observation(self,sid,unit=1,state='pass'):
        return dict(schema_version=1,plan_sha256=self.plan['plan_sha256'],product='openclaw',
                    target_version=self.plan['target']['version'],target_commit=self.plan['target']['source_commit'],
                    scenario_id=sid,state=state,run_id='test-owned-run',evidence=['test-owned-receipt'],unit=unit,
                    fixture_validated=True,native_invoked=True,
                    assertions=[dict(verdict=state,evidence=['test-owned-receipt'])])

    def test_full_scope_empty_cannot_seal(self):
        report=audit(self.plan,[])
        self.assertEqual(report['scenario_counts'],{'not-run':257})
        self.assertFalse(report['analysis_allowed'])

    def test_product_failures_are_completed_experiments(self):
        records=[self.observation(sid,unit,'fail') for sid,(case,_) in scenario_index(self.plan).items()
                 for unit in range(1,case['required_independent_units']+1)]
        report=audit(self.plan,records)
        self.assertTrue(report['experiments_complete'])
        self.assertEqual(report['scenario_counts'],{'fail':257})
        self.assertFalse(audit(self.plan,records[:-1])['analysis_allowed'])

    def test_missing_key_and_harness_failure_are_incomplete(self):
        for state in ['blocked','harness-error']:
            record=self.observation('REL-01-S01',state=state)
            record['reason']='fixture unavailable'
            self.assertFalse(audit(self.plan,[record])['experiments_complete'])

    def test_old_pilot_or_mismatched_pin_is_rejected(self):
        for field in ['plan_sha256','target_commit','target_version']:
            record=self.observation('REL-01-S01')
            record[field]='historical'
            with self.assertRaises(ValueError): validate_result(record,self.plan)

    def test_duplicate_unit_and_unexecuted_pass_rejected(self):
        record=self.observation('REL-01-S01')
        with self.assertRaisesRegex(ValueError,'same independent unit'): audit(self.plan,[record,record])
        record['native_invoked']=False
        with self.assertRaises(ValueError): validate_result(record,self.plan)

    def test_development_calibration_cannot_be_promoted_to_full_results(self):
        record=self.observation('REL-01-S01')
        record['full_campaign_coverage']=False
        validate_result(record,self.plan,allow_development=True)
        with self.assertRaisesRegex(ValueError,'calibration'): audit(self.plan,[record])

    def test_nonapplicable_requires_versioned_native_capability_proof(self):
        record=self.observation('REL-01-S01',state='unsupported')
        record.update(native_capability_absent=True,capability_evidence=['probe-receipt'],probe_attempted=True)
        with self.assertRaises(ValueError): validate_result(record,self.plan)
        record.update(native_contract=dict(target_commit=self.plan['target']['source_commit'],reference='native-contract',sha256='a'*64),
                      exclusion_reason='capability-not-provided')
        validate_result(record,self.plan)
        record['exclusion_reason']='no-macos-runner'
        with self.assertRaises(ValueError): validate_result(record,self.plan)

    def test_frozen_plan_tampering_and_early_interpretation_rejected(self):
        plan=copy.deepcopy(self.plan)
        plan['model']['spend_limit']=10
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'plan.json'
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'changed'): load_plan(path)
        record=self.observation('REL-01-S01')
        record['architecture_conclusion']='too early'
        with self.assertRaisesRegex(ValueError,'deferred'): validate_result(record,self.plan)
