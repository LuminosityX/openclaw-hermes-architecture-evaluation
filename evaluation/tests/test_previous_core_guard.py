"""Historical controls stay read-only, explicitly pinned and hosted-only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_local import ROOT,controller_source_hashes,sandbox_command


class PreviousCoreGuardTest(unittest.TestCase):
    def test_native_proof_binds_historical_installer_and_pin_data(self):
        hashes=controller_source_hashes('EXT-03')
        for name in ['evaluation/tools/prepare_previous_core.py','evaluation/design/previous-core.json']:
            self.assertIn(name,hashes);self.assertEqual(len(hashes[name]),64)

    def test_previous_mount_refuses_an_unpinned_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);previous=root/'openclaw-previous-runtime';previous.mkdir()
            expected=json.loads((ROOT/'evaluation/design/previous-core.json').read_text())
            identity=dict(current_campaign_target=False,target=expected)
            (previous/'identity.json').write_text(json.dumps(identity))
            command=sandbox_command(root/'runtime/node_modules',root/'node',128,[],previous_core=True)
            at=command.index(str(previous));self.assertEqual(command[at-1],'--ro-bind');self.assertEqual(command[at+1],'/previous')
            identity['target']={**expected,'version':'unexpected'};(previous/'identity.json').write_text(json.dumps(identity))
            with self.assertRaisesRegex(ValueError,'comparison identity'):
                sandbox_command(root/'runtime/node_modules',root/'node',128,[],previous_core=True)

    def test_historical_installer_refuses_local_execution_before_preparing_files(self):
        result=subprocess.run([sys.executable,str(ROOT/'evaluation/tools/prepare_previous_core.py')],env=dict(os.environ,GITHUB_ACTIONS='false'),capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('GitHub Actions',result.stderr)
