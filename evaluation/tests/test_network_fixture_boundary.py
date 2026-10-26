"""Network-test privileges are confined to a distinct, isolated hosted profile."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from network_boundary_cases import dns_question
from run_local import sandbox_command


class NetworkBoundaryTest(unittest.TestCase):
    def test_network_capabilities_require_an_isolated_non_user_namespace(self):
        with self.assertRaises(ValueError):sandbox_command(Path('/modules'),Path('/node'),64,[],network_fixture=True)
        ordinary=sandbox_command(Path('/modules'),Path('/node'),64,[],ssh_backend=True)
        self.assertNotIn('CAP_NET_ADMIN',ordinary)
        special=sandbox_command(Path('/modules'),Path('/node'),64,[],ssh_backend=True,network_fixture=True)
        self.assertIn('--unshare-net',special)
        self.assertIn('CAP_NET_ADMIN',special)
        self.assertIn('CAP_NET_BIND_SERVICE',special)
        self.assertNotIn('/etc/resolv.conf',special)

    def test_owned_dns_parser_preserves_actual_query_and_rejects_oversized_labels(self):
        question=b'\x06rebind\x0aevaluation\x04test\x00'+struct.pack('!HH',1,1)
        packet=struct.pack('!HHHHHH',33,0x100,1,0,0,0)+question
        self.assertEqual(dns_question(packet),('rebind.evaluation.test',1,1,question))
        for bad in [b'',packet[:12]+b'\xc0\x0c',packet+b'x'*513]:
            with self.assertRaises(ValueError):dns_question(bad)
