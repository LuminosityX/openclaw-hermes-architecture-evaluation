"""Recovery fixtures retain real process exits and always-ask operator policy."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
import recovery_cases


class RecoveryFixtureTests(unittest.TestCase):
    def test_scope_matches_all_frozen_recovery_scenarios(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id']=='REL-04' for s in c['scenarios']}
        self.assertEqual(expected,set(recovery_cases.SCENARIOS))

    def test_confirmation_policy_is_not_bypassed_and_plugin_exit_is_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'approval';config=recovery_cases.configure(root,'operator-confirmation')
            self.assertEqual(config['tools']['exec'],dict(host='gateway',security='full',ask='always'))
            self.assertEqual(config['gateway']['controlUi']['allowedOrigins'],['http://127.0.0.1:18789'])
            self.assertNotIn('dangerouslyDisableDeviceAuth',config['gateway']['controlUi'])
            root=Path(directory)/'exit';recovery_cases.configure(root,'plugin-exit')
            source=(root/'composition-a/index.js').read_text()
            self.assertIn('process.exit(42)',source)
            self.assertIn('owned-crash-occurred',source)
            self.assertIn('!fs.existsSync',source)


if __name__=='__main__':unittest.main()
