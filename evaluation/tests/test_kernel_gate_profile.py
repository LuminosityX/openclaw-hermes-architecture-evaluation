"""Extra evaluator capabilities are restricted to the explicit owned gate profile."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_local import sandbox_command


class KernelGateProfileTest(unittest.TestCase):
    def test_default_sandbox_does_not_gain_kernel_gate_authority(self):
        ordinary=sandbox_command(Path('/owned/modules'),Path('/owned/node'),128,[],ssh_backend=True)
        self.assertNotIn('CAP_SYS_ADMIN',ordinary);self.assertNotIn('CAP_SETPCAP',ordinary)
        explicit=sandbox_command(Path('/owned/modules'),Path('/owned/node'),128,[],ssh_backend=True,permission_gate=True)
        self.assertIn('CAP_SYS_ADMIN',explicit);self.assertIn('CAP_SETPCAP',explicit)
        self.assertIn('--unshare-net',explicit);self.assertIn('--cap-drop',explicit)
        self.assertNotIn('--unshare-user',explicit)

    def test_user_namespace_profile_cannot_silently_fake_native_kernel_permission_gate(self):
        with self.assertRaisesRegex(ValueError,'non-user-namespace'):
            sandbox_command(Path('/owned/modules'),Path('/owned/node'),128,[],permission_gate=True)
