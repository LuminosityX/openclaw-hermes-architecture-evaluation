"""A live old MCP session must be reauthorized before each owned effect."""
import http.client
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from credential_cases import CredentialPeer


class CredentialRevocationTest(unittest.TestCase):
    def test_revocation_denies_the_same_live_session_without_leaking_credential(self):
        secret='synthetic-unit-test-credential';peer=CredentialPeer(secret,port=0)
        def send(body,session=None):
            connection=http.client.HTTPConnection('127.0.0.1',peer.server.server_address[1],timeout=3)
            try:
                headers={'Content-Type':'application/json','Authorization':'Bearer '+secret}
                if session:headers['Mcp-Session-Id']=session
                connection.request('POST','/mcp',json.dumps(body),headers)
                response=connection.getresponse();return response.status,response.getheader('Mcp-Session-Id'),json.loads(response.read())
            finally:connection.close()
        try:
            status,session,_=send(dict(jsonrpc='2.0',id=1,method='initialize',params={}))
            self.assertEqual(status,200);self.assertTrue(session)
            peer.register('granted');peer.register('revoked')
            call=lambda token:dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='eval_probe',arguments=dict(token=token)))
            self.assertEqual(send(call('granted'),session)[0],200)
            peer.revoke();self.assertEqual(send(call('revoked'),session)[0],401)
            self.assertEqual(peer.receipts,{'granted':1})
            rejected=[e for e in peer.events if e['kind']=='credential-authorization-check' and not e['allowed']]
            self.assertTrue(rejected);self.assertEqual(rejected[-1]['mcp_generation'],1)
            self.assertNotIn(secret,json.dumps(peer.events))
        finally:peer.close()
