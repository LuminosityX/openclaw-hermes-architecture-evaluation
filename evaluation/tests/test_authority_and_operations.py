"""Owned authority policy and native-record diagnosis oracles."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import execution_authority_cases as authority
import operational_diagnosis_cases as operations
from operation_fixture import OperationFixture
import isolation_setup_cases


class AuthorityAndOperationsTests(unittest.TestCase):
    def test_exact_campaign_scope_and_explicit_authority_policy(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id'] in {'SEC-01','OBS-05'} for s in c['scenarios']}
        self.assertEqual(expected,set(authority.SCENARIOS)|set(operations.SCENARIOS))
        with tempfile.TemporaryDirectory() as directory:
            config=authority.configure(Path(directory)/'native','native-file')
            self.assertTrue(config['tools']['fs']['workspaceOnly'])
            self.assertEqual(config['tools']['exec'],dict(host='gateway',security='full',ask='off'))
            self.assertEqual(config['agents']['defaults']['sandbox']['mode'],'off')

    def test_setup_family_scope_and_fault_command_effect_is_independently_visible(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id']=='SEC-03' for s in c['scenarios']}
        self.assertEqual(expected,set(isolation_setup_cases.SCENARIOS))
        import shlex,subprocess
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'owned-effect.txt'
            arguments=isolation_setup_cases.command(destination,'SYNTHETIC_EXPECTED_EFFECT')
            result=subprocess.run(shlex.split(arguments['command']),capture_output=True,text=True,timeout=5,check=True)
            self.assertEqual(destination.read_text(),'SYNTHETIC_EXPECTED_EFFECT')
            self.assertIn('SYNTHETIC_EXPECTED_EFFECT',result.stdout)

    def test_ambiguous_or_absent_diagnostic_records_remain_unknown(self):
        self.assertEqual(operations.diagnose('service stopped')['cause'],'unknown')
        self.assertEqual(operations.diagnose('SQLITE_FULL\nfile is not a database')['cause'],'unknown')
        self.assertEqual(operations.diagnose('SQLITE_NOTADB: file is not a database')['cause'],'state-corruption')
        self.assertEqual(operations.diagnose('Invalid config: gateway.port expected number')['cause'],'invalid-configuration')
        self.assertEqual(operations.diagnose('EVAL_EXTENSION_STARTUP_FAILURE')['cause'],'extension-startup')
        self.assertEqual(operations.diagnose('ENOSPC: no space left on device')['cause'],'storage-exhaustion')

    def test_provider_cannot_claim_acceptance_without_a_real_tool_return(self):
        fixture=OperationFixture();token='PILOT_OPERATION_ORACLE'
        try:
            fixture.plan(token,'read',dict(path='/owned/file'),'OWNED_CANARY')
            connection=http.client.HTTPConnection('127.0.0.1',18080,timeout=3)
            base=dict(model='fixture-model',stream=False,tools=[dict(type='function',function=dict(name='read'))])
            for message,expected in [('different result',False),('OWNED_CANARY',True)]:
                body=dict(base,messages=[dict(role='user',content=token),dict(role='tool',tool_call_id='example',content=message)])
                connection.request('POST','/v1/chat/completions',json.dumps(body),{'Content-Type':'application/json'})
                response=connection.getresponse();result=json.loads(response.read())
                self.assertEqual('ACCEPTED:'+token in result['choices'][0]['message']['content'],expected)
            connection.close()
            self.assertFalse(fixture.receipts)
        finally:fixture.close()


if __name__=='__main__':unittest.main()
