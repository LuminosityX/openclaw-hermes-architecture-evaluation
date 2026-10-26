"""Official provider identity must be verified independently from host build."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from provider_plugin import PIN, verify


class ProviderPluginTests(unittest.TestCase):
    def test_changed_provider_integrity_is_rejected(self):
        pin=json.loads(PIN.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            package=root/'node_modules'/pin['package'];package.mkdir(parents=True)
            (package/'dist').mkdir()
            (package/'package.json').write_text(json.dumps(dict(version=pin['version'])))
            (package/'openclaw.plugin.json').write_text(json.dumps(dict(id=pin['plugin_id'])))
            (package/'dist/index.js').write_text('synthetic fixture only')
            lock=root/'package-lock.json'
            entry=dict(version=pin['version'],integrity=pin['integrity'])
            lock.write_text(json.dumps(dict(packages={'node_modules/'+pin['package']:entry})))
            self.assertTrue(verify(root/'node_modules',lock)['integrity_matches'])
            entry['integrity']='substituted-package'
            lock.write_text(json.dumps(dict(packages={'node_modules/'+pin['package']:entry})))
            with self.assertRaisesRegex(ValueError,'integrity'): verify(root/'node_modules',lock)
