"""Public-wire fixtures and synthetic credential boundaries."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import gateway_auth_cases


class GatewayAuthFixtureTests(unittest.TestCase):
    def test_authentication_remains_enabled_and_origins_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            config=gateway_auth_cases.configure(Path(directory)/'native')
            self.assertEqual(config['gateway']['auth']['mode'],'token')
            self.assertEqual(config['gateway']['controlUi']['allowedOrigins'],['http://127.0.0.1:18789'])
            self.assertNotIn('dangerouslyDisableDeviceAuth',config['gateway']['controlUi'])
            self.assertNotIn('allowInsecureAuth',config['gateway']['controlUi'])
            self.assertNotIn('trustedProxies',config['gateway'])

    def test_scope_matches_the_frozen_security_family(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        family=next(c for c in plan['cases'] if c['id']=='SEC-11')
        self.assertEqual(set(gateway_auth_cases.SCENARIOS),{s['id'] for s in family['scenarios']})

    @unittest.skipUnless(shutil.which('node'),'Existing Node required only for a pure cryptographic fixture check')
    def test_signed_device_fixture_rejects_changed_nonce(self):
        path=Path(__file__).resolve().parents[1]/'runner/gateway_auth_probe.mjs'
        completed=subprocess.run([shutil.which('node'),str(path),'--selfcheck'],capture_output=True,text=True,timeout=10,check=True)
        report=json.loads(completed.stdout)
        self.assertTrue(report['ed25519_signature_verified'])
        self.assertTrue(report['modified_nonce_rejected'])


if __name__=='__main__':unittest.main()
