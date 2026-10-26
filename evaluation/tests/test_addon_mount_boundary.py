"""A native addon profile cannot widen mounts beyond the owned runtime prefix."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_local import sandbox_command


class AddonMountTest(unittest.TestCase):
    def test_readonly_addon_mount_keeps_original_path_and_rejects_foreign_roots(self):
        with tempfile.TemporaryDirectory() as name:
            prefix=Path(name)/'owned';modules=prefix/'node_modules';modules.mkdir(parents=True)
            project=prefix/'addon';package=project/'node_modules/official-package';package.mkdir(parents=True)
            template=dict(kind='native-official-addon-install-template',project_root=str(project),package_root=str(package))
            path=prefix/'official-addon-template.json';path.write_text(json.dumps(template))
            (prefix/'official-addon-state.sqlite').write_bytes(b'owned-test-snapshot-not-a-runtime')
            command=sandbox_command(modules,Path('/node'),128,[],ssh_backend=True,official_addon=True)
            start=command.index(str(project));self.assertEqual(command[start-1:start+2],['--ro-bind',str(project),str(project)])
            self.assertIn('/official-addon.json',command)
            pairs=[command[i:i+3] for i in range(len(command)-2) if command[i]=='--ro-bind']
            self.assertIn(['--ro-bind',str(modules),str(modules)],pairs)
            self.assertNotIn(['--ro-bind',str(prefix),str(prefix)],pairs)
            template['project_root']=name;path.write_text(json.dumps(template))
            with self.assertRaisesRegex(ValueError,'owned hosted runtime'):sandbox_command(modules,Path('/node'),128,[],official_addon=True)
