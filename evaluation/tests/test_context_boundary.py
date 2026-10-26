"""A context boundary failure needs independent native callback evidence."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from context_contract_cases import observed_preflight_refusal


class ContextBoundaryTest(unittest.TestCase):
    def test_generic_http_errors_or_callback_alone_are_not_context_outcomes(self):
        event=[{'event_type':'compact-no-transcript-rewrite'}]
        self.assertFalse(observed_preflight_refusal({'status':500,'response_excerpt':'fixture crashed'},event))
        self.assertFalse(observed_preflight_refusal({'status':200,'response_excerpt':'Preflight compaction required but failed'},event))
        self.assertFalse(observed_preflight_refusal({'status':500,'response_excerpt':'Preflight compaction required but failed'},[]))

    def test_exact_native_error_and_actual_compact_callback_prove_boundary(self):
        self.assertTrue(observed_preflight_refusal(
            {'status':500,'response_excerpt':'{"error":"Preflight compaction required but failed: reference declined"}'},
            [{'event_type':'assemble'},{'event_type':'compact-no-transcript-rewrite'}]))
