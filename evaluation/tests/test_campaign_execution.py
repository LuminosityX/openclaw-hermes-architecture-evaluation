"""Formal records must come from new, pinned, complete native units."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from campaign import audit,load_plan
from run_campaign_family import bind_unit
from adapter_readiness import SOURCES
from suite import ROOT
from run_task_unit import native_completion_assertion
from task_workloads import workload


class CampaignExecutionTests(unittest.TestCase):
    def test_pending_scenario_binding_requires_exact_selection(self):
        plan,native=self.fixture()
        native['observations']=native['observations'][:1]
        arguments=(plan,'REL-14',1,native,'123','controller','unit-1/summary.json','a'*64)
        with self.assertRaisesRegex(ValueError,'missing or duplicated'):
            bind_unit(*arguments)
        rows=bind_unit(*arguments,selected_scenarios=['REL-14-S01'])
        self.assertEqual(len(rows),1)
        with self.assertRaisesRegex(ValueError,'outside'):
            bind_unit(*arguments,selected_scenarios=['SEC-11-S01'])
    def test_correct_artifact_does_not_hide_task_timeout_or_native_http_failure(self):
        task=workload('PERF-09-S01',1)
        good=dict(native_http_status=200,completion_ms=100)
        self.assertEqual(native_completion_assertion(good,task)['verdict'],'pass')
        for bad in [dict(good,task_transport_error='TimeoutError'),dict(good,completion_ms=181000),dict(good,native_http_status=500),{}]:
            self.assertEqual(native_completion_assertion(bad,task)['verdict'],'fail')
    def fixture(self):
        plan=load_plan()
        native=dict(kind='native-campaign-family-unit',full_campaign_coverage=True,case_id='REL-14',
            runtime_identity=dict(version=plan['target']['version'],commit=plan['target']['source_commit']),
            controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['REL-14']},
            observations=[dict(scenario_id=f'REL-14-S{i:02}',unit=1,state='fail',native_invoked=True,fixture_validated=True,
                assertions=[dict(name='receipt',verdict='fail',evidence=['independent-ledger'])]) for i in range(1,5)])
        return plan,native

    def test_calibration_cannot_be_relabelled_as_formal(self):
        plan,native=self.fixture()
        native.update(kind='native-adapter-validation',full_campaign_coverage=False)
        with self.assertRaisesRegex(ValueError,'explicitly formal'):
            bind_unit(plan,'REL-14',1,native,'run','commit','unit-1/summary.json','a'*64)

    def test_partial_family_does_not_open_the_architecture_gate(self):
        plan,native=self.fixture()
        rows=bind_unit(plan,'REL-14',1,native,'run','commit','unit-1/summary.json','a'*64)
        report=audit(plan,rows)
        self.assertEqual(report['accepted_observation_count'],4)
        self.assertFalse(report['analysis_allowed'])
        self.assertEqual(report['scenario_counts']['partial'],4)

    def test_missing_rows_or_wrong_independent_unit_are_rejected(self):
        plan,native=self.fixture()
        with self.assertRaisesRegex(ValueError,'unit index'):
            bind_unit(plan,'REL-14',2,native,'run','commit','native.json','a'*64)
        native['observations'].pop()
        with self.assertRaisesRegex(ValueError,'missing or duplicated'):
            bind_unit(plan,'REL-14',1,native,'run','commit','native.json','a'*64)

    def test_new_plan_preserves_scope_units_and_original_plan(self):
        plan=load_plan()
        original=load_plan(ROOT/plan['supersedes']['plan_path'])
        self.assertEqual(plan['cases'],original['cases'])
        self.assertEqual(plan['target'],original['target'])
        self.assertEqual(plan['resource_policy'],original['resource_policy'])
        self.assertEqual(plan['model'],original['model'])
        self.assertEqual(plan['supersedes']['plan_sha256'],original['plan_sha256'])
        self.assertFalse(plan['workflow']['interim_architecture_conclusions'])
