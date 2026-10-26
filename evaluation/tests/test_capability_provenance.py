"""Verified nonapplicability is separate from measurements and cannot skip probing."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from adapter_readiness import SOURCES,native_validation
from campaign import audit,load_plan
from run_campaign_family import bind_unit
from suite import ROOT


class CapabilityProvenanceTest(unittest.TestCase):
    def fixture(self,formal):
        plan=load_plan();rows=[dict(scenario_id=f'COST-05-S{i:02}',unit=1,state='unsupported',native_invoked=True,fixture_validated=True,
            native_capability_absent=True,capability_evidence=['actual-native-scope-probe'],probe_attempted=True,
            native_contract=dict(target_commit=plan['target']['source_commit'],reference='pinned-native-contract',sha256='a'*64),exclusion_reason='capability-not-provided') for i in range(1,5)]
        return plan,dict(kind='native-campaign-family-unit' if formal else 'native-adapter-validation',full_campaign_coverage=formal,case_id='COST-05',runtime_identity=dict(version=plan['target']['version'],commit=plan['target']['source_commit']),
            controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['COST-05']},observations=rows,validation_complete=True,fixture_and_invocation_valid=True)

    def test_formal_binder_preserves_probe_contract_without_counting_performance_samples(self):
        plan,native=self.fixture(True);rows=bind_unit(plan,'COST-05',1,native,'actual-hosted-run','controller','unit-1/summary.json','b'*64)
        report=audit(plan,rows)
        self.assertEqual(report['verified_nonapplicable_scenarios'],4)
        self.assertEqual(report['measured_scenarios'],0);self.assertEqual(report['accepted_observation_count'],0)
        self.assertEqual(rows[0]['native_contract']['target_commit'],plan['target']['source_commit'])
        native['observations'][0]['exclusion_reason']='missing-implementation'
        with self.assertRaises(ValueError):bind_unit(plan,'COST-05',1,native,'actual-hosted-run','controller','unit-1/summary.json','b'*64)

    def test_candidate_capability_needs_native_invocation_and_exact_contract(self):
        plan,proof=self.fixture(False)
        self.assertEqual(len(native_validation(plan,[proof])),4)
        missing=copy.deepcopy(proof);missing['observations'][0]['probe_attempted']=False
        self.assertNotIn('COST-05-S01',native_validation(plan,[missing]))
        missing=copy.deepcopy(proof);missing['observations'][0]['native_invoked']=False
        self.assertNotIn('COST-05-S01',native_validation(plan,[missing]))
        missing=copy.deepcopy(proof);missing['observations'][0]['native_contract']['target_commit']='other-core'
        self.assertNotIn('COST-05-S01',native_validation(plan,[missing]))
