"""Fault scripts and acceptance distinguish native failures from broken fixtures."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'runner')]
from protocol_cases import acceptance, completion_frames, scripted_response, selfcheck


class ProtocolTests(unittest.TestCase):
    def test_fragmented_unicode_json_is_exactly_reconstructed(self):
        self.assertTrue(selfcheck()['unicode_preserved'])
        script=scripted_response('REL-14-S01','PILOT_π_换行',1,{'messages':[]})
        frames=completion_frames(script,'PILOT_π_换行')
        args=''.join(c['function']['arguments'] for f in frames for c in f['choices'][0]['delta'].get('tool_calls',[]))
        self.assertEqual(json.loads(args)['token'],'PILOT_π_换行')

    def test_fault_scripts_recover_only_when_contract_allows_it(self):
        empty={'messages':[]}
        self.assertEqual(scripted_response('REL-15-S01','PILOT_TEST',1,empty)['retry_after'],'1')
        self.assertIn('tool_name',scripted_response('REL-15-S01','PILOT_TEST',2,empty))
        self.assertTrue(scripted_response('REL-15-S02','PILOT_TEST',2,empty)['disconnect'])
        self.assertEqual(scripted_response('REL-15-S04','PILOT_TEST',10,empty)['status'],503)
        self.assertEqual(scripted_response('REL-15-S05','PILOT_TEST',1,empty)['status'],400)

    def test_fixture_does_not_report_success_without_receipt(self):
        body={'messages':[{'role':'tool','content':'timeout'}]}
        self.assertEqual(scripted_response('REL-15-S03','PILOT_TEST',2,body)['content'],'INCOMPLETE:PILOT_TEST')

    def test_duplicate_effect_and_ignored_retry_after_fail_acceptance(self):
        events=[dict(kind='scripted-provider-request',monotonic_ns=0),
                dict(kind='scripted-provider-request',monotonic_ns=10),
                dict(kind='effect-commit'),dict(kind='effect-commit')]
        checks={c['name']:c['verdict'] for c in acceptance('REL-15-S01',{'accepted':True},events)}
        self.assertEqual(checks['no-duplicate-committed-effects'],'fail')
        self.assertEqual(checks['retry-after-respected'],'fail')

    def test_terminal_provider_failure_cannot_be_accepted(self):
        events=[dict(kind='scripted-provider-request')]
        checks=acceptance('REL-15-S04',{'accepted':True},events)
        self.assertIn('fail',[c['verdict'] for c in checks])
