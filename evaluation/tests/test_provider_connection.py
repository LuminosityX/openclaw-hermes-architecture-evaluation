"""Check credentials without generating tokens or retaining credential-bearing data."""
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from provider_connection import check, NoRedirect


class ConnectionTests(unittest.TestCase):
    def test_only_models_metadata_is_requested(self):
        calls=[]
        def open_request(request,timeout):
            calls.append(request)
            self.assertEqual(request.full_url,'https://api.deepseek.com/models')
            self.assertEqual(request.get_method(),'GET')
            self.assertIsNone(request.data)
            return io.BytesIO(json.dumps(dict(data=[dict(id='deepseek-flash',name='versioned-name',private='not-retained')])).encode())
        report=check('synthetic-test-only',open_request)
        self.assertEqual(len(calls),1)
        self.assertEqual(report['completion_requests'],0)
        self.assertNotIn('synthetic-test-only',json.dumps(report))
        self.assertNotIn('not-retained',json.dumps(report))

    def test_missing_key_never_calls_network(self):
        with self.assertRaisesRegex(ValueError,'not configured'): check('',lambda *a: self.fail('network invoked'))

    def test_invalid_key_body_is_not_logged(self):
        def reject(*a,**kw):
            raise urllib.error.HTTPError('https://api.deepseek.com/models',401,'unauthorized',{},io.BytesIO(b'synthetic-secret-in-body'))
        with self.assertRaisesRegex(ValueError,'HTTP 401') as context: check('synthetic-key',reject)
        self.assertNotIn('synthetic-secret-in-body',str(context.exception))

    def test_redirect_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'must not redirect'):
            NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid')

    def test_requested_model_must_exist(self):
        with self.assertRaisesRegex(ValueError,'did not advertise'):
            check('synthetic-key',lambda *a,**kw: io.BytesIO(b'{"data":[{"id":"different-model"}]}'))
