"""Acceptance catches broken artifacts, stale citations and duplicate effects."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from task_workloads import workload, judge, dependency_result


class TaskWorkloadTests(unittest.TestCase):
    def test_all_five_types_have_six_reproducible_distinct_units(self):
        for number in range(1,6):
            tasks=[workload(f'PERF-09-S{number:02}',unit) for unit in range(1,7)]
            self.assertEqual(len({task['public_fixture_sha256'] for task in tasks}),6)
            self.assertEqual(tasks[0],workload(f'PERF-09-S{number:02}',1))
            for task in tasks:
                self.assertNotIn('oracle',task['public'])
                self.assertNotIn('expected',task['public'])

    def test_broken_arithmetic_fails_and_independent_outputs_pass(self):
        task=workload('PERF-09-S01',1)
        self.assertFalse(judge(task,task['files'],function_results=[{'USD':'0.3'}])['accepted'])
        self.assertTrue(judge(task,{'solution.py':'fixed code'},function_results=task['oracle']['expected'])['accepted'])
        self.assertFalse(judge(task,{},function_results=task['oracle']['expected'])['accepted'])

    def test_dependency_oracle_includes_referenced_nodes_deduplicates_and_detects_cycle(self):
        self.assertEqual(dependency_result({'z':['a','a'],'b':[]}),['a','b','z'])
        self.assertEqual(dependency_result({'x':['x']}),{'error':'ValueError'})

    def test_older_or_draft_research_answer_fails(self):
        import json
        task=workload('PERF-09-S04',1)
        expected=task['oracle']['expected']
        self.assertTrue(judge(task,{'answer.json':json.dumps(expected)})['accepted'])
        self.assertFalse(judge(task,{'answer.json':json.dumps(dict(expected,cache_ttl_seconds=999))})['accepted'])

    def test_duplicate_effect_or_unverified_receipt_fails(self):
        import json
        task=workload('PERF-09-S05',1)
        receipt=dict(order_id=task['oracle']['order_id'],amount_cents=task['oracle']['amount_cents'],receipt_id='receipt-1')
        artifact={'receipt.json':json.dumps(receipt)}
        commit=dict(kind='commit-effect',sequence=1,**receipt)
        read=dict(kind='status-read',sequence=2)
        self.assertTrue(judge(task,artifact,service_events=[commit,read])['accepted'])
        self.assertFalse(judge(task,artifact,service_events=[commit,commit,read])['accepted'])
        self.assertFalse(judge(task,artifact,service_events=[commit])['accepted'])
