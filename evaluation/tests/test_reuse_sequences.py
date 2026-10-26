"""Paired task quality, stale rules and fee normalization stay independent."""
import json
from pathlib import Path
import sys
import unittest
from urllib.request import Request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reuse_workloads import workload,judge,answer
from reuse_accounting import account
from task_transcripts import provider_for


class ReuseSequenceTest(unittest.TestCase):
    def series(self,task):
        rows=[dict(artifact_text=json.dumps(expected),status=200,latency_ms=10) for expected in task['oracle']['expected']]
        return {arm:dict(answers=list(rows),asset_created=arm=='reuse',asset_marker_present=arm=='reuse',learning=dict(status=200,latency_ms=10)) for arm in ['baseline','reuse']}

    def test_equal_tasks_and_counterbalanced_order_with_explicit_stale_version_boundary(self):
        self.assertEqual(answer(dict(order_id='x',weight=2,zone='local',vip=True),1)['credits'],7)
        self.assertEqual(answer(dict(order_id='x',weight=3,zone='remote',vip=True),2)['credits'],28)
        for i,horizon in [(1,1),(2,5),(3,20),(4,5)]:
            task=workload(f'COST-03-S{i:02}',1)
            self.assertEqual(task['reuse']['horizon'],horizon)
            self.assertNotIn('golden_asset',task['public']['reuse'])
            self.assertEqual(workload(task['scenario_id'],2)['reuse']['arm_order'],['reuse','baseline'])
        self.assertEqual([r['policy_version'] for r in workload('COST-03-S04',1)['reuse']['orders']],[1,1,2,2,2])

    def test_correct_final_answer_cannot_hide_earlier_wrong_or_late_deliveries(self):
        task=workload('COST-03-S02',1);series=self.series(task)
        self.assertTrue(judge(task,{'series.json':json.dumps(series)})['accepted'])
        series['reuse']['answers'][0]=dict(artifact_text='{}',status=200,latency_ms=10)
        result=judge(task,{'series.json':json.dumps(series)})
        self.assertFalse(result['accepted']);self.assertEqual(result['accepted_deliveries']['reuse'],4)
        series=self.series(task);series['baseline']['answers'][0]['latency_ms']=26000
        self.assertFalse(judge(task,{'series.json':json.dumps(series)})['accepted'])

    def test_actual_learning_and_failed_calls_stay_in_reuse_numerator(self):
        def row(stage,tokens):return dict(forwarded_to_transport=True,synthetic_input_observations=dict(reuse_stage=stage),usage=dict(prompt_tokens=tokens))
        ledger=dict(kind='real-provider-request-ledger',forwarded_request_count=5,requests=[row('BASELINE_TASK_0',100),row('LEARN',30),row('REUSE_TASK_0',10),row('REUSE_TASK_0',15)])
        ledger['requests'][3].update(upstream_status=503,error_type='upstream-http-error')
        result=account(ledger,dict(baseline=1,reuse=2))
        self.assertEqual(result['normalization']['reuse']['known_tokens_per_accepted_delivery']['prompt_tokens'],27.5)
        self.assertIsNone(result['normalization']['reuse']['known_tokens_per_accepted_delivery']['completion_tokens'])
        self.assertEqual(result['groups']['unattributed']['requests'],1)
        self.assertIsNone(result['actual_charge_usd']);self.assertIsNone(result['monetary_break_even'])

    def test_golden_native_learning_and_delivery_paths_are_distinct(self):
        task=workload('COST-03-S01',1);transport=provider_for(task)
        def call(stage):
            request=Request('https://unused.invalid',data=json.dumps(dict(messages=[dict(role='user',content='COST_STAGE_'+stage+' '+task['task_id'])])).encode())
            with transport(request,timeout=1) as response:return json.loads(response.read().decode().splitlines()[0][6:])['choices'][0]['delta']
        self.assertEqual(call('LEARN')['tool_calls'][0]['function']['name'],'task_files')
        native_write=call('LEARN')['tool_calls'][0]['function'];self.assertEqual(native_write['name'],'write')
        self.assertTrue(json.loads(native_write['arguments'])['path'].endswith('/AGENTS.md'))
        delivery=call('REUSE_TASK_0')['tool_calls'][0]['function']
        self.assertEqual(json.loads(delivery['arguments'])['path'],'answer-reuse-00.json')
