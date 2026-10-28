"""Fixture-provider and rollout-predicate tests for the Codex adapter base.

The SSE fixture is tested over real HTTP without any product binary; binary
tests run only when a local codex is available (development machines) so CI
never gains an execution capability from this file.
"""

import json
from pathlib import Path
import shutil
import sys
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runner'))

from codex_provider_fixture import ResponsesFixture


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = ResponsesFixture().start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def _post(self, body, headers=None):
        request = urllib.request.Request(
            self.fixture.base_url + '/responses', data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + self.fixture.bearer, **(headers or {})})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()

    def test_sse_stream_event_order_and_completed_usage(self):
        status, body = self._post({'model': 'fixture-model', 'input': [], 'stream': True})
        self.assertEqual(status, 200)
        kinds = [line[len('event: '):] for line in body.splitlines() if line.startswith('event: ')]
        self.assertEqual(kinds[0], 'response.created')
        self.assertIn('response.output_item.done', kinds)
        self.assertEqual(kinds[-1], 'response.completed')
        completed = json.loads([l[len('data: '):] for l in body.splitlines()
                                if l.startswith('data: ') and '"response.completed"' in l][0])
        self.assertEqual(completed['response']['usage']['total_tokens'], 108)
        self.assertEqual(completed['response']['output'][0]['role'], 'assistant')

    def test_ledger_records_requests_independently(self):
        before = len(self.fixture.requests())
        self._post({'model': 'fixture-model', 'input': [{'role': 'user'}], 'stream': True})
        entries = self.fixture.requests()[before:]
        self.assertTrue(any(e['kind'] == 'response-request' and e['authorized'] for e in entries))
        self.assertTrue(any(e['kind'] == 'response-sent' for e in entries))

    def test_bad_bearer_is_rejected_and_ledgered(self):
        request = urllib.request.Request(
            self.fixture.base_url + '/responses', data=b'{}',
            headers={'Authorization': 'Bearer wrong'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 401)
        self.assertTrue(any(e['kind'] == 'response-request' and e.get('status') == 401
                            for e in self.fixture.requests()))

    def test_hold_gate_blocks_until_released(self):
        import threading
        self.fixture.hold_mode = True
        self.fixture.release.clear()
        thread = threading.Thread(
            target=lambda: self._post({'model': 'fixture-model', 'input': [], 'stream': True}))
        thread.start()
        self.assertTrue(self.fixture.hold_event.wait(timeout=5))
        self.assertFalse(any(e['kind'] == 'response-sent'
                             for e in self.fixture.requests()[-3:]))
        self.fixture.release.set()
        self.fixture.hold_mode = False
        thread.join(timeout=10)


class RolloutPredicateTests(unittest.TestCase):
    def test_predicates_classify_synthetic_rollout_lines(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runner'))
        import rel01_cases as rel01
        records = [
            {'type': 'session_meta', 'payload': {'session_id': 's1'}},
            {'type': 'response_item', 'payload': {'role': 'user',
             'content': [{'type': 'input_text', 'text': 'REL01_MARKER_INPUT_S01'}]}},
            {'type': 'response_item', 'payload': {'role': 'assistant',
             'content': [{'type': 'output_text', 'text': 'FIXTURE_FINAL_REPLY'}]}},
            {'type': 'event_msg', 'payload': {'type': 'task_complete',
             'last_agent_message': 'FIXTURE_FINAL_REPLY'}},
            {'type': 'token_usage_record', 'payload': {'response_id': 'resp_fixture_1'}},
        ]
        self.assertEqual(len(rel01.user_prompt_lines(records, 'REL01_MARKER_INPUT_S01')), 1)
        self.assertEqual(len(rel01.assistant_final_lines(records, 'FIXTURE_FINAL_REPLY')), 1)
        self.assertEqual(len(rel01.task_complete_events(records)), 1)
        self.assertEqual(len(rel01.usage_records(records, 'resp_fixture_1')), 1)
        self.assertEqual(rel01.user_prompt_lines(records, 'absent-token'), [])


@unittest.skipIf(shutil.which('codex') is None, 'no local codex binary on this host')
class CodexBinarySmokeTest(unittest.TestCase):
    def test_isolated_turn_completes_without_touching_real_home(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runner'))
        from codex_runtime import CodexRuntime
        runtime = CodexRuntime()
        try:
            result = runtime.run('Reply with exactly: UNITTEST_OK', timeout=90)
            self.assertEqual(result['exit'], 0)
            self.assertIn('FIXTURE_FINAL_REPLY', result['stdout'])
            digests = runtime.rollout_digest()
            self.assertEqual(len(digests), 1)
            self.assertIn('response_item', digests[0]['types'])
        finally:
            runtime.close()


if __name__ == '__main__':
    unittest.main()
