"""No credentials in the native namespace; real usage stays independently attributable."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'runner')]
from model_relay import Metadata, Relay, request_body, task_id
from provider_bridge import UnixConnection
from run_local import sandbox_command


class RelayTests(unittest.TestCase):
    def test_stream_fragmentation_retains_only_usage_and_identifiers(self):
        metadata=Metadata(True)
        response=(b'data: {"id":"completion-id","model":"deepseek-flash","choices":[{"delta":{"content":"private-response"}}]}\n\n'
                  b'data: {"usage":{"prompt_tokens":12,"completion_tokens":3,"prompt_cache_hit_tokens":4,"private":"excluded"},"choices":[]}\n\n'
                  b'data: [DONE]\n\n')
        for index in range(0,len(response),7): metadata.consume(response[index:index+7])
        metadata.finish()
        self.assertTrue(metadata.done)
        self.assertEqual(metadata.usage,{'prompt_tokens':12,'completion_tokens':3,'prompt_cache_hit_tokens':4})
        self.assertNotIn('private-response',str(metadata.__dict__))

    def test_truncated_usage_is_unknown(self):
        metadata=Metadata(True)
        metadata.consume(b'data: {"choices":[]}\n\ndata: [DONE]\n\n')
        metadata.finish()
        self.assertIsNone(metadata.usage)

    def test_provider_is_fixed_and_task_marker_attribution_uses_latest_user(self):
        body=request_body(dict(model='other',max_tokens=100000,messages=[dict(role='user',content='EVAL_OLD'),dict(role='user',content='EVAL_NEW')],stream=True))
        self.assertEqual(body['model'],'deepseek-flash')
        self.assertEqual(body['max_tokens'],4096)
        self.assertEqual(body['stream_options'],{'include_usage':True})
        self.assertEqual(task_id(body),'EVAL_NEW')

    def test_thinking_and_output_budget_are_explicit_conditions(self):
        body=request_body(dict(messages=[],stream=True),16384,'enabled')
        self.assertEqual(body['thinking'],{'type':'enabled'})
        self.assertEqual(body['max_tokens'],16384)
        with self.assertRaises(ValueError): request_body(dict(messages=[]),-1,'enabled')

    def test_unix_relay_never_passes_inbound_auth_or_follows_an_arbitrary_path(self):
        calls=[]
        class Response(io.BytesIO):
            status=200
            headers={'x-request-id':'provider-request-id'}
        def upstream(request,timeout):
            calls.append(request)
            self.assertEqual(request.full_url,'https://api.deepseek.com/chat/completions')
            self.assertEqual(request.get_header('Authorization'),'Bearer host-only-synthetic-key')
            return Response(b'{"id":"reply","model":"deepseek-flash","choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1}}')
        with tempfile.TemporaryDirectory() as directory:
            relay=Relay(Path(directory)/'socket','host-only-synthetic-key',open_request=upstream)
            thread=threading.Thread(target=relay.serve_forever,daemon=True);thread.start()
            try:
                connection=UnixConnection(str(relay.path))
                connection.request('POST','/v1/chat/completions',json.dumps(dict(messages=[dict(role='user',content='EVAL_TEST')],model='untrusted')),{'Authorization':'Bearer inbound-untrusted-key'})
                response=connection.getresponse();self.assertEqual(response.status,200);response.read();connection.close()
                connection=UnixConnection(str(relay.path))
                connection.request('POST','/user/balance',b'{}')
                response=connection.getresponse();self.assertEqual(response.status,404);response.read();connection.close()
            finally:
                relay.shutdown();thread.join();relay.write_ledger(Path(directory)/'usage.json');relay.server_close()
            ledger=(Path(directory)/'usage.json').read_text()
            self.assertEqual(len(calls),1)
            self.assertNotIn('host-only-synthetic-key',ledger)
            self.assertNotIn('inbound-untrusted-key',ledger)
            self.assertEqual(json.loads(ledger)['requests'][0]['usage']['prompt_tokens'],1)

    def test_namespace_clears_inherited_environment_and_binds_only_socket(self):
        command=sandbox_command(Path('/modules'),Path('/node'),64,[],relay_socket=Path('/owned/socket'))
        self.assertIn('--clearenv',command)
        self.assertNotIn('DEEPSEEK_API_KEY',str(command))
        self.assertIn('/relay/provider.sock',command)
        self.assertNotIn('--bind',command)
