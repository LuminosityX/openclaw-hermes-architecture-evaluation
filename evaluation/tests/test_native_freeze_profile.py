"""Only the explicitly owned native subtree gets mutable freeze controls."""
from pathlib import Path
import sys
import unittest
import json
import sqlite3
import tempfile
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

    def test_real_lease_envelope_uses_nested_process_owner(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
        from delegation_cases import owner_lease
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'state').mkdir()
            db=sqlite3.connect(root/'state/machine.sqlite')
            db.execute('create table state_leases(scope,lease_key,owner,expires_at,heartbeat_at,payload_json)')
            db.execute('insert into state_leases values(?,?,?,?,?,?)',('gateway-owner','global','synthetic-owner',123456,123000,json.dumps(dict(owner=dict(pid=321,host='owned-host'),port=18789,mode='foreground',supervisor=None))))
            db.commit();db.close()
            observed=owner_lease(root)
            self.assertEqual(observed['pid'],321)
            self.assertEqual(observed['port'],18789)
            self.assertNotIn('synthetic-owner',json.dumps(observed))
