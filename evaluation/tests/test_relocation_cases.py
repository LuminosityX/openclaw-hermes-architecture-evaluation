"""UID tests add only owned migration authority and keep public record checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import relocation_cases
from run_local import sandbox_command


class RelocationFixtureTests(unittest.TestCase):
    def test_scope_and_extension_counter_are_native_runtime_operations(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'campaigns/full-20261026-batched/plan.json').read_text())
        expected={s['id'] for c in plan['cases'] if c['id']=='REL-06' for s in c['scenarios']}
        self.assertEqual(expected,set(relocation_cases.SCENARIOS))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'owned';relocation_cases.configure(root)
            source=(root/'composition-a/index.js').read_text()
            self.assertIn("process.env.OPENCLAW_STATE_DIR+'/owned-extension-counter.json'",source)
            self.assertIn('persisted_counter:persistedCounter',source)
            self.assertIn('uid:process.getuid?.()',source)

    def test_chown_capability_is_not_added_to_normal_experiments(self):
        common=(Path('/owned/modules'),Path('/owned/node'),64,[])
        ordinary=sandbox_command(*common,ssh_backend=True)
        self.assertNotIn('CAP_CHOWN',ordinary)
        self.assertNotIn('CAP_KILL',ordinary)
        migration=sandbox_command(*common,ssh_backend=True,identity_migration=True)
        self.assertIn('CAP_CHOWN',migration)
        self.assertIn('CAP_KILL',migration)
        self.assertNotIn('CAP_DAC_OVERRIDE',migration)
        with self.assertRaisesRegex(ValueError,'hosted'):
            sandbox_command(*common,identity_migration=True)

    def test_owner_mutation_rejects_unowned_paths_without_touching_them(self):
        with self.assertRaisesRegex(RuntimeError,'owned fixture'):
            relocation_cases.owned_chown(Path('/usr'),1001)


if __name__=='__main__':unittest.main()
