"""Usage accounting must not hide paid failed calls or count synthetic controls."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from retain_provider_usage import summarize


class ProviderAccountingTest(unittest.TestCase):
    def test_synthetic_controls_are_excluded_and_missing_paid_usage_stays_unknown(self):
        ledger=dict(kind='real-provider-request-ledger',real_provider_request_count=3,requests=[
            dict(real_provider_call=True,forwarded_to_provider=True,usage_complete=True,response_model='moving-alias',
                usage=dict(prompt_tokens=100,completion_tokens=20,prompt_cache_hit_tokens=80,prompt_cache_miss_tokens=20)),
            dict(real_provider_call=True,forwarded_to_provider=True,usage_complete=False,upstream_status=503,usage=None)])
        synthetic=dict(kind='deterministic-provider-transcript-ledger',real_provider_request_count=0,requests=[])
        result=summarize({'task/provider-usage.json':json.dumps(ledger).encode(),'calibration/provider-usage.json':json.dumps(synthetic).encode()},'https://example.invalid/owned')
        self.assertEqual(result['real_provider_requests'],3)
        self.assertEqual(result['formal_task_units'],1)
        self.assertEqual(result['known_provider_usage_sums']['prompt_tokens'],100)
        self.assertEqual(result['requests_missing_counter']['prompt_tokens'],2)
        self.assertEqual(result['requests_without_complete_usage'],2)
        self.assertEqual(len(result['sources']),1)
        self.assertNotIn('raw_prompt',str(result))
