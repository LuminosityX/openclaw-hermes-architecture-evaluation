"""Comparison model fixture M conformance tests (protocol §3, Responses mode)."""

import json
from pathlib import Path
import shutil
import sys
import threading
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'comparison'))

from model_fixture import ModelFixture


class ModelFixtureConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = ModelFixture(unit_id='CONF-1', ack_text='ACK_CONF_1').start()

    @classmethod
    def tearDownClass(cls):
        cls.m.close()

    def _post(self, body=None):
        request = urllib.request.Request(
            self.m.base_url + '/responses',
            data=json.dumps(body or {'model': 'fixture-model', 'input': [], 'stream': True}).encode(),
            headers={'Authorization': 'Bearer ' + self.m.bearer})
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode()

    def test_ack_request_ledger_carries_protocol_fields(self):
        before = len(self.m.entries('request'))
        status, body = self._post({'model': 'fixture-model', 'stream': True,
                                   'input': [{'type': 'message', 'role': 'user',
                                              'content': [{'type': 'input_text',
                                                           'text': 'SESSION_MARKER_CONF'}]}],
                                   'tools': [{'type': 'function', 'name': 'exec_command',
                                              'parameters': {'type': 'object'}}]})
        self.assertEqual(status, 200)
        entries = self.m.entries('request')[before:]
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        for field in ('unit_id', 'monotonic_ns', 'wall_utc', 'protocol', 'request_number',
                      'input_items', 'tool_names', 'tool_schema_sha256', 'mode'):
            self.assertIn(field, entry)
        self.assertEqual(entry['unit_id'], 'CONF-1')
        self.assertEqual(entry['protocol'], 'responses')
        self.assertIn('SESSION_MARKER_CONF', json.dumps(entry['input_items']))
        self.assertEqual(entry['tool_names'], ['exec_command'])
        self.assertRegex(entry['tool_schema_sha256'], r'^[0-9a-f]{64}$')

    def test_sse_event_order_and_synthetic_usage(self):
        status, body = self._post()
        kinds = [line[len('event: '):] for line in body.splitlines() if line.startswith('event: ')]
        self.assertEqual(kinds[0], 'response.created')
        self.assertEqual(kinds[-1], 'response.completed')
        self.assertIn('response.output_item.done', kinds)
        completed = json.loads([line[len('data: '):] for line in body.splitlines()
                                if line.startswith('data: ')
                                and '"response.completed"' in line][0])
        self.assertEqual(completed['response']['usage']['total_tokens'], 108)
        self.assertEqual(completed['response']['output'][0]['role'], 'assistant')

    def test_503_once_then_ack(self):
        self.m.mode = '503_once'
        number_before = len(self.m.entries('request'))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self._post()
        self.assertEqual(caught.exception.code, 503)
        failures = self.m.entries('http-failure')
        self.assertEqual(failures[-1]['status'], 503)
        self.assertEqual(failures[-1]['request_number'], number_before + 1)
        status, _ = self._post()
        self.assertEqual(status, 200)
        self.assertEqual(self.m.mode, 'ack')

    def test_hold_before_response_gates_and_records_socket_close(self):
        m = ModelFixture(unit_id='HOLD-1').start()
        try:
            m.mode = 'hold_before_response'
            m.hold_release.clear()
            result = {}

            def client():
                try:
                    self._post_on(m)
                    result['status'] = 'completed'
                except Exception as error:  # deliberate early close by the client
                    result['status'] = f'error:{type(error).__name__}'

            thread = threading.Thread(target=client)
            thread.start()
            self.assertTrue(m.request_received.wait(timeout=5))
            self.assertFalse(m.entries('response-sent') or result)
            # Release the hold after the fault window was observed.
            m.hold_release.set()
            thread.join(timeout=10)
            self.assertTrue(m.entries('response-sent'))
            self.assertFalse(m.entries('socket-close'))
        finally:
            m.close()

    def test_scripted_calls_emit_function_call_items(self):
        m = ModelFixture(unit_id='SCRIPT-1').start()
        try:
            m.mode = 'scripted_calls'
            m.script = [{'call': {'name': 'exec_command',
                                  'arguments': {'cmd': 'echo hi'}}},
                        {'reply': 'SCRIPT_FINAL'}]
            status, body = self._post_on(m)
            self.assertEqual(status, 200)
            item = json.loads([line[len('data: '):] for line in body.splitlines()
                               if line.startswith('data: ')
                               and '"response.output_item.done"' in line][0])['item']
            self.assertEqual(item['type'], 'function_call')
            self.assertEqual(item['name'], 'exec_command')
            self.assertEqual(json.loads(item['arguments']), {'cmd': 'echo hi'})
            status, body = self._post_on(m)
            item = json.loads([line[len('data: '):] for line in body.splitlines()
                               if line.startswith('data: ')
                               and '"response.output_item.done"' in line][0])['item']
            self.assertEqual(item['content'][0]['text'], 'SCRIPT_FINAL')
        finally:
            m.close()

    def test_large_context_mode_sizes_reply(self):
        m = ModelFixture(unit_id='LARGE-1', ack_text='ACK').start()
        try:
            m.mode = 'large_context'
            m.large_bytes = 4096
            status, body = self._post_on(m)
            item = json.loads([line[len('data: '):] for line in body.splitlines()
                               if line.startswith('data: ')
                               and '"response.output_item.done"' in line][0])['item']
            self.assertEqual(len(item['content'][0]['text']), 4096)
        finally:
            m.close()

    def test_unauthorized_bearer_rejected_and_ledgered(self):
        request = urllib.request.Request(self.m.base_url + '/responses', data=b'{}')
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 401)
        self.assertTrue(any(e.get('authorized') is False for e in self.m.entries('request')))

    @staticmethod
    def _post_on(m, body=None):
        request = urllib.request.Request(
            m.base_url + '/responses',
            data=json.dumps(body or {'model': 'fixture-model', 'input': [], 'stream': True}).encode(),
            headers={'Authorization': 'Bearer ' + m.bearer})
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode()


@unittest.skipIf(shutil.which('codex') is None, 'no local codex binary on this host')
class CodexPositiveControlTests(unittest.TestCase):
    def test_profile_a_ack_round_trip(self):
        from codex_adapter import CodexAdapter
        m = ModelFixture(unit_id='PC-1', ack_text='ACK_PC_1').start()
        adapter = CodexAdapter(shutil.which('codex'), 'PC-1', m.base_url)
        try:
            result = adapter.run('Return the acknowledgment exactly.', timeout=120)
            self.assertEqual(result['exit'], 0)
            self.assertIn('ACK_PC_1', result['stdout'])
            requests = m.entries('request')
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]['unit_id'], 'PC-1')
            self.assertEqual(m.entries('response-sent')[0]['response_type'], 'ack')
        finally:
            adapter.close()
            m.close()


if __name__ == '__main__':
    unittest.main()
