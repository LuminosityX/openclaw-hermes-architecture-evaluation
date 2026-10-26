"""Billing partition and unknown-attempt correctness independent of native code."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from billing_accounting import account

class BillingAccountingTest(unittest.TestCase):
    def record(self,**extra):
        result=dict(forwarded_to_provider=True,started_at_utc='2026-10-26T21:00:00+00:00',task_id='EVAL_TEST',usage=dict(prompt_tokens=1000,prompt_cache_hit_tokens=800,prompt_cache_miss_tokens=200,completion_tokens=100,completion_tokens_details=dict(reasoning_tokens=60)))
        result.update(extra);return result
    def test_discarded_paid_reply_is_included_once_with_subsets(self):
        result=account(dict(requests=[self.record(owned_response_intervention='discard-paid-reply-with-503'),self.record()]))
        self.assertEqual(result['input_tokens_inclusive'],2000)
        self.assertEqual(result['output_tokens_including_reasoning'],200)
        self.assertEqual(result['calculated_usd'],'0.0001848')
        self.assertIsNone(result['actual_invoice_usd'])
    def test_missing_usage_prevents_false_complete_total(self):
        result=account(dict(requests=[self.record(),self.record(usage=None)]))
        self.assertIsNone(result['input_tokens_inclusive'])
        self.assertIsNone(result['calculated_usd'])
        self.assertFalse(result['complete_usage_for_all_attempts'])
    def test_peak_window_without_holiday_calendar_retains_price_range(self):
        result=account(dict(requests=[self.record(started_at_utc='2026-10-27T02:00:00+00:00')]))
        self.assertIsNone(result['calculated_usd'])
        self.assertIsNotNone(result['requests'][0]['calculated_usd_bounds'])

    def test_unfinished_admitted_attempt_is_not_omitted_from_total(self):
        result=account(dict(requests=[self.record()],real_provider_request_count=2))
        self.assertEqual(result['real_attempt_count'],2)
        self.assertEqual(result['unfinished_attempts_with_unknown_usage'],1)
        self.assertIsNone(result['input_tokens_inclusive'])
        self.assertIsNone(result['calculated_usd'])

    def test_owned_unit_identity_survives_a_partial_model_prompt_marker(self):
        record=self.record(task_id='EVAL_BILLIN',synthetic_input_observations=dict(owned_accounting_task_id='EVAL_BILLING_COST_07_S04_U1'))
        result=account(dict(requests=[record]))['requests'][0]
        self.assertEqual(result['task_id'],'EVAL_BILLING_COST_07_S04_U1')
        self.assertEqual(result['native_prompt_task_marker'],'EVAL_BILLIN')
        self.assertEqual(result['attribution_method'],'exclusive-owned-task-relay')
