"""The synthetic authority enforces PKCE, exact grants and single-use refresh."""
import http.client
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import urlencode,urlsplit,parse_qs

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from oauth_fixture import OAuthPeer,pkce
from oauth_cases import make_tls_fixture


class OAuthAuthorityTest(unittest.TestCase):
    def setUp(self):self.peer=OAuthPeer(read_only=True)
    def tearDown(self):self.peer.close()
    def call(self,method,path,data=None,port=18089,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
        try:
            connection.request(method,path,json.dumps(data) if data is not None else None,headers or ({'Content-Type':'application/json'} if data is not None else {}))
            response=connection.getresponse();raw=response.read();return response.status,dict(response.getheaders()),json.loads(raw) if raw else None
        finally:connection.close()

    def test_pkce_scope_and_refresh_rotation_have_positive_and_negative_controls(self):
        status,_,client=self.call('POST','/register',dict(redirect_uris=['http://127.0.0.1:12345/callback']))
        self.assertEqual(status,201);verifier='owned-verifier-'+'a'*50
        params=dict(client_id=client['client_id'],redirect_uri='http://127.0.0.1:12345/callback',code_challenge=pkce(verifier),code_challenge_method='S256',response_type='code',state='owned-state')
        def authorize():
            status,headers,_=self.call('GET','/authorize?'+urlencode(params));self.assertEqual(status,302)
            return parse_qs(urlsplit(headers['Location']).query)['code'][0]
        body=dict(grant_type='authorization_code',client_id=client['client_id'],redirect_uri=params['redirect_uri'],code=authorize(),code_verifier='incorrect')
        self.assertEqual(self.call('POST','/token',body)[0],400)
        body.update(code=authorize(),code_verifier=verifier);status,_,tokens=self.call('POST','/token',body)
        self.assertEqual(status,200);self.assertEqual(tokens['scope'],'mcp.read')
        refresh=dict(grant_type='refresh_token',refresh_token=tokens['refresh_token'],client_id=client['client_id'])
        status,_,rotated=self.call('POST','/token',refresh);self.assertEqual(status,200)
        self.assertEqual(self.call('POST','/token',refresh)[0],400)

        headers={'Content-Type':'application/json','Authorization':'Bearer '+rotated['access_token']}
        status,response,_=self.call('POST','/mcp',dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2025-03-26')),18085,headers)
        self.assertEqual(status,200);headers['Mcp-Session-Id']=response['Mcp-Session-Id'];self.peer.register('owned-read')
        payload=dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='eval_probe',arguments=dict(token='owned-read',action='effect')))
        self.assertEqual(self.call('POST','/mcp',payload,18085,headers)[0],403)
        self.assertFalse(self.peer.receipts)
        payload['params']['arguments']['action']='read'
        self.assertEqual(self.call('POST','/mcp',payload,18085,headers)[0],200)
        self.assertEqual(self.peer.receipts['owned-read'],1)
        self.peer.revoked=True;refresh['refresh_token']=rotated['refresh_token']
        self.assertEqual(self.call('POST','/token',refresh)[0],400)

    def test_resource_metadata_challenge_preserves_a_host_starting_with_mcp(self):
        with patch('oauth_fixture.RESOURCE','https://mcp.evaluation.test:18085/mcp'):
            status,headers,_=self.call('POST','/mcp',dict(jsonrpc='2.0',id=1,method='initialize'),18085)
        self.assertEqual(status,401)
        self.assertEqual(headers['WWW-Authenticate'],'Bearer resource_metadata="https://mcp.evaluation.test:18085/.well-known/oauth-protected-resource/mcp"')


class OAuthTlsFixtureTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('openssl'),'System openssl is required for the owned TLS fixture')
    def test_owned_ca_preserves_chain_and_hostname_verification(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)/'tls';metadata=make_tls_fixture(root)
            base=[shutil.which('openssl'),'verify','-CAfile',str(root/'ca.crt')]
            valid=subprocess.run([*base,'-verify_hostname','mcp.evaluation.test',str(root/'server.crt')],capture_output=True,text=True)
            denied=subprocess.run([*base,'-verify_hostname','different.evaluation.test',str(root/'server.crt')],capture_output=True,text=True)
            self.assertEqual(valid.returncode,0,valid.stderr)
            self.assertNotEqual(denied.returncode,0)
            self.assertFalse(metadata['tls_verification_disabled'])
