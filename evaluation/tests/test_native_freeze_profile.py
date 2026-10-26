"""Only the explicitly owned native subtree gets mutable freeze controls."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_local import sandbox_command


class NativeFreezeProfileTest(unittest.TestCase):
    def test_ordinary_namespaces_do_not_expose_native_runtime_control(self):
        ordinary=sandbox_command(Path('/owned/modules'),Path('/owned/node'),128,[],ssh_backend=True)
        self.assertNotIn('/native-control/freeze',ordinary)
        explicit=sandbox_command(Path('/owned/modules'),Path('/owned/node'),128,[],ssh_backend=True,native_control_group=Path('/owned/cgroup/native'))
        for source,name in [('cgroup.procs','procs'),('cgroup.freeze','freeze'),('cgroup.kill','kill')]:
            index=explicit.index('/owned/cgroup/native/'+source)
            self.assertEqual(explicit[index-1],'--bind');self.assertEqual(explicit[index+1],'/native-control/'+name)
        self.assertIn('--unshare-pid',explicit);self.assertIn('--unshare-net',explicit)
