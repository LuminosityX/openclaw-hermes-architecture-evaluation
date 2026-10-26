"""Dependency experiments expose the npm tool, not host project modules."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_local import sandbox_command

class DependencyToolchainTest(unittest.TestCase):
    def test_readonly_tool_only_mount_and_digest_guard(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);modules=root/'owned/node_modules';modules.mkdir(parents=True)
            npm=root/'tool/npm';(npm/'bin').mkdir(parents=True);(npm/'package.json').write_text('{"name":"npm"}')
            cli=npm/'bin/npm-cli.js';cli.write_text('owned CLI fixture')
            metadata=dict(npm_root=str(npm),npm_cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest())
            (modules.parent/'owned-npm-toolchain.json').write_text(json.dumps(metadata))
            command=sandbox_command(modules,Path('/node'),128,[],ssh_backend=True,dependency_installation=True)
            mounts=[command[i:i+3] for i in range(len(command)-2) if command[i]=='--ro-bind']
            self.assertIn(['--ro-bind',str(npm),'/toolchain/npm-package'],mounts)
            self.assertNotIn(['--ro-bind',str(npm.parent),str(npm.parent)],mounts)
            cli.write_text('changed')
            with self.assertRaisesRegex(ValueError,'digest changed'):sandbox_command(modules,Path('/node'),128,[],dependency_installation=True)
