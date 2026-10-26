"""Independent checks for workload fixtures, state locks and resource attribution."""
import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'runner'))
import mechanism_cases as cases


class MechanismFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = cases.MechanismFixture()
        self.connection = http.client.HTTPConnection('127.0.0.1', 18080, timeout=3)

    def tearDown(self):
        self.connection.close()
        self.fixture.close()

    def post(self, path, data):
        self.connection.request('POST', path, json.dumps(data), {'Content-Type': 'application/json'})
        response = self.connection.getresponse()
        return response.status, json.loads(response.read())

    def test_receipt_ledger_rejects_unknown_effect_and_exposes_duplicate(self):
        token = 'PILOT_TEST'
        self.fixture.register(token)
        self.assertEqual(self.post('/effect', dict(token='PILOT_UNKNOWN'))[0], 400)
        self.assertEqual(self.fixture.receipts, {})
        for ordinal in [1, 2]:
            status, body = self.post('/effect', dict(token=token, owner='test-plugin'))
            self.assertEqual(status, 200)
            self.assertEqual(body['receipt'], 'RECEIPT:'+token)
            commits = [e for e in self.fixture.events if e['kind'] == 'effect-commit']
            self.assertEqual(commits[-1]['ordinal'], ordinal)
        self.assertEqual(self.fixture.receipts[token], 2)

    def test_provider_uses_current_turn_and_public_dispatch(self):
        token = 'PILOT_LATEST'
        self.fixture.register(token, tool='eval_other', action='throw')
        request = dict(stream=False, messages=[dict(role='user', content='PILOT_OLDER'),
            dict(role='tool', content='RECEIPT:PILOT_OLDER'), dict(role='user', content=token)],
            tools=[dict(type='function', function=dict(name='tool_call'))])
        status, response = self.post('/v1/chat/completions', request)
        self.assertEqual(status, 200)
        call = response['choices'][0]['message']['tool_calls'][0]['function']
        self.assertEqual(call['name'], 'tool_call')
        self.assertEqual(json.loads(call['arguments']), dict(id='eval_other', args=dict(token=token, action='throw')))
        self.assertEqual(self.fixture.receipts, {})
        request['messages'].append(dict(role='tool', content='synthetic failure without a receipt'))
        _, response = self.post('/v1/chat/completions', request)
        self.assertEqual(response['choices'][0]['message']['content'], 'CONTROLLED_ERROR:'+token)

    def test_native_plugin_dependency_fixtures_are_private_and_config_is_strict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'plugins'
            config = cases.configure(root, 'EXT-09-S04')
            paths = [Path(p) for p in config['plugins']['load']['paths']]
            versions = [json.loads((p/'node_modules/eval-private-dependency/package.json').read_text())['version'] for p in paths]
            self.assertEqual(versions, ['1.0.0', '2.0.0'])
            for path in paths:
                manifest = json.loads((path/'openclaw.plugin.json').read_text())
                self.assertFalse(manifest['configSchema']['additionalProperties'])
                source = (path/'index.js').read_text()
                self.assertIn('api.pluginConfig?.tag', source)
                self.assertNotIn('/runtime/node_modules/openclaw/', source)

    def test_all_new_scenario_ids_match_the_frozen_plan(self):
        plan = json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026/plan.json').read_text())
        expected = {s['id'] for family in plan['cases'] if family['id'] in cases.FAMILIES for s in family['scenarios']}
        self.assertEqual(set(cases.SCENARIOS), expected)
        self.assertEqual(len(expected), 24)


class ResourceAttributionTests(unittest.TestCase):
    def test_missing_product_does_not_count_the_collector_as_product(self):
        result = cases.process_snapshot(2**30)
        self.assertEqual(result['processes'], 0)
        self.assertEqual(result['rss_bytes'], 0)
        self.assertEqual(result['pids'], [])

    def test_missing_cgroup_counters_remain_unknown(self):
        result = cases.cgroup_snapshot()
        # Ordinary unit-test environments have no run-owned measurement mount.
        if not Path('/measurement/cgroup').exists():
            self.assertTrue(all(value is None for value in result['counters'].values()))
            self.assertTrue(result['missing_counter_reason'])
        self.assertIn('fixture', result['scope'])


if __name__ == '__main__':
    unittest.main()
