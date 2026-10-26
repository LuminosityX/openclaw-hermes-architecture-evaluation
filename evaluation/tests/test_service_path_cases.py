"""Verify independent measurement oracles without installing the product locally."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import service_path_cases as service
import trace_access_cases as trace


class ServicePathOracleTests(unittest.TestCase):
    def test_abort_contract_uses_status_and_liveness_not_a_nonnull_run_id(self):
        import itertools
        for pending,status in itertools.product([False,True],['aborted','no-active-run']):
            cancellation=dict(returncode=0,stdout=json.dumps(dict(ok=True,status=status,abortedRunId=None)))
            self.assertEqual(service.active_abort_acknowledged(cancellation,dict(request_pending_before_rpc=pending)),pending and status=='aborted')

    def test_new_families_match_every_frozen_scenario(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        selected=[*service.FAMILIES,'OBS-07']
        expected={s['id'] for c in plan['cases'] if c['id'] in selected for s in c['scenarios']}
        self.assertEqual(expected,set(service.SCENARIOS)|set(trace.SCENARIOS))
        self.assertEqual(len(expected),25)

    def test_large_catalogue_has_executable_registrations_and_owned_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'native'
            config=service.configure(root,128)
            source=(root/'composition-a/index.js').read_text()
            self.assertIn('api.registerTool({"name": "padding_126"',source)
            self.assertEqual(len(config['tools']['allow']),128)
            inventory=service.owned_inventory(root)
            self.assertGreater(inventory['file_inodes'],4)
            self.assertGreater(inventory['apparent_bytes'],0)
            self.assertFalse(inventory['shared_runtime_included'])

    def test_diagnosis_has_no_access_to_fixture_truth(self):
        known=json.dumps(dict(messages=[dict(role='toolResult',toolName='eval_probe',
            content='EVAL_COMPOSITION_TOOL_FAILURE')])).encode()
        self.assertTrue(trace.record_diagnosis(known)['tool_failure'])
        unknown=json.dumps(dict(messages=[dict(content='An unknown operation failed')])).encode()
        self.assertEqual(trace.record_diagnosis(unknown)['cause_boundary'],'unknown')

    def test_synthetic_nonzero_usage_and_input_shape_are_independent(self):
        fixture=trace.UsageFixture()
        connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=3)
        try:
            token='PILOT_TEST_USAGE';fixture.register(token)
            for stream in [False,True]:
                body=dict(model='fixture-model',messages=[dict(role='user',content=token)],stream=stream,
                    tools=[dict(type='function',function=dict(name='eval_probe',parameters=dict(type='object')))])
                connection.request('POST','/v1/chat/completions',json.dumps(body),{'Content-Type':'application/json'})
                response=connection.getresponse();raw=response.read()
                self.assertEqual(response.status,200)
                if stream:
                    self.assertIn(b'"prompt_tokens": 41',raw)
                    self.assertTrue(raw.endswith(b'data: [DONE]\n\n'))
                else:self.assertEqual(json.loads(raw)['usage']['completion_tokens'],7)
            self.assertEqual(len(fixture.reported_usage),2)
            shapes=[e for e in fixture.events if e['kind']=='provider-input-shape']
            self.assertEqual([e['tool_catalogue_count'] for e in shapes],[1,1])
            self.assertFalse(fixture.receipts)
        finally:connection.close();fixture.close()


if __name__=='__main__':unittest.main()
