"""Rebind and repeated-disconnect fixtures must enforce real independent faults."""
import http.client
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import lifecycle_cases as lifecycle


class LifecycleFixtureTests(unittest.TestCase):
    def test_exact_frozen_family_scope(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id'] in lifecycle.FAMILIES for s in c['scenarios']}
        self.assertEqual(expected,set(lifecycle.SCENARIOS))
        self.assertEqual(len(expected),12)

    def test_rebind_revokes_old_credentials_without_stopping_tool_receipts(self):
        fixture=lifecycle.RebindFixture()
        try:
            fixture.grants[18082]='synthetic-generation-b'
            connection=http.client.HTTPConnection('127.0.0.1',18082,timeout=3)
            connection.request('POST','/v1/chat/completions','{}',{'Authorization':'Bearer synthetic-generation-a'})
            response=connection.getresponse();response.read();connection.close()
            self.assertEqual(response.status,401)
            fixture.close_old()
            fixture.register('PILOT_REBIND_TEST')
            connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=3)
            connection.request('POST','/effect',json.dumps(dict(token='PILOT_REBIND_TEST')),{'Content-Type':'application/json'})
            response=connection.getresponse();response.read();connection.close()
            self.assertEqual(response.status,200)
            self.assertEqual(fixture.receipts,{'PILOT_REBIND_TEST':1})
        finally:fixture.close()

    def test_actual_provider_socket_is_dropped_once_before_retry(self):
        fixture=lifecycle.DisconnectFixture(); token='PILOT_DISCONNECT_TEST'
        try:
            fixture.register(token);fixture.drop_tokens.add(token)
            body=json.dumps(dict(model='fixture-model',messages=[dict(role='user',content=token)],
                tools=[dict(type='function',function=dict(name='eval_probe'))],stream=False))
            connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=3)
            connection.request('POST','/v1/chat/completions',body,{'Content-Type':'application/json'})
            with self.assertRaises(http.client.RemoteDisconnected):connection.getresponse()
            connection.close()
            connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=3)
            connection.request('POST','/v1/chat/completions',body,{'Content-Type':'application/json'})
            response=connection.getresponse();response.read();connection.close()
            self.assertEqual(response.status,200)
            self.assertEqual(fixture.dropped,{token})
            self.assertEqual(sum(e['kind']=='provider-connection-dropped' for e in fixture.events),1)
        finally:fixture.close()


if __name__=='__main__':unittest.main()
