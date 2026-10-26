"""The remote peer's lost-ack and idempotency arms must stay distinguishable."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from effect_recovery_cases import EffectPeer
from mcp_http_fixture import McpHTTPFixture


class EffectBoundaryTest(unittest.TestCase):
    def fixture(self):
        peer=EffectPeer.__new__(EffectPeer)
        peer.drop_before=set();peer.idempotent=set();peer.sessions={'s':dict(valid=True,generation=1)}
        peer.receipts={};peer.events=[]
        peer.event=lambda kind,**values:peer.events.append(dict(kind=kind,**values))
        return peer

    def call(self):return dict(method='tools/call',id=7,params=dict(arguments=dict(token='owned-effect')))

    def test_before_commit_loss_closes_session_without_effect(self):
        peer=self.fixture();peer.drop_before.add('owned-effect')
        with patch.object(McpHTTPFixture,'response',side_effect=AssertionError('must not dispatch effect')):
            self.assertTrue(peer.response(self.call(),'s')['_drop_connection'])
        self.assertEqual(peer.receipts,{})
        self.assertFalse(peer.sessions['s']['valid'])

    def test_deduplication_requires_explicit_remote_key_grant(self):
        peer=self.fixture();peer.receipts['owned-effect']=1;peer.idempotent.add('owned-effect')
        with patch.object(McpHTTPFixture,'response',side_effect=AssertionError('must not commit twice')):
            self.assertIn('RECEIPT:owned-effect',str(peer.response(self.call(),'s')))
        self.assertEqual(peer.receipts['owned-effect'],1)
        peer.idempotent.clear()
        with patch.object(McpHTTPFixture,'response',return_value={'ordinary_unkeyed_dispatch':True}) as original:
            self.assertTrue(peer.response(self.call(),'s')['ordinary_unkeyed_dispatch'])
            original.assert_called_once()
