"""The cache condition requires actual replayed bytes and a single effect."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from session_authority_cases import CachedAuthorityPeer


class AuthorityResultCacheTest(unittest.TestCase):
    def test_cache_reuses_original_result_without_repeating_effect(self):
        peer=CachedAuthorityPeer('OWNED_CANARY',port=0)
        try:
            session=peer.session();peer.register('owned-effect')
            request=dict(jsonrpc='2.0',id='first',method='tools/call',params=dict(name='eval_probe',arguments=dict(token='owned-effect')))
            first=peer.response(request,session)
            request['id']='second';second=peer.response(request,session)
            self.assertEqual(first['result'],second['result'])
            self.assertEqual(second['id'],'second')
            self.assertIn('OWNED_CANARY',str(second['result']))
            self.assertEqual(peer.receipts,{'owned-effect':1})
            self.assertEqual(sum(e['kind']=='owned-cached-result-served' for e in peer.events),1)
        finally:peer.close()
